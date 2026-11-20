"""Сборка скриптов и потоковый запуск (общий для GUI и headless)."""
from __future__ import annotations

import os
import pwd
import re
import shlex
import shutil
import subprocess

from .tasks import Task, available

PRELUDE = r"""export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
sz() { du -sbc "$@" 2>/dev/null | tail -1 | cut -f1; }
"""
EST_RE = re.compile(r"^@@EST (\S+) (\d+|-)\s*$")


def fmt_size(n) -> str:
    n = float(n)
    for u in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024 or u == "ТБ":
            return f"{n:.0f} {u}" if u == "Б" else f"{n:.1f} {u}"
        n /= 1024
    return "?"


def build_script(tasks, dry: bool = False) -> str:
    parts = [PRELUDE]
    for t in tasks:
        parts.append(f"echo; echo {shlex.quote('▶ ' + t.title)}")
        if dry:
            if t.preview:
                parts.append(f"( {t.preview}\n) 2>&1 | head -60")
            if t.estimate:
                parts.append(
                    f'e=$( ( {t.estimate}\n) 2>/dev/null | tail -1 ); '
                    f'case "$e" in (""|*[!0-9]*) e=0;; esac; echo "@@EST {t.id} $e"')
            else:
                parts.append(f'echo "@@EST {t.id} -"')
        else:
            parts.append(t.cmd)
    return "\n".join(parts) + "\n"


class Runner:
    def __init__(self):
        self.proc = None
        self.stopped = False

    def stream(self, argv, on_line) -> int:
        self.proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, bufsize=1, errors="replace")
        for line in self.proc.stdout:
            on_line(line.rstrip("\n"))
        return self.proc.wait()

    def stop(self):
        self.stopped = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def user_argv(script: str, user: str):
    if os.geteuid() != 0:
        return ["bash", "-c", script]
    home = pwd.getpwnam(user).pw_dir
    return ["runuser", "-u", user, "--", "env", f"HOME={home}", "bash", "-c", script]


def headless(ids, user: str, tasks, dry: bool = False) -> int:
    """Запуск без GUI (для systemd timer и CLI). Опасные задачи не запускаются никогда."""
    by = {t.id: t for t in tasks}
    sel: list[Task] = []
    for i in ids:
        t = by.get(i)
        if not t:
            print(f"! неизвестная задача: {i}")
        elif t.risk == "danger":
            print(f"! пропущено (опасная): {i}")
        elif not available(t):
            print(f"! пропущено (нет {t.requires}): {i}")
        else:
            sel.append(t)

    def out(line):
        m = EST_RE.match(line)
        if m:
            print("  оценка: " + ("н/д" if m.group(2) == "-" else fmt_size(int(m.group(2)))), flush=True)
        else:
            print(line, flush=True)

    free0 = shutil.disk_usage("/").free
    r = Runner()
    rc_all = 0
    root_t = [t for t in sel if t.root]
    user_t = [t for t in sel if not t.root]
    if root_t:
        if os.geteuid() == 0:
            rc_all |= r.stream(["bash", "-c", build_script(root_t, dry)], out)
        else:
            print("! root-задачи пропущены: запусти от root (sudo)")
    if user_t:
        rc_all |= r.stream(user_argv(build_script(user_t, dry), user), out)
    if not dry:
        print(f"\nИтого освобождено: {fmt_size(max(0, shutil.disk_usage('/').free - free0))}")
    return 1 if rc_all else 0
