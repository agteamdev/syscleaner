import subprocess
import sys
import unittest

from tests import helpers

LANGS = ("en", "ru", "uk", "it", "de", "es", "fr", "pl", "pt")


class GuiLogicTests(unittest.TestCase):
    def test_gui_logic_in_every_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                r = subprocess.run([sys.executable, str(helpers.ROOT / "tests" / "gui_smoke.py"), str(helpers.ROOT)],
                                   capture_output=True, text=True, env=helpers.clean_env({"SYSCLEANER_LANG": lang}))
                self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
                self.assertIn("GUI smoke OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
