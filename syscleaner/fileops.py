"""File actions for the Disk tab: trash and open-in-file-manager (Gio only, no GTK here)."""
from __future__ import annotations

import os
from pathlib import Path

from gi.repository import Gio


def is_protected(path: str) -> bool:
    """Never offer to trash the filesystem root, any top-level system folder, a home folder itself."""
    p = os.path.abspath(path)
    return (p == "/" or os.path.dirname(p) in ("/", "/home") or p == str(Path.home()))


def trash(path: str) -> None:
    """Move to the freedesktop trash (home trash, or the mount-local one on other partitions).
    Raises PermissionError for protected paths and GLib.Error if the file cannot be trashed."""
    if is_protected(path):
        raise PermissionError(path)
    Gio.File.new_for_path(path).trash(None)


def folder_uri(path: str, is_dir: bool) -> str:
    """URI of the folder to show: the folder itself, or the one that contains a file.
    (launch_default_for_uri does not accept plain paths, so the URI is built through GFile.)"""
    target = path if is_dir else (os.path.dirname(path) or "/")
    return Gio.File.new_for_path(target).get_uri()


def open_folder(path: str, is_dir: bool) -> None:
    """Open in the default file manager. Raises GLib.Error if there is no handler."""
    Gio.AppInfo.launch_default_for_uri(folder_uri(path, is_dir), None)
