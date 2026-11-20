"""Расписание: генерация systemd service+timer (ставится через pkexec)."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

UNIT = "syscleaner"
CONF_DIR = "/etc/syscleaner"
FREQS = {
    "Ежедневно": "*-*-* {t}:00",
    "Еженедельно (вс)": "Sun *-*-* {t}:00",
    "Ежемесячно (1-го числа)": "*-*-01 {t}:00",
}
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def exec_start() -> str:
    if os.environ.get("APPIMAGE"):
        return shlex.quote(os.environ["APPIMAGE"])
    parent = Path(__file__).resolve().parent.parent
    if str(parent) == "/usr/lib/syscleaner":
        return "/usr/bin/syscleaner"
    return f"/usr/bin/env PYTHONPATH={shlex.quote(str(parent))} python3 -m syscleaner"


def install_script(ids, freq_label: str, hhmm: str, user: str) -> str:
    cal = FREQS[freq_label].format(t=hhmm)
    conf = json.dumps({"user": user, "tasks": list(ids)}, ensure_ascii=False, indent=2)
    return f"""set -e
mkdir -p {CONF_DIR}
cat > {CONF_DIR}/schedule.json <<'SYSCLEANER_EOF'
{conf}
SYSCLEANER_EOF
cat > /etc/systemd/system/{UNIT}.service <<'SYSCLEANER_EOF'
[Unit]
Description=SysCleaner: плановая очистка

[Service]
Type=oneshot
ExecStart={exec_start()} --headless --config {CONF_DIR}/schedule.json
Nice=19
IOSchedulingClass=idle
SYSCLEANER_EOF
cat > /etc/systemd/system/{UNIT}.timer <<'SYSCLEANER_EOF'
[Unit]
Description=SysCleaner: расписание

[Timer]
OnCalendar={cal}
Persistent=true
RandomizedDelaySec=10min

[Install]
WantedBy=timers.target
SYSCLEANER_EOF
systemctl daemon-reload
systemctl enable --now {UNIT}.timer
echo "Расписание включено: {cal}"
systemctl list-timers {UNIT}.timer --no-pager
"""


def uninstall_script() -> str:
    return f"""systemctl disable --now {UNIT}.timer 2>/dev/null || true
rm -f /etc/systemd/system/{UNIT}.timer /etc/systemd/system/{UNIT}.service {CONF_DIR}/schedule.json
systemctl daemon-reload
echo "Расписание отключено и удалено"
"""


def status() -> str:
    try:
        en = subprocess.run(["systemctl", "is-enabled", f"{UNIT}.timer"], capture_output=True, text=True)
        if en.returncode != 0:
            return "не настроено"
        nxt = subprocess.run(["systemctl", "show", f"{UNIT}.timer", "-p", "NextElapseUSecRealtime", "--value"],
                             capture_output=True, text=True).stdout.strip()
        return f"включено · следующий запуск: {nxt or 'н/д'}"
    except Exception as e:  # noqa: BLE001
        return f"н/д ({e})"
