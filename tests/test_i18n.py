import subprocess
import sys
import unittest

from tests import helpers
from syscleaner import i18n, settings

CODE = ("import sys; sys.path.insert(0, %r); from syscleaner import i18n; "
        "print(i18n.LANG, '|', i18n._('Select all'))" % str(helpers.ROOT))


def lang_in_fresh_process(env, saved=None):
    """Run a clean interpreter so the language is decided exactly as at program start."""
    with helpers.temp_dir() as cfg:
        with helpers.env(XDG_CONFIG_HOME=cfg):
            if saved is not None:
                settings.save({"language": saved})
        out = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True,
                             env=helpers.clean_env(dict(env, XDG_CONFIG_HOME=cfg)))
    return out.stdout.strip()


class LanguageTests(unittest.TestCase):
    def test_follows_system_locale(self):
        self.assertTrue(lang_in_fresh_process({"LANG": "ru_RU.UTF-8"}).startswith("ru"))
        self.assertTrue(lang_in_fresh_process({"LANG": "uk_UA.UTF-8"}).startswith("uk"))
        self.assertTrue(lang_in_fresh_process({"LANG": "de_DE.UTF-8"}).startswith("de"))
        self.assertTrue(lang_in_fresh_process({"LANGUAGE": "it:ru", "LANG": "en_US.UTF-8"}).startswith("it"))

    def test_unknown_or_c_locale_is_english(self):
        self.assertEqual(lang_in_fresh_process({"LANG": "xx_XX.UTF-8"}), "en | Select all")
        self.assertEqual(lang_in_fresh_process({"LANG": "C"}), "en | Select all")

    def test_saved_choice_beats_system_locale(self):
        self.assertEqual(lang_in_fresh_process({"LANG": "ru_RU.UTF-8"}, saved="en"), "en | Select all")
        self.assertTrue(lang_in_fresh_process({"LANG": "en_US.UTF-8"}, saved="fr").startswith("fr"))
        self.assertEqual(lang_in_fresh_process({"LANG": "ru_RU.UTF-8"}, saved="auto").split(" |")[0], "ru")

    def test_env_variable_beats_saved_choice(self):
        got = lang_in_fresh_process({"LANG": "ru_RU.UTF-8", "SYSCLEANER_LANG": "en"}, saved="fr")
        self.assertEqual(got, "en | Select all")

    def test_unknown_saved_language_falls_back_to_english(self):
        self.assertTrue(lang_in_fresh_process({"LANG": "ru_RU.UTF-8"}, saved="xx").startswith("en"))

    def test_picker_lists_english_first_and_every_catalog(self):
        langs = i18n.available_languages()
        self.assertEqual(langs[0], ("en", "English"))
        codes = {c for c, _ in langs}
        self.assertTrue({"ru", "uk", "it", "de", "es", "fr", "pl", "pt"} <= codes)


class CatalogTests(unittest.TestCase):
    def test_every_catalog_is_complete(self):
        """tools/check_i18n.py: no missing / stale strings, placeholders and newlines intact."""
        r = subprocess.run([sys.executable, str(helpers.ROOT / "tools" / "check_i18n.py")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
