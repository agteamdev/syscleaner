import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import helpers

try:
    from syscleaner import fileops
except ImportError:  # PyGObject is not installed (e.g. a plain pip-based Python)
    fileops = None


@unittest.skipIf(fileops is None, "needs python3-gi (Gio)")
class FileOpsTests(unittest.TestCase):
    def test_protected_paths(self):
        for p in ("/", "/usr", "/etc", "/home", "/home/someone", "/var", str(Path.home())):
            self.assertTrue(fileops.is_protected(p), p)
        for p in (str(Path.home() / "Downloads" / "x"), "/mnt/data/thing", "/opt/app/cache"):
            self.assertFalse(fileops.is_protected(p), p)

    def test_trash_refuses_protected_paths(self):
        with self.assertRaises(PermissionError):
            fileops.trash("/usr")

    def test_folder_uri_is_a_real_uri_for_folders_and_files(self):
        with helpers.temp_dir() as d:
            f = Path(d, "a b.txt")
            f.write_text("x")
            self.assertEqual(fileops.folder_uri(d, True), Path(d).as_uri())
            self.assertEqual(fileops.folder_uri(str(f), False), Path(d).as_uri())   # a file opens its folder

    def test_trash_moves_a_file_into_the_freedesktop_trash(self):
        code = ("import sys; sys.path.insert(0, %r); from syscleaner import fileops; fileops.trash(sys.argv[1])"
                % str(helpers.ROOT))
        with tempfile.TemporaryDirectory(dir=str(Path.home())) as d:   # same filesystem as $HOME
            data = Path(d, "data")
            data.mkdir()
            victim = Path(d, "work", "victim.txt")
            victim.parent.mkdir()
            victim.write_text("bye")
            r = subprocess.run([sys.executable, "-c", code, str(victim)], capture_output=True, text=True,
                               env=helpers.clean_env({"XDG_DATA_HOME": str(data), "HOME": str(Path.home())}))
            if r.returncode != 0 and "rash" in r.stderr:
                self.skipTest("this environment has no usable trash: " + r.stderr.strip()[-120:])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(victim.exists())
            self.assertTrue(list(data.glob("Trash/files/victim*")))


if __name__ == "__main__":
    unittest.main()
