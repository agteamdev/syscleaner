"""About dialog: version, update check, project links, support and preferences (language, auto-check)."""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import __version__, links, settings, updater  # noqa: E402
from .i18n import _, available_languages  # noqa: E402

RESTART = 100  # dialog response meaning "restart the application"
PAD = 12


def short_url(url: str) -> str:
    """'https://github.com/agteamdev/syscleaner/' -> 'github.com/agteamdev/syscleaner' (shown beside a link)."""
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def open_url(url: str):
    """Open a link in the default browser. Returns None on success, otherwise the error text."""
    try:
        Gio.AppInfo.launch_default_for_uri(url, None)
    except GLib.Error as e:
        return e.message
    return None


def update_icon(res: dict) -> str:
    if not res["ok"]:
        return "❗"
    if res["latest"] is None:
        return "🔎"
    return "🆕" if res["newer"] else "✅"


def update_message(res: dict, current: str):
    """Turn an updater.check() result into (text, link_url or None, link_label or None)."""
    if not res["ok"]:
        code = res["error"]
        reasons = {"offline": _("no connection"),
                   "rate_limit": _("GitHub rate limit reached, try again later"),
                   "bad_response": _("unexpected response")}
        reason = reasons.get(code) or code.replace("http_", "HTTP ")
        return _("Could not check for updates ({reason}).").format(reason=reason), None, None
    if res["latest"] is None:
        return _("No published releases found yet."), None, None
    if res["newer"]:
        text = _("New version available: {latest} (you have {current}).").format(
            latest=res["latest"], current=current)
        return text, res["url"], _("Open the release page")
    return _("You have the latest version ({current}).").format(current=current), None, None


# ---------- small building blocks: titled cards ("boxed lists") ----------
def _heading(text: str):
    lbl = Gtk.Label(xalign=0)
    lbl.set_markup("<b>" + GLib.markup_escape_text(text) + "</b>")
    lbl.set_margin_top(6)
    return lbl


def _padded(child, h=PAD, v=8):
    child.set_margin_start(h)
    child.set_margin_end(h)
    child.set_margin_top(v)
    child.set_margin_bottom(v)
    return child


def _card(rows):
    """A framed column of rows separated by thin lines."""
    frame = Gtk.Frame()
    frame.set_shadow_type(Gtk.ShadowType.IN)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    for i, row in enumerate(rows):
        if i:
            col.pack_start(Gtk.Separator(), False, False, 0)
        col.pack_start(row, False, False, 0)
    frame.add(col)
    return frame


def _dim(label, opacity=0.65):
    label.set_opacity(opacity)
    return label


