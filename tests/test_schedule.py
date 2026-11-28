import os
import stat
import subprocess
import unittest

from tests import helpers  # noqa: F401
from syscleaner import schedule

FAKE_SYSTEMCTL = """#!/bin/sh
case "$1" in
  is-enabled) exit "${FAKE_ENABLED:-0}";;
  show)
    case "$2" in
      syscleaner.timer) echo "NextElapseUSecRealtime=Sun 2026-11-29 04:30:00 UTC";;
      syscleaner.service)
        echo "Result=${FAKE_RESULT:-success}"
        echo "ExecMainExitTimestamp=${FAKE_TS-Sat 2026-11-28 04:31:10 UTC}"
        echo "ExecMainStatus=0";;
    esac;;
esac
"""


class ScriptTests(unittest.TestCase):
    def test_install_script_is_valid_bash_for_every_frequency(self):
        for freq in schedule.FREQS:
            script = schedule.install_script(["tmp", "thumbs"], freq, "04:30", "someone")
            r = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("OnCalendar=", script)

    def test_uninstall_and_run_now_scripts_are_valid_bash(self):
        for script in (schedule.uninstall_script(), schedule.run_now_script()):
            self.assertEqual(subprocess.run(["bash", "-n", "-c", script]).returncode, 0)
        self.assertIn("journalctl -u syscleaner.service", schedule.run_now_script())

    def test_time_format(self):
        for ok in ("04:30", "4:30", "23:59", "00:00"):
            self.assertTrue(schedule.TIME_RE.match(ok), ok)
        for bad in ("24:00", "12:60", "1230", "ab:cd", ""):
            self.assertFalse(schedule.TIME_RE.match(bad), bad)

    def test_labels_and_calendar_are_in_step(self):
        self.assertEqual(len(schedule.FREQ_NAMES), len(schedule.FREQS))


class SystemctlTests(unittest.TestCase):
    def setUp(self):
        self.cm = helpers.temp_dir()
        d = self.cm.__enter__()
        path = os.path.join(d, "systemctl")
        with open(path, "w") as f:
            f.write(FAKE_SYSTEMCTL)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.env = helpers.env(PATH=d + os.pathsep + os.environ["PATH"], FAKE_ENABLED=None, FAKE_RESULT=None, FAKE_TS=None)
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        self.cm.__exit__(None, None, None)

    def test_status_when_enabled_and_when_not(self):
        self.assertTrue(schedule.is_installed())
        self.assertIn("2026-11-29 04:30", schedule.status())
        with helpers.env(FAKE_ENABLED="1"):
            self.assertFalse(schedule.is_installed())
            self.assertEqual(schedule.status(), "not configured")

    def test_last_run(self):
        run = schedule.last_run()
        self.assertEqual((run["result"], run["exit"]), ("success", "0"))
        self.assertIn("2026-11-28 04:31:10", schedule.last_run_text())
        with helpers.env(FAKE_RESULT="exit-code"):
            self.assertIn("failed: exit-code", schedule.last_run_text())
        with helpers.env(FAKE_TS=""):
            self.assertIsNone(schedule.last_run())
            self.assertEqual(schedule.last_run_text(), "Last run: never")


if __name__ == "__main__":
    unittest.main()
