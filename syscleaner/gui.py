"""GTK3 user interface for SysCleaner."""
from __future__ import annotations

import os
import pwd
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import __version__, diskscan, fileops, history, schedule, settings, updater  # noqa: E402
from .about import RESTART, AboutDialog  # noqa: E402
from .i18n import _  # noqa: E402
from .runner import BEGIN_RE, EST_RE, Runner, build_script, fmt_duration, fmt_size  # noqa: E402
from .tasks import READONLY_GROUPS, available, load  # noqa: E402

RISK = {"safe": _("🟢 safe"), "caution": _("🟡 caution"), "danger": _("🔴 dangerous")}
ERR_RE = re.compile(r"(?i)(\berror\b|\bfailed\b|permission denied|^E: )")

# Log colours per theme variant (picked automatically from the system GTK theme).
PALETTE = {
    "dark": {"head": "#6cb4ff", "err": "#ff7b72", "ok": "#5fd38d"},
    "light": {"head": "#1a5fb4", "err": "#c01c28", "ok": "#26a269"},
}
PAD = 12  # base spacing in pixels

# GTK themes draw a dashed `outline` around the focused list / log. On big panels it just looks
# like stray dashes (the selected row is already highlighted), so it is switched off for them only.
CSS = b"""
treeview.sc-nofocus:focus,
textview.sc-nofocus:focus,
textview.sc-nofocus text:focus {
    outline-style: none;
    outline-width: 0;
}
"""


def install_css():
    provider = Gtk.CssProvider()
    try:
        provider.load_from_data(CSS)
    except GLib.Error:
        return
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def themed_button(label, icon_name):
    """Button with a real theme icon next to the label (icon skipped if the theme lacks it)."""
    btn = Gtk.Button(label=label)
    theme = Gtk.IconTheme.get_default()
    if theme is not None and theme.has_icon(icon_name):
        btn.set_image(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))
        btn.set_always_show_image(True)
    return btn


def pad(widget, h=PAD, v=8):
    """Give a widget breathing room so text does not touch the edges."""
    widget.set_margin_start(h)
    widget.set_margin_end(h)
    widget.set_margin_top(v)
    widget.set_margin_bottom(v)
    return widget


def is_dark(widget) -> bool:
    """True if the current GTK theme has a dark base colour."""
    ctx = widget.get_style_context()
    for name in ("theme_base_color", "theme_bg_color"):
        found, rgba = ctx.lookup_color(name)
        if found:
            return (0.299 * rgba.red + 0.587 * rgba.green + 0.114 * rgba.blue) < 0.5
    return False


def _msg(parent, kind, text, secondary=None, buttons=Gtk.ButtonsType.OK):
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=kind, buttons=buttons, text=text)
    if secondary:
        d.format_secondary_text(secondary)
    r = d.run()
    d.destroy()
    return r


