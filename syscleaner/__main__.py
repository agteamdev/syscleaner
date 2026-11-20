import argparse
import json
import os
import pwd
import sys

from . import __version__
from .tasks import load


def main():
    ap = argparse.ArgumentParser(prog="syscleaner", description="GUI-очистка и диагностика Linux Mint / Debian")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--list", action="store_true", help="показать список задач")
    ap.add_argument("--headless", action="store_true", help="запуск без GUI")
    ap.add_argument("--dry-run", action="store_true", help="только предпросмотр и оценка (с --headless)")
    ap.add_argument("--config", help="JSON {user, tasks[]} (используется расписанием)")
    ap.add_argument("--tasks", help="id задач через запятую (с --headless)")
    ap.add_argument("--user", help="пользователь для user-задач при запуске от root")
    a = ap.parse_args()

    groups, tasks, warns = load()
    for w in warns:
        print("warn:", w, file=sys.stderr)

    if a.list:
        for t in tasks:
            print(f"{t.id:16} {t.risk:8} {'root' if t.root else 'user':5} {'⏱' if t.schedule else ' '} {t.title}")
        return 0

    if a.headless:
        from .runner import headless
        ids, user = [], a.user
        if a.config:
            with open(a.config, encoding="utf-8") as f:
                c = json.load(f)
            ids, user = c.get("tasks", []), user or c.get("user")
        if a.tasks:
            ids = [x for x in a.tasks.split(",") if x]
        user = user or os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name
        return headless(ids, user, tasks, dry=a.dry_run)

    from .gui import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
