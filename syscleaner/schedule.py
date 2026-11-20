"""Scheduling: generate a systemd service + timer (installed via pkexec)."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

from .i18n import _

UNIT = "syscleaner"
CONF_DIR = "/etc/syscleaner"
FREQS = {
    "Daily": "*-*-* {t}:00",
    "Weekly (Sunday)": "Sun *-*-* {t}:00",
    "Monthly (1st day)": "*-*-01 {t}:00",
}
# display names, same order as FREQS
FREQ_NAMES = (_("Daily"), _("Weekly (Sunday)"), _("Monthly (1st day)"))
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def exec_start() -> str:
    """Command line for the systemd service, depending on how the app was installed."""
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
Description=SysCleaner: scheduled cleanup

[Service]
Type=oneshot
ExecStart={exec_start()} --headless --config {CONF_DIR}/schedule.json
Nice=19
IOSchedulingClass=idle
SYSCLEANER_EOF
cat > /etc/systemd/system/{UNIT}.timer <<'SYSCLEANER_EOF'
[Unit]
Description=SysCleaner: schedule

[Timer]
OnCalendar={cal}
Persistent=true
RandomizedDelaySec=10min

[Install]
WantedBy=timers.target
SYSCLEANER_EOF
systemctl daemon-reload
systemctl enable --now {UNIT}.timer
echo "{_('Schedule enabled')}: {cal}"
systemctl list-timers {UNIT}.timer --no-pager
"""


def uninstall_script() -> str:
    return f"""systemctl disable --now {UNIT}.timer 2>/dev/null || true
rm -f /etc/systemd/system/{UNIT}.timer /etc/systemd/system/{UNIT}.service {CONF_DIR}/schedule.json
systemctl daemon-reload
echo "{_('Schedule disabled and removed')}"
"""


def status() -> str:
    try:
        en = subprocess.run(["systemctl", "is-enabled", f"{UNIT}.timer"], capture_output=True, text=True)
        if en.returncode != 0:
            return _("not configured")
        nxt = subprocess.run(["systemctl", "show", f"{UNIT}.timer", "-p", "NextElapseUSecRealtime", "--value"],
                             capture_output=True, text=True).stdout.strip()
        return _("enabled · next run: {when}").format(when=nxt or _("n/a"))
    except Exception as e:  # noqa: BLE001
        return f"n/a ({e})"