class AboutDialog(Gtk.Dialog):
    def __init__(self, parent, cfg: dict, is_busy):
        super().__init__(title=_("About SysCleaner"), transient_for=parent, modal=True)
        self.cfg, self.is_busy = cfg, is_busy
        self._alive = True
        self._release_url = None
        self.set_default_size(580, -1)
        self.connect("destroy", lambda *_a: setattr(self, "_alive", False))
        self.add_button(_("Close"), Gtk.ResponseType.CLOSE)
        area = self.get_content_area()
        area.set_spacing(8)
        area.set_border_width(PAD + 8)

        # --- header: icon, name, version -----------------------------------
        head = Gtk.Box(spacing=18)
        icon = Path(__file__).resolve().parent.parent / "packaging" / "icons" / "128x128" / "syscleaner.png"
        img = (Gtk.Image.new_from_file(str(icon)) if icon.exists()
               else Gtk.Image.new_from_icon_name("syscleaner", Gtk.IconSize.DIALOG))
        head.pack_start(img, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title = Gtk.Label(xalign=0)
        title.set_markup('<span size="xx-large" weight="bold">SysCleaner</span>')
        names.pack_start(title, False, False, 0)
        version = Gtk.Label(xalign=0)
        version.set_markup("<b>" + GLib.markup_escape_text(_("Version {version}").format(version=__version__)) + "</b>")
        names.pack_start(version, False, False, 0)
        names.pack_start(Gtk.Label(xalign=0, wrap=True,
                                   label=_("Cleanup and diagnostics for Linux Mint / Debian / Ubuntu")), False, False, 0)
        names.pack_start(_dim(Gtk.Label(xalign=0, label=_("MIT license · © AG TEAM DEV"))), False, False, 0)
        head.pack_start(names, True, True, 0)
        area.pack_start(head, False, False, 4)

        # --- updates ---------------------------------------------------------
        area.pack_start(_heading(_("Updates")), False, False, 0)
        top = Gtk.Box(spacing=10)
        self.upd_icon = Gtk.Label(label="⏳")
        top.pack_start(self.upd_icon, False, False, 0)
        self.upd_lbl = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.upd_lbl.set_max_width_chars(46)
        top.pack_start(self.upd_lbl, True, True, 0)
        self.upd_open = Gtk.Button(label=_("Open the release page"))
        self.upd_open.get_style_context().add_class("suggested-action")
        self.upd_open.set_no_show_all(True)
        self.upd_open.connect("clicked", lambda *_a: self._release_url and self.open_link(self._release_url))
        top.pack_start(self.upd_open, False, False, 0)
        self.upd_btn = Gtk.Button(label=_("Check again"))
        self.upd_btn.connect("clicked", lambda *_a: self.check_updates())
        top.pack_start(self.upd_btn, False, False, 0)
        upd = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        upd.pack_start(top, False, False, 0)
        self.apt_hint = _dim(Gtk.Label(xalign=0, wrap=True, selectable=True, label=_(
            "Installed via APT? Update with: sudo apt update && sudo apt upgrade")), 0.75)
        self.apt_hint.set_no_show_all(True)
        upd.pack_start(self.apt_hint, False, False, 0)
        area.pack_start(_card([_padded(upd)]), False, False, 0)

        # --- project links ---------------------------------------------------
        area.pack_start(_heading(_("Project")), False, False, 0)
        area.pack_start(_card([
            self._link_row("🌐", _("Website"), links.REPO_URL),
            self._link_row("🐞", _("Report an issue"), links.ISSUES_URL),
            self._link_row("🔖", _("All releases"), links.RELEASES_URL),
            self._link_row("📦", _("APT repository"), links.APT_URL),
        ]), False, False, 0)

        # --- support ---------------------------------------------------------
        area.pack_start(_heading(_("Support the project")), False, False, 0)
        area.pack_start(_dim(Gtk.Label(xalign=0, wrap=True, label=_(
            "SysCleaner is free and open source. If it saved you time, you can support its development:")), 0.8),
            False, False, 0)
        area.pack_start(_card([
            self._link_row("💖", "Patreon", links.PATREON_URL),
            self._link_row("💳", _("Donate (NOWPayments)"), links.DONATE_URL),
        ]), False, False, 0)

        # --- preferences -----------------------------------------------------
        area.pack_start(_heading(_("Preferences")), False, False, 0)
        self.auto = Gtk.CheckButton(label=_("Check for updates automatically at startup"))
        self.auto.set_tooltip_text(_("Contacts api.github.com at most every 12 hours. Only the app name and version are sent."))
        self.auto.set_active(bool(cfg.get("check_updates")))
        self.auto.connect("toggled", self.on_auto)
        lang = Gtk.Box(spacing=10)
        lang.pack_start(Gtk.Label(label=_("Language:")), False, False, 0)
        self.combo = Gtk.ComboBoxText()
        self.combo.append("auto", _("System default"))
        for code, name in available_languages():
            self.combo.append(code, name)
        self.initial = str(cfg.get("language") or "auto")
        if not self.combo.set_active_id(self.initial):
            self.combo.set_active_id("auto")
        self.combo.connect("changed", self.on_language)
        lang.pack_start(self.combo, True, True, 0)
        self.restart_btn = Gtk.Button(label=_("Restart now"))
        self.restart_btn.set_no_show_all(True)
        self.restart_btn.connect("clicked", self.on_restart)
        lang.pack_start(self.restart_btn, False, False, 0)
        langbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        langbox.pack_start(lang, False, False, 0)
        self.note = _dim(Gtk.Label(xalign=0, wrap=True), 0.8)
        self.note.set_no_show_all(True)
        langbox.pack_start(self.note, False, False, 0)
        if os.environ.get("SYSCLEANER_LANG"):
            langbox.pack_start(_dim(Gtk.Label(xalign=0, wrap=True, label=_(
                "The SYSCLEANER_LANG environment variable is set and overrides this choice.")), 0.8), False, False, 0)
        area.pack_start(_card([_padded(self.auto), _padded(langbox)]), False, False, 0)

        self.msg = _dim(Gtk.Label(xalign=0, wrap=True), 0.85)  # transient messages (a link that would not open)
        self.msg.set_no_show_all(True)
        area.pack_start(self.msg, False, False, 0)

        self.check_updates()

    # ---- rows and links ----
    def _link_row(self, emoji, title, url):
        """One clickable row: icon, title and the address in a dim colour on the right."""
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_tooltip_text(url)
        row = Gtk.Box(spacing=12)
        row.set_border_width(6)
        row.pack_start(Gtk.Label(label=emoji), False, False, 0)
        row.pack_start(Gtk.Label(label=title, xalign=0), True, True, 0)
        row.pack_end(_dim(Gtk.Label(label=short_url(url), xalign=1)), False, False, 0)
        btn.add(row)
        btn.connect("clicked", lambda *_a: self.open_link(url))
        return btn

    def open_link(self, url):
        err = open_url(url)
        self.msg.set_text(_("Could not open: {err}").format(err=err) if err else "")
        self.msg.set_visible(bool(err))

    # ---- update check ----
    def check_updates(self):
        self.upd_btn.set_sensitive(False)
        self.upd_open.hide()
        self.apt_hint.hide()
        self.upd_icon.set_text("⏳")
        self.upd_lbl.set_text(_("Checking for updates…"))
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        GLib.idle_add(self._show, updater.check(__version__))

    def _show(self, res):
        if not self._alive:
            return
        if res["ok"] and res["latest"]:  # keep the startup check in sync with what the user just saw
            self.cfg["update_cache"] = {"ts": time.time(), "latest": res["latest"], "url": res["url"]}
            settings.save(self.cfg)
        text, url, label = update_message(res, __version__)
        self.upd_icon.set_text(update_icon(res))
        self.upd_lbl.set_text(text)
        self._release_url = url
        if url:
            self.upd_open.set_label(label)
            self.upd_open.show()
            self.apt_hint.show()
        else:
            self.upd_open.hide()
            self.apt_hint.hide()
        self.upd_btn.set_sensitive(True)

    def on_auto(self, btn):
        self.cfg["check_updates"] = btn.get_active()
        settings.save(self.cfg)

    # ---- language ----
    def on_language(self, combo):
        new = combo.get_active_id() or "auto"
        self.cfg["language"] = new
        settings.save(self.cfg)
        changed = new != self.initial
        self.note.set_text(_("The new language is applied after a restart.") if changed else "")
        for w in (self.note, self.restart_btn):
            w.set_visible(changed)

    def on_restart(self, _btn):
        if self.is_busy():
            self.note.set_text(_("Wait until the current operation finishes, then restart."))
            self.note.show()
            return
        self.response(RESTART)