# ───────────────────────── "Disk" tab ─────────────────────────
class DiskTab(Gtk.Box):
    """ncdu-like browser: double-click enters a folder, the bar shows the share of the parent.

    Scanning streams results folder by folder, so a progress bar (percent of items done),
    the item being measured and the elapsed time are shown while it runs.
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_border_width(PAD)
        self._gen = 0            # scan generation: stale scans are ignored and killed
        self._proc = None
        self._scanning = False
        self._items: list = []
        self._n = self._done = 0
        self._cur = ""
        self._t0 = 0.0

        top = Gtk.Box(spacing=6)
        self.entry = Gtk.Entry(text=str(Path.home()), hexpand=True)
        self.entry.connect("activate", lambda *_a: self.scan(self.entry.get_text()))
        for label, fn in ((_("⬆ Up"), lambda *_a: self.scan(os.path.dirname(self.cur.rstrip("/")) or "/")),
                          ("🏠 ~", lambda *_a: self.scan(str(Path.home()))),
                          ("/", lambda *_a: self.scan("/"))):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            top.pack_start(b, False, False, 0)
        top.pack_start(self.entry, True, True, 0)
        self.chk_root = Gtk.CheckButton(label=_("as root"))
        self.chk_root.set_tooltip_text(_("Also see system folders you have no access to (asks for a password)"))
        top.pack_start(self.chk_root, False, False, 0)
        go = Gtk.Button(label=_("Scan"))
        go.connect("clicked", lambda *_a: self.scan(self.entry.get_text()))
        top.pack_start(go, False, False, 0)
        self.btn_stop = Gtk.Button(label=_("■ Stop"), sensitive=False)
        self.btn_stop.connect("clicked", lambda *_a: self.stop_scan())
        top.pack_start(self.btn_stop, False, False, 0)
        self.pack_start(top, False, False, 0)

        self.cur = str(Path.home())
        self.store = Gtk.ListStore(str, str, int, str, bool)  # name, size, percent, path, is_dir
        tv = Gtk.TreeView(model=self.store)
        self.tv = tv
        tv.get_style_context().add_class("sc-nofocus")
        c1 = Gtk.TreeViewColumn(_("Name"), Gtk.CellRendererText(xpad=8, ypad=4), text=0)
        c1.set_expand(True)
        tv.append_column(c1)
        c2 = Gtk.TreeViewColumn(_("Share of folder"), Gtk.CellRendererProgress(xpad=8, ypad=4), value=2, text=1)
        c2.set_min_width(320)
        tv.append_column(c2)
        tv.connect("row-activated", self.on_activate)
        tv.connect("button-press-event", self.on_press)
        tv.get_selection().connect("changed", self.on_sel_changed)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.NONE)
        sw.add(tv)
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.add(sw)
        self.pack_start(frame, True, True, 0)

        acts = Gtk.Box(spacing=6)
        self._act_btns = []
        for label, fn in ((_("Open in file manager"), self.act_open), (_("Copy path"), self.act_copy),
                          (_("Move to trash"), self.act_trash)):
            b = Gtk.Button(label=label, sensitive=False)
            b.connect("clicked", fn)
            acts.pack_start(b, False, False, 0)
            self._act_btns.append(b)
        self.pack_start(acts, False, False, 0)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_no_show_all(True)  # shown only while scanning
        self.pack_start(self.progress, False, False, 0)
        self.status = Gtk.Label(xalign=0, label=_("Press “Scan”. Double-click a folder to enter it."))
        self.pack_start(self.status, False, False, 0)

    def on_activate(self, tv, path, _col):
        row = self.store[path]
        if row[4]:
            self.scan(row[3])

    # ---- actions on the selected item ----
    def _selected(self):
        model, it = self.tv.get_selection().get_selected()
        return (model, it, model[it]) if it else None

    def on_sel_changed(self, *_a):
        on = self.tv.get_selection().get_selected()[1] is not None
        for b in self._act_btns:
            b.set_sensitive(on)

    def on_press(self, tv, ev):
        """Right click: select the row under the pointer and show the same actions as a menu."""
        if ev.button != 3:
            return False
        hit = tv.get_path_at_pos(int(ev.x), int(ev.y))
        if not hit:
            return False
        tv.get_selection().select_path(hit[0])
        menu = Gtk.Menu()
        for label, fn in ((_("Open in file manager"), self.act_open), (_("Copy path"), self.act_copy),
                          (_("Move to trash"), self.act_trash)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", fn)
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(ev)
        return True

    def act_open(self, *_a):
        sel = self._selected()
        if not sel:
            return
        row = sel[2]
        try:
            fileops.open_folder(row[3], row[4])
        except GLib.Error as e:
            self.status.set_text(_("Could not open: {err}").format(err=e.message))

    def act_copy(self, *_a):
        sel = self._selected()
        if not sel:
            return
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(sel[2][3], -1)
        clipboard.store()  # keep the text after the app closes (needs a clipboard manager)
        self.status.set_text(_("Path copied: {path}").format(path=sel[2][3]))

    def act_trash(self, *_a):
        sel = self._selected()
        if not sel:
            return
        model, it, row = sel
        path, name = row[3], os.path.basename(row[3])
        refuse = _("Refusing to trash a system folder: {path}").format(path=path)
        if fileops.is_protected(path):
            self.status.set_text(refuse)
            return
        if _msg(self.get_toplevel(), Gtk.MessageType.QUESTION, _("Move “{name}” to the trash?").format(name=name),
                _("{size} · {path}\nYou can restore it from the trash.").format(size=row[1], path=path),
                Gtk.ButtonsType.OK_CANCEL) != Gtk.ResponseType.OK:
            return
        try:
            fileops.trash(path)
        except PermissionError:
            self.status.set_text(refuse)
        except GLib.Error as e:
            self.status.set_text(_("Could not move to the trash: {err}").format(err=e.message))
        else:
            model.remove(it)
            self._items = [x for x in self._items if x[1] != path]
            self.status.set_text(_("Moved to the trash: {name}").format(name=name))

    # ---- scan control ----
    def scan(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            self.status.set_text(_("Not a folder: {path}").format(path=path))
            return
        self._cancel_running()
        self._gen += 1
        gen = self._gen
        self.cur = path
        self.entry.set_text(path)
        self.store.clear()
        self._items, self._n, self._done, self._cur = [], 0, 0, ""
        self._t0 = time.monotonic()
        self._scanning = True
        self.progress.set_fraction(0.0)
        self.progress.set_text("")
        self.progress.show()
        self.btn_stop.set_sensitive(True)
        self.status.set_text(_("⏳ Scanning… (can take a minute on large filesystems)"))
        GLib.timeout_add_seconds(1, self._tick, gen)
        threading.Thread(target=self._scan, args=(path, self.chk_root.get_active(), gen), daemon=True).start()

    def _cancel_running(self):
        self._gen += 1  # makes the running thread stop at its next line
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()

    def stop_scan(self):
        if not self._scanning:
            return
        self._cancel_running()
        self._scanning = False
        self.progress.hide()
        self.btn_stop.set_sensitive(False)
        self.status.set_text(_("Scan stopped"))

    # ---- worker thread ----
    def _scan(self, path, as_root, gen):
        try:
            proc = diskscan.start(path, as_root)
        except OSError as e:
            GLib.idle_add(self._failed, str(e), gen)
            return
        self._proc = proc
        for line in proc.stdout:
            if gen != self._gen:
                proc.terminate()
                return
            ev = diskscan.parse_line(line)
            if ev is None:
                continue
            if ev[0] == "n":
                GLib.idle_add(self._on_n, ev[1], gen)
            elif ev[0] == "cur":
                GLib.idle_add(self._on_cur, ev[1], gen)
            elif ev[0] == "item":
                GLib.idle_add(self._on_item, ev[1], ev[2], ev[3], gen)
        proc.wait()
        GLib.idle_add(self._finish, path, gen)

    # ---- UI callbacks (main thread) ----
    def _update_progress(self):
        pct = int(100 * self._done / self._n) if self._n else 0
        self.progress.set_fraction(self._done / self._n if self._n else 0.0)
        self.progress.set_text(_("{pct}% · {done}/{n} · {elapsed} · {cur}").format(
            pct=pct, done=self._done, n=self._n, elapsed=fmt_duration(time.monotonic() - self._t0),
            cur=os.path.basename(self._cur.rstrip("/")) or self._cur))

    def _tick(self, gen):
        if gen != self._gen or not self._scanning:
            return False
        self._update_progress()
        return True

    def _on_n(self, n, gen):
        if gen == self._gen:
            self._n = n
            self._update_progress()

    def _on_cur(self, cur, gen):
        if gen == self._gen:
            self._cur = cur
            self._update_progress()

    def _on_item(self, isdir, size, path, gen):
        if gen != self._gen:
            return
        self._items.append((size, path, isdir))
        self._done += 1
        self.store.append([("📁 " if isdir else "📄 ") + os.path.basename(path), fmt_size(size), 0, path, isdir])
        self._update_progress()

    def _finish(self, path, gen):
        if gen != self._gen:
            return
        self._scanning = False
        self.progress.hide()
        self.btn_stop.set_sensitive(False)
        rows = sorted(self._items, reverse=True)[:500]
        total = sum(size for size, _p, _d in self._items)
        self.store.clear()
        for size, pp, isdir in rows:
            pct = int(100 * size / total) if total else 0
            self.store.append([("📁 " if isdir else "📄 ") + os.path.basename(pp), fmt_size(size),
                               min(pct, 100), pp, isdir])
        self.status.set_text(_("{path} — total {total}, items: {n} (this filesystem only, -x)").format(
            path=path, total=fmt_size(total), n=len(self._items)))

    def _failed(self, err, gen):
        if gen == self._gen:
            self._scanning = False
            self.progress.hide()
            self.btn_stop.set_sensitive(False)
            self.status.set_text(_("Failed to start: {err}").format(err=err))


# ───────────────────────── "History" tab ─────────────────────────
class HistoryTab(Gtk.Box):
    """Runs of the cleanup (manual, scheduled, command line) with duration and freed space."""

    def __init__(self, titles: dict):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_border_width(PAD)
        self.titles = titles  # task id -> title, for the tooltip
        self.store = Gtk.ListStore(str, str, str, str, str, str, str)  # when, source, tasks, duration, freed, result, tip
        tv = Gtk.TreeView(model=self.store)
        tv.get_style_context().add_class("sc-nofocus")
        tv.set_tooltip_column(6)
        for i, title in enumerate((_("When"), _("Started by"), _("Tasks"), _("Duration"), _("Freed"), _("Result"))):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(xpad=8, ypad=4), text=i)
            col.set_expand(i == 0)
            tv.append_column(col)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.NONE)
        sw.add(tv)
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.add(sw)
        self.pack_start(frame, True, True, 0)
        self.summary = Gtk.Label(xalign=0)
        self.pack_start(self.summary, False, False, 0)
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_markup("<small>" + GLib.markup_escape_text(
            _("“Freed” is the growth of free space on / during a run, so it is approximate.")) + "</small>")
        self.pack_start(note, False, False, 0)
        bar = Gtk.Box(spacing=6)
        for label, fn in ((_("Refresh"), lambda *_a: self.reload()), (_("Clear history"), self.on_clear)):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            bar.pack_start(b, False, False, 0)
        self.pack_start(bar, False, False, 0)

    @staticmethod
    def _when(ts: str) -> str:
        try:
            return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return ts

    def reload(self):
        records = history.load()
        sources = {"gui": _("Manual"), "schedule": _("Scheduled"), "cli": _("Command line")}
        self.store.clear()
        for r in reversed(records):  # newest first
            result = _("Stopped") if r["stopped"] else (_("Success") if r["ok"] else _("Failed"))
            tip = ", ".join(self.titles.get(i, i) for i in r["tasks"])
            self.store.append([self._when(r["ts"]), sources.get(r["source"], r["source"]), str(len(r["tasks"])),
                               fmt_duration(r["seconds"]), fmt_size(r["freed"]), result, tip])
        if records:
            t = history.totals(records)
            self.summary.set_markup(_("{runs} runs · about {size} freed in total").format(
                runs=t["runs"], size="<b>" + fmt_size(t["freed"]) + "</b>"))
        else:
            self.summary.set_text(_("No runs recorded yet."))

    def on_clear(self, *_a):
        if _msg(self.get_toplevel(), Gtk.MessageType.WARNING, _("Clear the run history?"), _("This cannot be undone."),
                Gtk.ButtonsType.OK_CANCEL) == Gtk.ResponseType.OK:
            history.clear()
            self.reload()


# ───────────────────────── main window ─────────────────────────
class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title=f"SysCleaner {__version__}")
        install_css()
        self.cfg = settings.load()
        self._ws = settings.window_state(self.cfg)  # remembered size / position / maximized / panel split
        self._geom = {k: self._ws[k] for k in ("width", "height", "x", "y") if k in self._ws}
        self._maximized = False
        self._busy = False
        self.set_default_size(self._ws.get("width", 1200), self._ws.get("height", 780))
        if "x" in self._ws and "y" in self._ws and self._position_ok(
                self._ws["x"], self._ws["y"], self._ws.get("width", 1200)):
            self.move(self._ws["x"], self._ws["y"])  # ignored by Wayland compositors, works on X11
        if self._ws.get("maximized"):
            self.maximize()
        self.connect("configure-event", self._on_configure)
        self.connect("window-state-event", self._on_state)
        self.connect("delete-event", self._on_delete)
        self.set_icon_name("syscleaner")
        icon = Path(__file__).resolve().parent.parent / "packaging" / "icons" / "256x256" / "syscleaner.png"
        if icon.exists():  # running from a source checkout
            try:
                self.set_icon_from_file(str(icon))
            except Exception:  # noqa: BLE001
                pass
        self.groups, self.tasks, self.warnings = load()
        self.by_id = {t.id: t for t in self.tasks}
        self.estimates: dict = {}
        self.runner = Runner()
        self.free_before = 0

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_border_width(PAD)
        self.add(outer)
        top = Gtk.Box(spacing=8)
        self.disk_lbl = Gtk.Label(xalign=0)
        top.pack_start(self.disk_lbl, True, True, 0)
        self.about_btn = themed_button(_("About"), "help-about")
        self.about_btn.connect("clicked", self.on_about)
        top.pack_end(self.about_btn, False, False, 0)
        outer.pack_start(top, False, False, 0)
        self.disk_bar = Gtk.ProgressBar()
        outer.pack_start(self.disk_bar, False, False, 0)
        self.nb = Gtk.Notebook()
        self.nb.set_show_border(False)  # the panels below carry their own single frame
        outer.pack_start(self.nb, True, True, 0)
        self.disk_tab = DiskTab()
        self.nb.append_page(self._clean_tab(), Gtk.Label(label=_("🧹 Cleanup")))
        self.nb.append_page(self.disk_tab, Gtk.Label(label=_("📊 Disk")))
        self.history_tab = HistoryTab({t.id: t.title for t in self.tasks})
        self.nb.append_page(self.history_tab, Gtk.Label(label=_("📜 History")))
        self.history_tab.reload()
        self.update_disk()
        self.log.connect("style-updated", self.apply_theme)  # follow light/dark system theme
        self.apply_theme()
        for w in self.warnings:
            self.write(f"⚠ {w}\n", "err")
        if self.cfg.get("check_updates") is True:  # opt-in, switched on in the About dialog
            self.start_update_check()

    # ---- update check at startup (only if the user opted in) ----
    def start_update_check(self):
        cache = self.cfg.get("update_cache")
        if isinstance(cache, dict) and cache.get("latest") and isinstance(cache.get("ts"), (int, float)) \
                and abs(time.time() - cache["ts"]) < 12 * 3600:
            self._apply_update(str(cache["latest"]))  # checked recently: no network needed
            return
        threading.Thread(target=lambda: GLib.idle_add(self._update_done, updater.check(__version__)),
                         daemon=True).start()

    def _update_done(self, res):
        if res["ok"] and res["latest"]:
            self.cfg["update_cache"] = {"ts": time.time(), "latest": res["latest"], "url": res["url"]}
            settings.save(self.cfg)
            self._apply_update(res["latest"])

    def _apply_update(self, latest):
        if updater.is_newer(latest, __version__):
            self.about_btn.set_label(_("About · new version {latest}").format(latest=latest))
            self.about_btn.get_style_context().add_class("suggested-action")
            self.about_btn.set_tooltip_text(_("New version {latest} is available. Open About to download it.").format(
                latest=latest))

    # ---- window state (remembered between runs) ----
    def _position_ok(self, x, y, w) -> bool:
        """True if the saved position still lands on a connected monitor (screens come and go)."""
        try:
            display = Gdk.Display.get_default()
            for i in range(display.get_n_monitors()):
                g = display.get_monitor(i).get_geometry()
                if g.x - w + 120 <= x <= g.x + g.width - 120 and g.y - 10 <= y <= g.y + g.height - 80:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _on_configure(self, *_a):
        if not self._maximized:  # keep the normal (un-maximized) geometry
            w, h = self.get_size()
            x, y = self.get_position()
            self._geom = {"width": w, "height": h, "x": x, "y": y}
        return False

    def _on_state(self, _w, event):
        self._maximized = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
        return False

    def save_window_state(self):
        state = dict(self._geom)
        state["maximized"] = self._maximized
        state["paned"] = self.paned.get_position()
        self.cfg["window"] = state
        settings.save(self.cfg)

    def _on_delete(self, *_a):
        self.save_window_state()
        return False

    def is_busy(self) -> bool:
        return self._busy or self.disk_tab._scanning

    def restart(self):
        """Start a fresh copy (used after changing the language)."""
        self.save_window_state()
        try:
            os.execv(sys.executable, [sys.executable, "-m", "syscleaner"] + sys.argv[1:])
        except OSError as e:
            self.write(_("Failed to start: {err}").format(err=e) + "\n", "err")

    def on_about(self, _b):
        dlg = AboutDialog(self, self.cfg, self.is_busy)
        dlg.show_all()
        resp = dlg.run()
        dlg.destroy()
        if resp == RESTART:
            self.restart()

    # ---- theme ----
    def apply_theme(self, *_a):
        variant = "dark" if is_dark(self.log) else "light"
        if variant == getattr(self, "_variant", None):
            return  # GtkTextTag:foreground is write-only, so remember what we applied
        self._variant = variant
        table = self.log.get_buffer().get_tag_table()
        for name, colour in PALETTE[variant].items():
            tag = table.lookup(name)
            if tag is not None:
                tag.set_property("foreground", colour)

    # ---- cleanup tab ----
    def _clean_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(PAD)
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned = paned
        page.pack_start(paned, True, True, 0)

        # columns: active, markup, id, sensitive, risk, size
        self.store = Gtk.TreeStore(bool, str, str, bool, str, str)
        # tasks that do not apply to this system (missing program / no data) are hidden, empty groups too
        visible = [t for t in self.tasks if available(t) or not t.hide_missing]
        by_group: dict = {}
        for t in visible:
            by_group.setdefault(t.group, []).append(t)
        parents = {}
        for gid, gtitle in self.groups:
            if gid in by_group:
                parents[gid] = self.store.append(
                    None, [False, f"<b>{GLib.markup_escape_text(gtitle)}</b>", "", True, "", ""])
        for t in visible:
            ok = available(t)
            label = GLib.markup_escape_text(t.title) + (" ⏱" if t.schedule else "")
            if t.source:
                label = ("⚠ " if t.root else "") + label + "  <i>(" + _("custom") + ")</i>"
            if not ok:
                why = _("{prog} not found").format(prog=GLib.markup_escape_text(t.requires)) if t.requires \
                    else _("nothing found")
                label += f"  <i>({why})</i>"
            self.store.append(parents[t.group], [t.default and ok, label, t.id, ok, RISK[t.risk], ""])

        tv = Gtk.TreeView(model=self.store)
        tv.get_style_context().add_class("sc-nofocus")
        self.tree = tv
        tv.set_headers_visible(False)
        tv.set_enable_tree_lines(False)
        tg = Gtk.CellRendererToggle(xpad=8, ypad=5)
        tg.connect("toggled", self.on_toggle)
        tv.append_column(Gtk.TreeViewColumn("", tg, active=0, sensitive=3))
        c = Gtk.TreeViewColumn(_("Task"), Gtk.CellRendererText(xpad=6, ypad=5), markup=1, sensitive=3)
        c.set_expand(True)
        tv.append_column(c)
        tv.append_column(Gtk.TreeViewColumn(_("Size"), Gtk.CellRendererText(xalign=1.0, xpad=10, ypad=5), text=5))
        tv.append_column(Gtk.TreeViewColumn(_("Risk"), Gtk.CellRendererText(xpad=10, ypad=5), text=4))
        tv.expand_all()
        tv.get_selection().connect("changed", self.on_select)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.NONE)
        sw.set_min_content_width(580)
        sw.add(tv)
        left_frame = Gtk.Frame()
        left_frame.set_shadow_type(Gtk.ShadowType.IN)
        left_frame.add(sw)
        paned.pack1(left_frame, True, False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.desc = pad(Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True))
        self.desc.set_markup("<i>" + GLib.markup_escape_text(_(
            "Select a task on the left to see its description and command.\n"
            "⏱ means the task can be added to the schedule. “Preview” deletes "
            "nothing and shows a size estimate.")) + "</i>")
        right.pack_start(self.desc, False, False, 0)
        self.total_lbl = pad(Gtk.Label(xalign=0), v=4)
        right.pack_start(self.total_lbl, False, False, 0)
        right.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        self.log = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.log.get_style_context().add_class("sc-nofocus")
        self.log.set_left_margin(PAD)
        self.log.set_right_margin(PAD)
        self.log.set_top_margin(PAD)
        self.log.set_bottom_margin(PAD)
        buf = self.log.get_buffer()
        buf.create_tag("head", weight=Pango.Weight.BOLD)
        buf.create_tag("err")
        buf.create_tag("ok")
        buf.create_mark("end", buf.get_end_iter(), False)
        lsw = Gtk.ScrolledWindow()
        lsw.set_shadow_type(Gtk.ShadowType.NONE)
        lsw.add(self.log)
        right.pack_start(lsw, True, True, 0)
        right_frame = Gtk.Frame()  # same frame as the task list, so top and bottom edges line up
        right_frame.set_shadow_type(Gtk.ShadowType.IN)
        right_frame.add(right)
        paned.pack2(right_frame, True, False)
        paned.set_position(self._ws.get("paned", 620))

        self._run = {"gen": 0, "active": False, "t0": 0.0, "idx": 0, "total": 0, "title": ""}
        self.run_bar = Gtk.ProgressBar(show_text=True)
        self.run_bar.set_no_show_all(True)  # shown only while tasks run
        page.pack_start(self.run_bar, False, False, 0)

        bar = Gtk.Box(spacing=8)
        for text, fn in ((_("Safe only"), self.sel_safe), (_("Select all"), self.sel_all),
                         (_("Select none"), self.sel_none),
                         (_("Clear log"), lambda *_a: buf.set_text(""))):
            b = Gtk.Button(label=text)
            b.connect("clicked", fn)
            bar.pack_start(b, False, False, 0)
        self.btn_sched = Gtk.Button(label=_("⏱ Schedule…"))
        self.btn_sched.connect("clicked", self.on_schedule)
        self.btn_dry = Gtk.Button(label=_("🔍 Preview"))
        self.btn_dry.connect("clicked", lambda *_a: self.start(True))
        self.btn_run = Gtk.Button(label=_("▶ Run selected"))
        self.btn_run.get_style_context().add_class("suggested-action")
        self.btn_run.connect("clicked", lambda *_a: self.start(False))
        self.btn_stop = Gtk.Button(label=_("■ Stop"), sensitive=False)
        self.btn_stop.connect("clicked", lambda *_a: self.runner.stop())
        for b in (self.btn_run, self.btn_dry, self.btn_sched):
            bar.pack_end(b, False, False, 0)
        bar.pack_end(self.btn_stop, False, False, 0)
        page.pack_start(bar, False, False, 0)
        return page

    # ---- helpers ----
    def update_disk(self):
        u = shutil.disk_usage("/")
        self.disk_lbl.set_markup(_("Disk <b>/</b>: used <b>{used:.1f}</b> GB of {total:.1f}, "
                                   "free <b>{free:.1f}</b> GB").format(
            used=u.used / 2**30, total=u.total / 2**30, free=u.free / 2**30))
        self.disk_bar.set_fraction(u.used / u.total)
        return u.free

    def write(self, text, tag=None):
        buf = self.log.get_buffer()
        if tag is None:
            if ERR_RE.search(text):
                tag = "err"
            elif text.startswith("▶") or text.startswith("==="):
                tag = "head"
        if tag:
            buf.insert_with_tags_by_name(buf.get_end_iter(), text, tag)
        else:
            buf.insert(buf.get_end_iter(), text)
        mark = buf.get_mark("end")
        buf.move_mark(mark, buf.get_end_iter())
        self.log.scroll_mark_onscreen(mark)

    def sel_ids(self):
        return [ch[2] for grp in self.store for ch in grp.iterchildren() if ch[0] and ch[3]]

    def on_toggle(self, _r, path):
        row = self.store[path]
        if not row[3]:
            return
        row[0] = not row[0]
        if row[2] == "":  # group row: toggle all children
            for ch in row.iterchildren():
                if ch[3]:
                    ch[0] = row[0]
        self.update_total()

    def on_select(self, sel):
        model, it = sel.get_selected()
        if not it or not model[it][2]:
            return
        t = self.by_id[model[it][2]]
        esc = GLib.markup_escape_text
        extra = ""
        if t.preview or t.estimate:
            extra = "\n\n<small>" + _("Preview uses:") + " " + esc((t.estimate or t.preview).splitlines()[0]) + "</small>"
        root = _("needs root (asks for a password)") if t.root else _("no root needed")
        sched = "  ·  " + _("can be scheduled ⏱") if t.schedule else ""
        own = "\n" + esc(_("Custom task from {file}").format(file=t.source)) if t.source else ""
        self.desc.set_markup(
            f"<big><b>{esc(t.title)}</b></big>\n"
            f"{esc(_('Risk:'))} {esc(RISK[t.risk])}  ·  {esc(root)}{esc(sched)}{own}\n\n"
            f"{esc(t.desc)}\n\n<tt>{esc(('sudo ' if t.root else '') + t.cmd)}</tt>{extra}")

    def sel_safe(self, *_a):
        for grp in self.store:
            grp[0] = False
            for ch in grp.iterchildren():
                t = self.by_id[ch[2]]
                ch[0] = ch[3] and t.risk == "safe" and t.group not in READONLY_GROUPS
        self.update_total()

    def sel_all(self, *_a):
        for grp in self.store:
            grp[0] = True
            for ch in grp.iterchildren():
                ch[0] = bool(ch[3])  # every task that is available on this system
        self.update_total()

    def sel_none(self, *_a):
        for grp in self.store:
            grp[0] = False
            for ch in grp.iterchildren():
                ch[0] = False
        self.update_total()

    def update_total(self):
        if not self.estimates:
            self.total_lbl.set_text("")
            return
        tot = sum(self.estimates[i] for i in self.sel_ids() if self.estimates.get(i))
        self.total_lbl.set_markup(_("Estimated to free for the selection: <b>{size}</b> (approximate)").format(
            size=fmt_size(tot)))

    def refresh_sizes(self):
        for grp in self.store:
            s, have = 0, False
            for ch in grp.iterchildren():
                if ch[2] in self.estimates:
                    v = self.estimates[ch[2]]
                    ch[5] = _("n/a") if v is None else fmt_size(v)
                    if v:
                        s += v
                        have = True
                else:
                    ch[5] = ""
            grp[5] = fmt_size(s) if have else ""
        self.update_total()

    def set_busy(self, busy):
        self._busy = busy
        for b in (self.btn_run, self.btn_dry, self.btn_sched):
            b.set_sensitive(not busy)
        self.btn_stop.set_sensitive(busy)

    # ---- run / preview ----
    def handle_line(self, line):
        b = BEGIN_RE.match(line)
        if b:
            GLib.idle_add(self._on_begin, int(b.group(1)), int(b.group(2)), b.group(3))
            return
        m = EST_RE.match(line)
        if m:
            v = None if m.group(2) == "-" else int(m.group(2))
            GLib.idle_add(self._set_est, m.group(1), v)
        else:
            GLib.idle_add(self.write, line + "\n")

    # ---- run progress bar ----
    def _on_begin(self, idx, total, tid):
        t = self.by_id.get(tid)
        self._run.update(idx=idx, total=total, title=t.title if t else tid)
        self._update_run_bar()

    def _update_run_bar(self):
        r = self._run
        done = max(r["idx"] - 1, 0)
        frac = done / r["total"] if r["total"] else 0.0
        self.run_bar.set_fraction(frac)
        self.run_bar.set_text(_("{pct}% · {idx}/{total} · {elapsed} · {title}").format(
            pct=int(100 * frac), idx=r["idx"], total=r["total"],
            elapsed=fmt_duration(time.monotonic() - r["t0"]), title=r["title"] or _("starting…")))

    def _tick_run(self, gen):
        if gen != self._run["gen"] or not self._run["active"]:
            return False
        self._update_run_bar()
        return True

    def _set_est(self, tid, v):
        self.estimates[tid] = v
        self.write("   " + _("estimate: {size}").format(size=_("n/a") if v is None else fmt_size(v)) + "\n", "ok")

    def start(self, dry):
        ids = self.sel_ids()
        if not ids:
            _msg(self, Gtk.MessageType.INFO, _("Nothing selected"))
            return
        tasks = [self.by_id[i] for i in ids]
        custom_root = [t for t in tasks if t.source and t.root]
        if (not dry or custom_root) and not self.confirm_run(tasks, dry):
            return
        self.set_busy(True)
        self.runner.stopped = False
        self.free_before = self.update_disk()
        gen = self._run["gen"] + 1
        self._run = {"gen": gen, "active": True, "t0": time.monotonic(), "idx": 0, "total": len(tasks), "title": "",
                     "ids": [t.id for t in tasks]}
        self._rc_bad = False
        self.run_bar.set_fraction(0.0)
        self._update_run_bar()
        self.run_bar.show()
        GLib.timeout_add_seconds(1, self._tick_run, gen)
        head = _("PREVIEW (nothing is deleted)") if dry else _("RUN")
        self.write(f"\n=== {head} · {datetime.now():%H:%M:%S} ===\n", "head")
        threading.Thread(target=self.worker, args=(tasks, dry), daemon=True).start()

    def confirm_run(self, tasks, dry) -> bool:
        """The last question before anything runs: size estimate, dangerous and own root tasks."""
        risky = [t for t in tasks if t.risk == "danger"] if not dry else []
        custom_root = [t for t in tasks if t.source and t.root]
        lines = []
        if not dry:
            known = [self.estimates.get(t.id) for t in tasks]
            if any(known):
                lines.append(_("Estimated to free about {size} (from the last preview).").format(
                    size=fmt_size(sum(v or 0 for v in known))))
            else:
                lines.append(_("No size estimate yet. Tip: run “Preview” first."))
        if any(t.root for t in tasks):
            lines.append(_("Tasks that need root will ask for your password once."))
        if risky:
            lines.append(_("Dangerous tasks:") + "\n" + "\n".join("  • " + t.title for t in risky))
        if custom_root:
            lines.append(_("Your own tasks that run as root (full access to the system):") + "\n" + "\n".join(
                f"  • {t.title} ({t.source})" for t in custom_root))
            lines.append(_("Run them only if you wrote or trust them."))
        careful = bool(risky or custom_root)
        title = (_("The preview will run your own tasks as root. Continue?") if dry
                 else _("Run the selected tasks? ({n})").format(n=len(tasks)))
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.NONE, text=title,
                                message_type=Gtk.MessageType.WARNING if careful else Gtk.MessageType.QUESTION)
        dlg.format_secondary_text("\n\n".join(lines))
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        go = dlg.add_button(_("Continue") if dry else _("Run"), Gtk.ResponseType.OK)
        go.get_style_context().add_class("destructive-action" if careful else "suggested-action")
        dlg.set_default_response(Gtk.ResponseType.CANCEL if careful else Gtk.ResponseType.OK)
        resp = dlg.run()
        dlg.destroy()
        return resp == Gtk.ResponseType.OK

    def worker(self, tasks, dry):
        try:
            rt = [t for t in tasks if t.root]
            ut = [t for t in tasks if not t.root]
            if rt:
                GLib.idle_add(self.write, "━━ " + _("root tasks (single password prompt)") + " ━━\n", "head")
                rc = self.runner.stream(["pkexec", "bash", "-c", build_script(rt, dry, 0, len(tasks))], self.handle_line)
                self._rc_bad = self._rc_bad or rc != 0
                GLib.idle_add(self.write, _("[exit code: {rc}]").format(rc=rc) + "\n", "ok" if rc == 0 else "err")
            if ut and not self.runner.stopped:
                GLib.idle_add(self.write, "━━ " + _("user tasks") + " ━━\n", "head")
                rc = self.runner.stream(["bash", "-c", build_script(ut, dry, len(rt), len(tasks))], self.handle_line)
                self._rc_bad = self._rc_bad or rc != 0
                GLib.idle_add(self.write, _("[exit code: {rc}]").format(rc=rc) + "\n", "ok" if rc == 0 else "err")
        except Exception as e:  # noqa: BLE001
            GLib.idle_add(self.write, _("Failed to start: {err}").format(err=e) + "\n", "err")
        finally:
            GLib.idle_add(self.finish, dry)

    def finish(self, dry):
        free = self.update_disk()
        took = fmt_duration(time.monotonic() - self._run["t0"])
        self._run["active"] = False
        self.run_bar.hide()
        if dry:
            self.refresh_sizes()
            tot = sum(self.estimates.get(i) or 0 for i in self.sel_ids())
            self.write("\n" + _("✔ Preview finished. Can free ≈ {size} · {elapsed}").format(
                size=fmt_size(tot), elapsed=took) + "\n", "ok")
        else:
            freed = max(0, free - self.free_before)
            self.write("\n" + _("✔ Done. Free space increased by {size} · {elapsed}").format(
                size=fmt_size(freed), elapsed=took) + "\n", "ok")
            history.add(history.make_record("gui", self._run.get("ids", []), freed,
                                            time.monotonic() - self._run["t0"], not self._rc_bad,
                                            self.runner.stopped))
            self.history_tab.reload()
            self.estimates.clear()
            self.refresh_sizes()
        self.set_busy(False)

    # ---- schedule ----
    def on_schedule(self, _b):
        ids = [i for i in self.sel_ids() if self.by_id[i].schedule]
        dlg = Gtk.Dialog(title=_("Cleanup schedule (systemd timer)"), transient_for=self, modal=True)
        dlg.add_button(_("Close"), Gtk.ResponseType.CLOSE)
        dlg.add_button(_("Disable schedule"), 2)
        dlg.add_button(_("Enable / update"), 1)
        run_now = dlg.add_button(_("Run now"), 3)
        run_now.set_sensitive(schedule.is_installed())
        area = dlg.get_content_area()
        area.set_spacing(10)
        area.set_border_width(PAD + 4)
        area.pack_start(Gtk.Label(xalign=0, label=_("Status: {status}").format(status=schedule.status())),
                        False, False, 0)
        area.pack_start(Gtk.Label(xalign=0, label=schedule.last_run_text()), False, False, 0)
        names = "\n".join("  • " + self.by_id[i].title for i in ids) or "  " + _(
            "(none — check tasks marked with ⏱ in the list)")
        area.pack_start(Gtk.Label(xalign=0, label=_("Checked tasks marked with ⏱ will run:") + "\n" + names),
                        False, False, 0)
        combo = Gtk.ComboBoxText()
        for name in schedule.FREQ_NAMES:
            combo.append_text(name)
        combo.set_active(1)
        row = Gtk.Box(spacing=8)
        row.pack_start(Gtk.Label(label=_("Frequency:")), False, False, 0)
        row.pack_start(combo, False, False, 0)
        row.pack_start(Gtk.Label(label=_("time (HH:MM):")), False, False, 0)
        tm = Gtk.Entry(text="04:30", width_chars=6)
        row.pack_start(tm, False, False, 0)
        area.pack_start(row, False, False, 0)
        area.pack_start(Gtk.Label(xalign=0, wrap=True, label=_(
            "Runs as root via systemd with low priority; logs: journalctl -u syscleaner. "
            "Dangerous tasks are never scheduled.")), False, False, 0)
        dlg.show_all()
        resp = dlg.run()
        idx, hhmm = combo.get_active(), tm.get_text().strip()
        dlg.destroy()
        if resp == 1:
            if not ids:
                _msg(self, Gtk.MessageType.INFO, _("No schedulable tasks selected"))
                return
            if not schedule.TIME_RE.match(hhmm):
                _msg(self, Gtk.MessageType.ERROR, _("Time must be in HH:MM format"))
                return
            user = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
            freq = list(schedule.FREQS)[idx]
            self.run_root_script(schedule.install_script(ids, freq, hhmm.zfill(5), user), _("Enabling schedule"))
        elif resp == 2:
            self.run_root_script(schedule.uninstall_script(), _("Disabling schedule"))
        elif resp == 3:
            self.run_root_script(schedule.run_now_script(), _("Running the schedule now"))

    def run_root_script(self, script, title):
        self.set_busy(True)
        self.runner.stopped = False
        self.write(f"\n=== {title} ===\n", "head")

        def w():
            try:
                rc = self.runner.stream(["pkexec", "bash", "-c", script], self.handle_line)
                GLib.idle_add(self.write, _("[exit code: {rc}]").format(rc=rc) + "\n", "ok" if rc == 0 else "err")
            finally:
                GLib.idle_add(self.set_busy, False)
        threading.Thread(target=w, daemon=True).start()


def run():
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
