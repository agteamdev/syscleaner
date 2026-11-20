#!/usr/bin/env python3
"""Take README screenshots of the real app. Run it inside a desktop session (X11 / XWayland):

    python3 tools/screenshots.py                  # current theme and language
    SYSCLEANER_LANG=en GTK_THEME=Adwaita:dark python3 tools/screenshots.py dark
    SYSCLEANER_LANG=en GTK_THEME=Adwaita      python3 tools/screenshots.py light

Output: docs/screenshots/{cleanup,preview,disk}[-<suffix>].png

Privacy: only a fixed allow-list of user-level cache tasks is previewed (no password prompt, no file
names in the log) and the Disk tab scans /usr, so no personal paths end up in the images.
Still, look at the PNGs before you commit them.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("GDK_BACKEND", "x11")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from syscleaner.gui import MainWindow  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
SUFFIX = f"-{sys.argv[1]}" if len(sys.argv) > 1 else ""
PREVIEW_IDS = {"thumbs", "brave", "flatpak_cache", "npm", "pip", "go"}


def shot(win, name):
    gw = win.get_window()
    pb = Gdk.pixbuf_get_from_window(gw, 0, 0, gw.get_width(), gw.get_height())
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}{SUFFIX}.png"
    pb.savev(str(path), "png", [], [])
    print("saved", path)


def main():
    win = MainWindow()
    win.set_default_size(1180, 760)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    st = {"step": 0, "wait": 4}  # wait = number of 0.5 s ticks before the next action

    def tick():
        if st["wait"] > 0:
            st["wait"] -= 1
            return True
        step = st["step"]
        if step == 0:  # main tab with the first task selected
            win.tree.get_selection().select_path(Gtk.TreePath.new_from_string("0:0"))
            st["step"], st["wait"] = 1, 2
        elif step == 1:
            shot(win, "cleanup")
            for grp in win.store:
                grp[0] = False
                for ch in grp.iterchildren():
                    ch[0] = bool(ch[3] and ch[2] in PREVIEW_IDS)
            win.update_total()
            win.start(True)  # dry-run of user-level tasks only
            st["step"], st["wait"] = 2, 2
        elif step == 2:
            if win.btn_stop.get_sensitive():  # still running
                return True
            st["step"], st["wait"] = 3, 2
        elif step == 3:
            shot(win, "preview")
            win.nb.set_current_page(1)
            win.disk_tab.scan("/usr")
            st["step"], st["wait"] = 4, 2
        elif step == 4:
            if len(win.disk_tab.store) == 0 and st["wait"] > -60:
                st["wait"] -= 1
                return True
            st["step"], st["wait"] = 5, 2
        else:
            shot(win, "disk")
            Gtk.main_quit()
            return False
        return True

    GLib.timeout_add(500, tick)
    Gtk.main()


if __name__ == "__main__":
    main()
