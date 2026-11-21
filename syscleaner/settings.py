"""User settings stored as JSON in ~/.config/syscleaner/settings.json (no GTK here, testable anywhere)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "syscleaner" / "settings.json"


def load() -> dict:
    """Return the saved settings, or {} if there are none or the file is damaged."""
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict) -> bool:
    """Write atomically (temp file + rename) so a crash never leaves a half-written file."""
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".settings-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def _int(value, lo: int, hi: int):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if lo <= value <= hi else None


def window_state(cfg: dict) -> dict:
    """Validated window geometry; keys that are missing or out of range are simply left out."""
    raw = cfg.get("window")
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key, lo, hi in (("width", 480, 16000), ("height", 360, 16000), ("x", -16000, 16000),
                        ("y", -16000, 16000), ("paned", 150, 8000)):
        v = _int(raw.get(key), lo, hi)
        if v is not None:
            out[key] = v
    if isinstance(raw.get("maximized"), bool):
        out["maximized"] = raw["maximized"]
    return out
