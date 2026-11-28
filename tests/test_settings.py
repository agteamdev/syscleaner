import json
import os
import unittest

from tests import helpers  # noqa: F401
from syscleaner import settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.cm = helpers.temp_dir()
        self.dir = self.cm.__enter__()
        self.env = helpers.env(XDG_CONFIG_HOME=self.dir)
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        self.cm.__exit__(None, None, None)

    def test_missing_file_gives_empty(self):
        self.assertEqual(settings.load(), {})

    def test_roundtrip_and_no_temp_files(self):
        self.assertTrue(settings.save({"language": "ru", "window": {"width": 1000}}))
        self.assertEqual(settings.load()["language"], "ru")
        left = [f for f in os.listdir(os.path.dirname(settings.path())) if f.endswith(".tmp")]
        self.assertEqual(left, [])

    def test_damaged_files_are_ignored(self):
        settings.save({"a": 1})
        for bad in ("{broken json", "[1, 2]", ""):
            with open(settings.path(), "w", encoding="utf-8") as f:
                f.write(bad)
            self.assertEqual(settings.load(), {})

    def test_window_state_validation(self):
        got = settings.window_state({"window": {"width": 99999, "height": "big", "x": -50, "y": True,
                                                 "paned": 600, "maximized": "yes"}})
        self.assertEqual(got, {"x": -50, "paned": 600})
        self.assertEqual(settings.window_state({}), {})
        self.assertEqual(settings.window_state({"window": 5}), {})
        ok = settings.window_state({"window": {"width": 1200, "height": 780, "maximized": True}})
        self.assertEqual(ok, {"width": 1200, "height": 780, "maximized": True})


if __name__ == "__main__":
    unittest.main()
