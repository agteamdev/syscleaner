"""Script building and streaming execution (shared by the GUI and headless mode)."""
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
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return "?"


def build_script(tasks, dry: bool = False) -> str:
    """Build one bash script for a batch of tasks (real run or dry-run)."""
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
    """Run user-level tasks as `user` when we are root (systemd timer), directly otherwise."""
    if os.geteuid() != 0:
        return ["bash", "-c", script]
    home = pwd.getpwnam(user).pw_dir
    return ["runuser", "-u", user, "--", "env", f"HOME={home}", "bash", "-c", script]


def headless(ids, user: str, tasks, dry: bool = False) -> int:
    """Run without a GUI (systemd timer / CLI). Tasks with risk=danger are never executed."""
    by = {t.id: t for t in tasks}
    sel: list[Task] = []
    for i in ids:
        t = by.get(i)
        if not t:
            print(f"! unknown task: {i}")
        elif t.risk == "danger":
            print(f"! skipped (dangerous): {i}")
        elif not available(t):
            print(f"! skipped ({t.requires} not found): {i}")
        else:
            sel.append(t)

    def out(line):
        m = EST_RE.match(line)
        if m:
            print("  estimate: " + ("n/a" if m.group(2) == "-" else fmt_size(int(m.group(2)))), flush=True)
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
            print("! root tasks skipped: run as root (sudo)")
    if user_t:
        rc_all |= r.stream(user_argv(build_script(user_t, dry), user), out)
    if not dry:
        print(f"\nTotal freed: {fmt_size(max(0, shutil.disk_usage('/').free - free0))}")
    return 1 if rc_all else 0
