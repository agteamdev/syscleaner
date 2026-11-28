"""Run history: one JSON object per line in ~/.local/state/syscleaner/history.jsonl (no GTK here)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

MAX_RECORDS = 1000
_TRIM_BYTES = 400_000


def path(home=None) -> Path:
    """History file of the current user, or of the user whose home directory is given."""
    if home is not None:
        base = Path(home) / ".local" / "state"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "syscleaner" / "history.jsonl"


def make_record(source: str, task_ids, freed, seconds, ok: bool, stopped: bool = False) -> dict:
    """source: "gui" | "schedule" | "cli". `freed` is the growth of free space on / during the run."""
    return {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "source": source,
            "tasks": list(task_ids), "freed": max(0, int(freed)), "seconds": max(0, int(seconds)),
            "ok": bool(ok) and not stopped, "stopped": bool(stopped)}


def _trim(p: Path) -> None:
    lines = p.read_text(encoding="utf-8").splitlines()[-MAX_RECORDS:]
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".history-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, p)


def add(record: dict, home=None, owner=None) -> bool:
    """Append a record. When root writes into a user's home (scheduled run), pass owner=(uid, gid):
    anything root had to create is handed over to that user so the GUI can read and clear it."""
    p = path(home)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if p.stat().st_size > _TRIM_BYTES:
            _trim(p)
        if owner is not None:
            for q in (p, p.parent, p.parent.parent, p.parent.parent.parent):
                if q.exists() and q.stat().st_uid == 0:  # never touch what already belongs to someone else
                    os.chown(q, owner[0], owner[1])
        return True
    except OSError:
        return False


def _clean(r: dict) -> dict:
    tasks = r.get("tasks")
    return {"ts": r["ts"], "source": str(r.get("source") or "gui"),
            "tasks": [str(t) for t in tasks] if isinstance(tasks, list) else [],
            "freed": r["freed"] if isinstance(r.get("freed"), int) and not isinstance(r.get("freed"), bool) else 0,
            "seconds": r["seconds"] if isinstance(r.get("seconds"), int) and not isinstance(r.get("seconds"), bool) else 0,
            "ok": bool(r.get("ok")), "stopped": bool(r.get("stopped"))}


def load(home=None, limit=None) -> list:
    """All valid records, oldest first; damaged lines are skipped."""
    try:
        lines = path(home).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and isinstance(r.get("ts"), str):
            out.append(_clean(r))
    return out[-limit:] if limit else out


def totals(records) -> dict:
    return {"runs": len(records), "freed": sum(r["freed"] for r in records),
            "failed": sum(1 for r in records if not r["ok"] and not r["stopped"])}


def clear(home=None) -> bool:
    try:
        path(home).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True
