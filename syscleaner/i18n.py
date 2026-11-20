"""Minimal i18n: YAML catalogs, language auto-detected from the system locale.

A catalog is a YAML file  data/i18n/<lang>.yaml  with three sections:
  ui:      {English source string: translation}
  groups:  {group id: translated title}
  tasks:   {task id: {title: ..., desc: ...}}
Users can add or override translations in ~/.config/syscleaner/i18n/<lang>.yaml.
Set SYSCLEANER_LANG=en (or ru, ...) to force a language.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DATA_DIR = Path(__file__).resolve().parent / "data" / "i18n"
USER_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "syscleaner" / "i18n"


def detect_langs() -> list[str]:
    """Language candidates in priority order, e.g. ['ru_RU', 'ru']."""
    forced = os.environ.get("SYSCLEANER_LANG")
    if forced:
        return [forced]
    raw: list[str] = []
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v:
            raw += v.split(":")
    out: list[str] = []
    for v in raw:
        v = v.split(".")[0].split("@")[0]
        if v in ("", "C", "POSIX"):
            continue
        out.append(v)
        if "_" in v:
            out.append(v.split("_")[0])
    return out


def _read(path: Path) -> dict:
    if yaml is None or not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _load() -> tuple[str, dict]:
    for lang in detect_langs():
        if lang.split("_")[0] == "en":
            break  # English is the source language
        builtin, user = _read(DATA_DIR / f"{lang}.yaml"), _read(USER_DIR / f"{lang}.yaml")
        if builtin or user:
            cat: dict = {"ui": {}, "groups": {}, "tasks": {}}
            for src in (builtin, user):
                for section in cat:
                    cat[section].update(src.get(section) or {})
            return lang, cat
    return "en", {"ui": {}, "groups": {}, "tasks": {}}


LANG, CATALOG = _load()


def _(msgid: str) -> str:
    """Translate a UI string (falls back to the English source)."""
    return CATALOG["ui"].get(msgid, msgid)


def group_title(gid: str, default: str) -> str:
    return CATALOG["groups"].get(gid, default)


def task_text(tid: str) -> dict:
    return CATALOG["tasks"].get(tid) or {}
