import os
import tempfile
import unittest

from tests import helpers  # noqa: F401
from syscleaner import diskscan


def scan(path):
    proc = diskscan.start(path)
    with proc.stdout:
        events = [e for e in map(diskscan.parse_line, proc.stdout) if e]
    proc.wait()
    return events


class DiskScanTests(unittest.TestCase):
    def test_tricky_names_symlinks_and_empty_dirs(self):
        d = tempfile.mkdtemp(prefix="sc test ")
        os.makedirs(f"{d}/dir with spaces")
        with open(f"{d}/dir with spaces/f.bin", "wb") as f:
            f.write(b"x" * 200_000)
        with open(f"{d}/файл кириллица.txt", "w", encoding="utf-8") as f:
            f.write("hi")
        os.symlink("/usr", f"{d}/link")
        os.makedirs(f"{d}/empty")
        events = scan(d)
        self.assertEqual(events[0][0], "n")
        self.assertEqual(events[-1], ("end",))
        items = {os.path.basename(e[3]): e for e in events if e[0] == "item"}
        self.assertEqual(events[0][1], len(items))                  # progress denominator is exact
        self.assertTrue(items["dir with spaces"][1] and items["empty"][1])
        self.assertFalse(items["link"][1])                          # a symlink is not entered
        self.assertGreaterEqual(items["dir with spaces"][2], 200_000)
        self.assertEqual(len([e for e in events if e[0] == "cur"]), len(items))

    def test_empty_folder(self):
        self.assertEqual(scan(tempfile.mkdtemp()), [("n", 0), ("end",)])

    def test_parser_ignores_garbage(self):
        self.assertIsNone(diskscan.parse_line("@@ITEM\tx\tnotanumber\tp"))
        self.assertIsNone(diskscan.parse_line("hello"))


if __name__ == "__main__":
    unittest.main()
