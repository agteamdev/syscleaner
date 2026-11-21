"""About dialog: version, update check, links, project support and language choice."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import __version__, links, settings, updater  # noqa: E402
from .i18n import _, available_languages  # noqa: E402

RESTART = 100  # dialog response meaning "restart the application"
PAD = 12


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


class AboutDialog(Gtk.Dialog):
    def __init__(self, parent, cfg: dict, is_busy):
        super().__init__(title=_("About SysCleaner"), transient_for=parent, modal=True)
        self.cfg, self.is_busy = cfg, is_busy
        self._alive = True
        self.connect("destroy", lambda *_a: setattr(self, "_alive", False))
        self.add_button(_("Close"), Gtk.ResponseType.CLOSE)
        area = self.get_content_area()
        area.set_spacing(12)
        area.set_border_width(PAD + 6)

        # --- header -----------------------------------------------------
        head = Gtk.Box(spacing=16)
        icon = Path(__file__).resolve().parent.parent / "packaging" / "icons" / "128x128" / "syscleaner.png"
        img = (Gtk.Image.new_from_file(str(icon)) if icon.exists()
               else Gtk.Image.new_from_icon_name("syscleaner", Gtk.IconSize.DIALOG))
        head.pack_start(img, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(xalign=0)
        title.set_markup('<span size="xx-large" weight="bold">SysCleaner</span>')
        names.pack_start(title, False, False, 0)
        names.pack_start(Gtk.Label(xalign=0, label=_("Version {version}").format(version=__version__)),
                         False, False, 0)
        names.pack_start(Gtk.Label(xalign=0, label=_("Cleanup and diagnostics for Linux Mint / Debian / Ubuntu")),
                         False, False, 0)
        names.pack_start(Gtk.Label(xalign=0, label=_("MIT license · © AG TEAM DEV")), False, False, 0)
        head.pack_start(names, True, True, 0)
        area.pack_start(head, False, False, 0)
        area.pack_start(Gtk.Separator(), False, False, 0)

        # --- update check -----------------------------------------------
        row = Gtk.Box(spacing=8)
        self.upd_lbl = Gtk.Label(xalign=0, wrap=True, selectable=True)
        row.pack_start(self.upd_lbl, True, True, 0)
        self.upd_link = Gtk.LinkButton.new_with_label(links.RELEASES_URL, _("Open the release page"))
        self.upd_link.set_no_show_all(True)
        row.pack_start(self.upd_link, False, False, 0)
        self.upd_btn = Gtk.Button(label=_("Check again"))
        self.upd_btn.connect("clicked", lambda *_a: self.check_updates())
        row.pack_start(self.upd_btn, False, False, 0)
        area.pack_start(row, False, False, 0)

        # --- links ------------------------------------------------------
        area.pack_start(Gtk.Separator(), False, False, 0)
        lk = Gtk.Box(spacing=6)
        for label, url in ((_("Website"), links.REPO_URL), (_("Report an issue"), links.ISSUES_URL),
                           (_("All releases"), links.RELEASES_URL)):
            lk.pack_start(Gtk.LinkButton.new_with_label(url, label), False, False, 0)
        area.pack_start(lk, False, False, 0)

        # --- support ----------------------------------------------------
        sup = Gtk.Label(xalign=0, wrap=True)
        sup.set_markup("<b>" + GLib.markup_escape_text(_("Support the project")) + "</b>\n" + GLib.markup_escape_text(
            _("SysCleaner is free and open source. If it saved you time, you can support its development:")))
        area.pack_start(sup, False, False, 0)
        sb = Gtk.Box(spacing=6)
        for label, url in (("Patreon", links.PATREON_URL), (_("Donate (NOWPayments)"), links.DONATE_URL)):
            sb.pack_start(Gtk.LinkButton.new_with_label(url, label), False, False, 0)
        area.pack_start(sb, False, False, 0)

        # --- language ---------------------------------------------------
        area.pack_start(Gtk.Separator(), False, False, 0)
        lang = Gtk.Box(spacing=8)
        lang.pack_start(Gtk.Label(label=_("Language:")), False, False, 0)
        self.combo = Gtk.ComboBoxText()
        self.combo.append("auto", _("System default"))
        for code, name in available_languages():
            self.combo.append(code, name)
        self.initial = str(cfg.get("language") or "auto")
        if not self.combo.set_active_id(self.initial):
            self.combo.set_active_id("auto")
        self.combo.connect("changed", self.on_language)
        lang.pack_start(self.combo, False, False, 0)
        self.restart_btn = Gtk.Button(label=_("Restart now"))
        self.restart_btn.set_no_show_all(True)
        self.restart_btn.connect("clicked", self.on_restart)
        lang.pack_start(self.restart_btn, False, False, 0)
        area.pack_start(lang, False, False, 0)
        self.note = Gtk.Label(xalign=0, wrap=True)
        self.note.set_no_show_all(True)
        area.pack_start(self.note, False, False, 0)
        if os.environ.get("SYSCLEANER_LANG"):
            env = Gtk.Label(xalign=0, wrap=True, label=_(
                "The SYSCLEANER_LANG environment variable is set and overrides this choice."))
            area.pack_start(env, False, False, 0)

        self.check_updates()

    # ---- update check ----
    def check_updates(self):
        self.upd_btn.set_sensitive(False)
        self.upd_link.hide()
        self.upd_lbl.set_text(_("Checking for updates…"))
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        GLib.idle_add(self._show, updater.check(__version__))

    def _show(self, res):
        if not self._alive:
            return
        text, url, label = update_message(res, __version__)
        self.upd_lbl.set_text(text)
        if url:
            self.upd_link.set_uri(url)
            self.upd_link.set_label(label)
            self.upd_link.show()
        self.upd_btn.set_sensitive(True)

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
