import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests import helpers
from syscleaner import tasks as T

CUSTOM = """
groups:
  - {id: mine, title: "Mine"}
tasks:
  - id: my_root
    group: mine
    title: "My root task"
    cmd: echo hi
    root: true
    schedule: true
  - id: my_user
    group: mine
    title: "My user task"
    cmd: echo hi
  - id: brave
    disabled: true
  - id: bad
    group: nope
    title: x
    cmd: echo
"""


class BuiltinTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with helpers.temp_dir() as empty:
            with mock.patch.object(T, "USER_DIR", Path(empty)):
                cls.groups, cls.tasks, cls.warnings = T.load()

    def test_loads_cleanly(self):
        self.assertEqual(self.warnings, [])
        self.assertGreaterEqual(len(self.tasks), 50)
        self.assertEqual([g for g, _ in self.groups], ["clean", "browsers", "dev", "find", "security"])

    def test_every_command_is_valid_bash(self):
        for t in self.tasks:
            for kind in ("cmd", "estimate", "preview"):
                src = getattr(t, kind)
                if src:
                    r = subprocess.run(["bash", "-n", "-c", src], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, f"{t.id}.{kind}: {r.stderr}")

    def test_builtin_tasks_are_not_custom_and_danger_is_never_scheduled(self):
        for t in self.tasks:
            self.assertEqual(t.source, "")
            if t.risk == "danger":
                self.assertFalse(t.schedule, t.id)

    def test_availability_by_path(self):
        with helpers.temp_dir() as home:
            with helpers.env(HOME=home):
                fx = next(t for t in self.tasks if t.id == "firefox_cache")
                self.assertFalse(T.available(fx))
                Path(home, ".cache/mozilla/firefox/abc.default/cache2").mkdir(parents=True)
                self.assertTrue(T.available(fx))


class CustomTaskTests(unittest.TestCase):
    def load_custom(self):
        with helpers.temp_dir() as d:
            Path(d, "mine.yaml").write_text(CUSTOM, encoding="utf-8")
            with mock.patch.object(T, "USER_DIR", Path(d)):
                return T.load()

    def test_custom_tasks_are_marked_and_never_scheduled(self):
        _, tasks, warnings = self.load_custom()
        by = {t.id: t for t in tasks}
        self.assertEqual(by["my_root"].source, "mine.yaml")
        self.assertTrue(by["my_root"].root)
        self.assertFalse(by["my_root"].schedule)          # the schedule runs as root and only knows built-ins
        self.assertEqual(by["my_user"].source, "mine.yaml")
        self.assertEqual(by["thumbs"].source, "")

    def test_disabled_removes_builtin_and_bad_entries_warn(self):
        _, tasks, warnings = self.load_custom()
        self.assertNotIn("brave", {t.id for t in tasks})
        self.assertTrue(any("bad" in w or "nope" in w for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
