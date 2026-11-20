"""GTK3 user interface for SysCleaner."""
from __future__ import annotations

import os
import pwd
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from . import __version__, schedule  # noqa: E402
from .i18n import _  # noqa: E402
from .runner import EST_RE, Runner, build_script, fmt_size  # noqa: E402
from .tasks import available, load  # noqa: E402

RISK = {"safe": _("🟢 safe"), "caution": _("🟡 caution"), "danger": _("🔴 dangerous")}
ERR_RE = re.compile(r"(?i)(\berror\b|\bfailed\b|permission denied|^E: )")

# Log colours per theme variant (picked automatically from the system GTK theme).
PALETTE = {
    "dark": {"head": "#6cb4ff", "err": "#ff7b72", "ok": "#5fd38d"},
    "light": {"head": "#1a5fb4", "err": "#c01c28", "ok": "#26a269"},
}
PAD = 12  # base spacing in pixels


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
    """ncdu-like browser: double-click enters a folder, the bar shows the share of the parent."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_border_width(PAD)
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
        self.pack_start(top, False, False, 0)

        self.cur = str(Path.home())
        self.store = Gtk.ListStore(str, str, int, str, bool)  # name, size, percent, path, is_dir
        tv = Gtk.TreeView(model=self.store)
        c1 = Gtk.TreeViewColumn(_("Name"), Gtk.CellRendererText(xpad=8, ypad=4), text=0)
        c1.set_expand(True)
        tv.append_column(c1)
        c2 = Gtk.TreeViewColumn(_("Share of folder"), Gtk.CellRendererProgress(xpad=8, ypad=4), value=2, text=1)
        c2.set_min_width(320)
        tv.append_column(c2)
        tv.connect("row-activated", self.on_activate)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(tv)
        self.pack_start(sw, True, True, 0)
        self.status = Gtk.Label(xalign=0, label=_("Press “Scan”. Double-click a folder to enter it."))
        self.pack_start(self.status, False, False, 0)

    def on_activate(self, tv, path, _col):
        row = self.store[path]
        if row[4]:
            self.scan(row[3])

    def scan(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            self.status.set_text(_("Not a folder: {path}").format(path=path))
            return
        self.cur = path
        self.entry.set_text(path)
        self.store.clear()
        self.status.set_text(_("⏳ Scanning… (can take a minute on large filesystems)"))
        threading.Thread(target=self._scan, args=(path, self.chk_root.get_active()), daemon=True).start()

    def _scan(self, path, as_root):
        argv = ["du", "-xa", "-B1", "--max-depth=1", path]
        if as_root:
            argv.insert(0, "pkexec")
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace")
        rows, total = [], 0
        for line in p.stdout.splitlines():
            try:
                size, pp = line.split("\t", 1)
                size = int(size)
            except ValueError:
                continue
            if pp == path:
                total = size
            else:
                rows.append((size, pp))
        rows.sort(reverse=True)
        out = [(size, pp, os.path.isdir(pp) and not os.path.islink(pp)) for size, pp in rows[:500]]
        GLib.idle_add(self._fill, path, total, out)

    def _fill(self, path, total, rows):
        if path != self.cur:
            return
        for size, pp, isdir in rows:
            pct = int(100 * size / total) if total else 0
            self.store.append([("📁 " if isdir else "📄 ") + os.path.basename(pp), fmt_size(size),
                               min(pct, 100), pp, isdir])
        self.status.set_text(_("{path} — total {total}, items: {n} (this filesystem only, -x)").format(
            path=path, total=fmt_size(total), n=len(rows)))


# ───────────────────────── main window ─────────────────────────
class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title=f"SysCleaner {__version__}")
        self.set_default_size(1200, 780)
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
        self.disk_lbl = Gtk.Label(xalign=0)
        self.disk_bar = Gtk.ProgressBar()
        outer.pack_start(self.disk_lbl, False, False, 0)
        outer.pack_start(self.disk_bar, False, False, 0)
        self.nb = Gtk.Notebook()
        outer.pack_start(self.nb, True, True, 0)
        self.disk_tab = DiskTab()
        self.nb.append_page(self._clean_tab(), Gtk.Label(label=_("🧹 Cleanup")))
        self.nb.append_page(self.disk_tab, Gtk.Label(label=_("📊 Disk")))
        self.update_disk()
        self.log.connect("style-updated", self.apply_theme)  # follow light/dark system theme
        self.apply_theme()
        for w in self.warnings:
            self.write(f"⚠ {w}\n", "err")

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
        page.pack_start(paned, True, True, 0)

        # columns: active, markup, id, sensitive, risk, size
        self.store = Gtk.TreeStore(bool, str, str, bool, str, str)
        parents = {}
        for gid, gtitle in self.groups:
            parents[gid] = self.store.append(None, [False, f"<b>{GLib.markup_escape_text(gtitle)}</b>", "", True, "", ""])
        for t in self.tasks:
            ok = available(t)
            label = GLib.markup_escape_text(t.title) + (" ⏱" if t.schedule else "")
            if not ok:
                label += "  <i>(" + _("{prog} not found").format(prog=GLib.markup_escape_text(t.requires)) + ")</i>"
            self.store.append(parents[t.group], [t.default and ok, label, t.id, ok, RISK[t.risk], ""])

        tv = Gtk.TreeView(model=self.store)
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
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_min_content_width(580)
        sw.add(tv)
        paned.pack1(sw, True, False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.desc = pad(Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True))
        self.desc.set_markup("<i>" + GLib.markup_escape_text(_(
            "Select a task on the left to see its description and command.\n"
            "⏱ means the task can be added to the schedule. “Preview” deletes "
            "nothing and shows a size estimate.")) + "</i>")
        right.pack_start(self.desc, False, False, 0)
        self.total_lbl = pad(Gtk.Label(xalign=0), v=4)
        right.pack_start(self.total_lbl, False, False, 0)
        self.log = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
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
        lsw.set_shadow_type(Gtk.ShadowType.IN)
        lsw.add(self.log)
        right.pack_start(lsw, True, True, 0)
        paned.pack2(right, True, False)
        paned.set_position(620)

        bar = Gtk.Box(spacing=8)
        for text, fn in ((_("Safe only"), self.sel_safe), (_("Select none"), self.sel_none),
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
        self.desc.set_markup(
            f"<big><b>{esc(t.title)}</b></big>\n"
            f"{esc(_('Risk:'))} {esc(RISK[t.risk])}  ·  {esc(root)}{esc(sched)}\n\n"
            f"{esc(t.desc)}\n\n<tt>{esc(('sudo ' if t.root else '') + t.cmd)}</tt>{extra}")

    def sel_safe(self, *_a):
        for grp in self.store:
            grp[0] = False
            for ch in grp.iterchildren():
                t = self.by_id[ch[2]]
                ch[0] = ch[3] and t.risk == "safe" and t.group == "clean"
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
        for b in (self.btn_run, self.btn_dry, self.btn_sched):
            b.set_sensitive(not busy)
        self.btn_stop.set_sensitive(busy)

    # ---- run / preview ----
    def handle_line(self, line):
        m = EST_RE.match(line)
        if m:
            v = None if m.group(2) == "-" else int(m.group(2))
            GLib.idle_add(self._set_est, m.group(1), v)
        else:
            GLib.idle_add(self.write, line + "\n")

    def _set_est(self, tid, v):
        self.estimates[tid] = v
        self.write("   " + _("estimate: {size}").format(size=_("n/a") if v is None else fmt_size(v)) + "\n", "ok")

    def start(self, dry):
        ids = self.sel_ids()
        if not ids:
            _msg(self, Gtk.MessageType.INFO, _("Nothing selected"))
            return
        tasks = [self.by_id[i] for i in ids]
        risky = [t for t in tasks if t.risk == "danger"]
        if risky and not dry:
            r = _msg(self, Gtk.MessageType.WARNING, _("Dangerous tasks selected"),
                     "\n".join("• " + t.title for t in risky) + "\n\n" + _("Run “Preview” first. Continue anyway?"),
                     Gtk.ButtonsType.OK_CANCEL)
            if r != Gtk.ResponseType.OK:
                return
        self.set_busy(True)
        self.runner.stopped = False
        self.free_before = self.update_disk()
        head = _("PREVIEW (nothing is deleted)") if dry else _("RUN")
        self.write(f"\n=== {head} · {datetime.now():%H:%M:%S} ===\n", "head")
        threading.Thread(target=self.worker, args=(tasks, dry), daemon=True).start()

    def worker(self, tasks, dry):
        try:
            rt = [t for t in tasks if t.root]
            ut = [t for t in tasks if not t.root]
            if rt:
                GLib.idle_add(self.write, "━━ " + _("root tasks (single password prompt)") + " ━━\n", "head")
                rc = self.runner.stream(["pkexec", "bash", "-c", build_script(rt, dry)], self.handle_line)
                GLib.idle_add(self.write, _("[exit code: {rc}]").format(rc=rc) + "\n", "ok" if rc == 0 else "err")
            if ut and not self.runner.stopped:
                GLib.idle_add(self.write, "━━ " + _("user tasks") + " ━━\n", "head")
                rc = self.runner.stream(["bash", "-c", build_script(ut, dry)], self.handle_line)
                GLib.idle_add(self.write, _("[exit code: {rc}]").format(rc=rc) + "\n", "ok" if rc == 0 else "err")
        except Exception as e:  # noqa: BLE001
            GLib.idle_add(self.write, _("Failed to start: {err}").format(err=e) + "\n", "err")
        finally:
            GLib.idle_add(self.finish, dry)

    def finish(self, dry):
        free = self.update_disk()
        if dry:
            self.refresh_sizes()
            tot = sum(self.estimates.get(i) or 0 for i in self.sel_ids())
            self.write("\n" + _("✔ Preview finished. Can free ≈ {size}").format(size=fmt_size(tot)) + "\n", "ok")
        else:
            self.write("\n" + _("✔ Done. Free space increased by {size}").format(
                size=fmt_size(max(0, free - self.free_before))) + "\n", "ok")
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
        area = dlg.get_content_area()
        area.set_spacing(10)
        area.set_border_width(PAD + 4)
        area.pack_start(Gtk.Label(xalign=0, label=_("Status: {status}").format(status=schedule.status())),
                        False, False, 0)
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
