"""Task loading from YAML: built-in tasks plus user tasks (~/.config/syscleaner/tasks.d/*.yaml)."""
from __future__ import annotations

import glob
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .i18n import group_title, task_text

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DATA_DIR = Path(__file__).resolve().parent / "data"
USER_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "syscleaner" / "tasks.d"
RISKS = ("safe", "caution", "danger")
READONLY_GROUPS = {"find", "security"}  # groups that only inspect the system (not selected by "Safe only")


@dataclass
class Task:
    id: str
    group: str
    title: str
    desc: str
    cmd: str
    root: bool = False
    risk: str = "safe"
    default: bool = False
    requires: str = ""      # program that must exist, otherwise the task is greyed out
    estimate: str = ""      # command whose last output line is a number of bytes (dry-run)
    preview: str = ""       # command showing what would be affected (dry-run)
    schedule: bool = False  # may be added to the systemd timer schedule
    requires_path: tuple = ()   # globs (~ allowed); the task needs at least one of them to exist
    hide_missing: bool = False  # hide the task entirely when `requires` / `requires_path` is not met


def available(t: Task) -> bool:
    """True if the program and/or data the task needs exist on this system."""
    if t.requires and shutil.which(t.requires) is None:
        return False
    if t.requires_path and not any(glob.glob(os.path.expanduser(p)) for p in t.requires_path):
        return False
    return True


def _paths(value) -> tuple:
    if not value:
        return ()
    return (str(value),) if isinstance(value, str) else tuple(str(v) for v in value)


def _read(path: Path, warnings: list):
    if yaml is None:
        raise RuntimeError("python3-yaml is not installed (sudo apt install python3-yaml)")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        warnings.append(f"{path}: {e}")
        return {}
    if not isinstance(data, dict):
        warnings.append(f"{path}: top level must be a mapping")
        return {}
    return data


def load():
    """Return (groups[(id, title)], tasks[Task], warnings[str])."""
    warnings: list = []
    groups: dict = {}
    tasks: dict = {}
    files = [DATA_DIR / "tasks.yaml"]
    if USER_DIR.is_dir():
        files += sorted(list(USER_DIR.glob("*.yaml")) + list(USER_DIR.glob("*.yml")))
    for f in files:
        data = _read(f, warnings)
        for g in data.get("groups") or []:
            try:
                groups[str(g["id"])] = str(g.get("title", g["id"]))
            except Exception as e:  # noqa: BLE001
                warnings.append(f"{f.name}: bad group {g!r}: {e}")
        for raw in data.get("tasks") or []:
            try:
                tid = str(raw["id"])
                if raw.get("disabled"):
                    tasks.pop(tid, None)
                    continue
                t = Task(
                    id=tid, group=str(raw["group"]), title=str(raw["title"]),
                    desc=str(raw.get("desc", "")).strip(), cmd=str(raw["cmd"]).strip(),
                    root=bool(raw.get("root", False)), risk=str(raw.get("risk", "safe")),
                    default=bool(raw.get("default", False)), requires=str(raw.get("requires", "")),
                    estimate=str(raw.get("estimate", "")).strip(),
                    preview=str(raw.get("preview", "")).strip(),
                    schedule=bool(raw.get("schedule", False)),
                    requires_path=_paths(raw.get("requires_path")),
                    hide_missing=bool(raw.get("hide_missing", False)),
                )
                if t.risk not in RISKS:
                    raise ValueError(f"risk must be one of {RISKS}")
                if t.group not in groups:
                    raise ValueError(f"unknown group '{t.group}'")
                if t.risk == "danger":
                    t.schedule = False  # dangerous tasks are never scheduled
                tasks[tid] = t
            except Exception as e:  # noqa: BLE001
                warnings.append(f"{f.name}: task {str(raw)[:50]!r}: {e}")
    # apply translations of the system language (English is the source text)
    groups = {gid: group_title(gid, title) for gid, title in groups.items()}
    for t in tasks.values():
        tr = task_text(t.id)
        t.title = str(tr.get("title", t.title))
        t.desc = str(tr.get("desc", t.desc)).strip()
    return list(groups.items()), list(tasks.values()), warnings
