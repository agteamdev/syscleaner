import os
import unittest
from unittest import mock

from tests import helpers  # noqa: F401
from syscleaner import history


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.cm = helpers.temp_dir()
        self.dir = self.cm.__enter__()
        self.env = helpers.env(XDG_STATE_HOME=self.dir)
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        self.cm.__exit__(None, None, None)

    def test_add_load_totals_clear(self):
        self.assertEqual(history.load(), [])
        history.add(history.make_record("gui", ["tmp", "thumbs"], 5000, 12, True))
        history.add(history.make_record("schedule", ["tmp"], 1000, 3, False))
        history.add(history.make_record("gui", ["tmp"], -50, 1, True, stopped=True))   # negative growth is clamped
        recs = history.load()
        self.assertEqual([r["source"] for r in recs], ["gui", "schedule", "gui"])
        self.assertEqual(recs[2]["freed"], 0)
        self.assertFalse(recs[2]["ok"])                                                # stopped is not a success
        self.assertEqual(history.totals(recs), {"runs": 3, "freed": 6000, "failed": 1})
        self.assertEqual(len(history.load(limit=2)), 2)
        self.assertTrue(history.clear())
        self.assertEqual(history.load(), [])
        self.assertTrue(history.clear())                                               # clearing nothing is fine

    def test_damaged_lines_are_skipped_and_fields_normalised(self):
        p = history.path()
        p.parent.mkdir(parents=True)
        p.write_text('not json\n{"ts": "2026-01-01T00:00:00+00:00", "freed": "x", "tasks": "oops"}\n[1]\n{"no": "ts"}\n',
                     encoding="utf-8")
        recs = history.load()
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["freed"], recs[0]["tasks"], recs[0]["source"]), (0, [], "gui"))

    def test_old_records_are_trimmed(self):
        with mock.patch.object(history, "MAX_RECORDS", 5), mock.patch.object(history, "_TRIM_BYTES", 200):
            for i in range(30):
                history.add(history.make_record("cli", [f"t{i}"], i, 1, True))
        recs = history.load()
        self.assertLessEqual(len(recs), 30)
        self.assertEqual(recs[-1]["tasks"], ["t29"])                                   # newest survives
        self.assertLess(len(recs), 30)

    def test_history_of_another_home_and_ownership_hand_over(self):
        with helpers.temp_dir() as home:
            ok = history.add(history.make_record("schedule", ["tmp"], 1, 1, True), home=home,
                             owner=(os.getuid(), os.getgid()))
            self.assertTrue(ok)
            self.assertEqual(len(history.load(home=home)), 1)
            self.assertTrue(history.path(home).is_file())


if __name__ == "__main__":
    unittest.main()
