"""Загрузка задач из YAML: встроенные + пользовательские (~/.config/syscleaner/tasks.d/*.yaml)."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DATA_DIR = Path(__file__).resolve().parent / "data"
USER_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "syscleaner" / "tasks.d"
RISKS = ("safe", "caution", "danger")


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
    requires: str = ""
    estimate: str = ""   # команда, печатающая в последней строке число байт
    preview: str = ""    # команда, показывающая, что будет затронуто
    schedule: bool = False  # можно ставить в расписание


def available(t: Task) -> bool:
    return not t.requires or shutil.which(t.requires) is not None


def _read(path: Path, warnings: list):
    if yaml is None:
        raise RuntimeError("Не установлен python3-yaml (sudo apt install python3-yaml)")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        warnings.append(f"{path}: {e}")
        return {}
    if not isinstance(data, dict):
        warnings.append(f"{path}: корень файла должен быть словарём")
        return {}
    return data


def load():
    """Возвращает (groups[(id, title)], tasks[Task], warnings[str])."""
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
                warnings.append(f"{f.name}: плохая группа {g!r}: {e}")
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
                )
                if t.risk not in RISKS:
                    raise ValueError(f"risk должен быть одним из {RISKS}")
                if t.group not in groups:
                    raise ValueError(f"неизвестная группа '{t.group}'")
                if t.risk == "danger":
                    t.schedule = False  # опасное по расписанию не запускаем никогда
                tasks[tid] = t
            except Exception as e:  # noqa: BLE001
                warnings.append(f"{f.name}: задача {str(raw)[:50]!r}: {e}")
    return list(groups.items()), list(tasks.values()), warnings
