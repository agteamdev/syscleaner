"""Real runs of the user-level cleanup tasks against a throw-away HOME."""
import os
import subprocess
import unittest
from pathlib import Path

from tests import helpers
from syscleaner.runner import EST_RE, build_script
from syscleaner.tasks import load

IDS = ["firefox_cache", "chrome_cache", "brave", "yarn_classic", "cargo_registry", "gradle_caches",
       "flatpak_app_caches", "recent_docs"]


FAKE_PS = """#!/bin/sh
# stand-in for `ps -C NAME -o stat=`: reports a live process only for names listed in $FAKE_RUNNING
for r in $FAKE_RUNNING; do [ "$r" = "$2" ] && echo "Ss" && exit 0; done
exit 1
"""


def mk(home, rel, size=100_000):
    p = Path(home, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


class CleaningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by = {t.id: t for t in load()[1]}

    def setUp(self):
        self.cm = helpers.temp_dir()
        self.home = self.cm.__enter__()
        self.bin = os.path.join(self.home, ".fakebin")          # outside every cleaned folder
        os.makedirs(self.bin)
        ps = os.path.join(self.bin, "ps")
        with open(ps, "w") as f:
            f.write(FAKE_PS)
        os.chmod(ps, 0o755)
        for rel, size in ((".cache/mozilla/firefox/abc.default/cache2/entries/a", 300_000),
                          ("snap/firefox/common/.cache/mozilla/firefox/x.default/cache2/entries/b", 200_000),
                          (".cache/google-chrome/Default/Cache/c", 400_000), (".cache/google-chrome-beta/Default/Cache/c", 50_000),
                          (".cache/BraveSoftware/Brave-Browser/Default/Cache/d", 150_000),
                          (".cache/yarn/v6/pkg", 250_000), (".cargo/registry/cache/x/crate.crate", 120_000),
                          (".cargo/registry/src/x/lib.rs", 60_000), (".gradle/caches/modules/m", 90_000),
                          (".var/app/org.gnome.Foo/cache/a", 70_000), (".var/app/org.bar.Baz/cache/sub/b", 30_000),
                          (".local/share/recently-used.xbel", 5_000)):
            mk(self.home, rel, size)
        for rel in (".mozilla/firefox/abc.default/places.sqlite", ".mozilla/firefox/abc.default/logins.json",
                    ".config/google-chrome/Default/Login Data", ".config/google-chrome/Default/Bookmarks",
                    ".config/BraveSoftware/Brave-Browser/Default/History", ".cargo/registry/index/keep.txt",
                    ".gradle/wrapper/keep", ".var/app/org.gnome.Foo/data/keep.db"):
            mk(self.home, rel, 10)

    def tearDown(self):
        self.cm.__exit__(None, None, None)

    def run_tasks(self, ids, dry, running=""):
        env = dict(os.environ, HOME=self.home, FAKE_RUNNING=running, PATH=self.bin + os.pathsep + os.environ["PATH"])
        out = subprocess.run(["bash", "-c", build_script([self.by[i] for i in ids], dry)], capture_output=True,
                             text=True, env=env)
        return out.stdout

    def exists(self, rel):
        return Path(self.home, rel).exists()

    def test_estimates_match_the_real_sizes(self):
        est, cur = {}, None
        for line in self.run_tasks(IDS, True).splitlines():
            m = EST_RE.match(line)
            if m:
                est[m.group(1)] = int(m.group(2))
        self.assertGreaterEqual(est["firefox_cache"], 500_000)
        self.assertGreaterEqual(est["chrome_cache"], 450_000)
        self.assertGreaterEqual(est["cargo_registry"], 180_000)
        self.assertGreaterEqual(est["flatpak_app_caches"], 100_000)
        self.assertTrue(all(est[i] > 0 for i in IDS))
        self.assertTrue(self.exists(".cache/yarn/v6/pkg"), "a dry run must not delete anything")

    def test_cleaning_removes_caches_but_never_profiles(self):
        out = self.run_tasks(IDS, False)
        self.assertNotIn("skipped", out)
        for gone in (".cache/mozilla/firefox/abc.default/cache2", "snap/firefox/common/.cache/mozilla/firefox/x.default/cache2",
                     ".cache/google-chrome", ".cache/google-chrome-beta", ".cache/BraveSoftware", ".cache/yarn",
                     ".cargo/registry/cache", ".cargo/registry/src", ".gradle/caches", ".var/app/org.gnome.Foo/cache/a",
                     ".var/app/org.bar.Baz/cache/sub", ".local/share/recently-used.xbel"):
            self.assertFalse(self.exists(gone), f"should be gone: {gone}")
        for kept in (".mozilla/firefox/abc.default/places.sqlite", ".mozilla/firefox/abc.default/logins.json",
                     ".config/google-chrome/Default/Login Data", ".config/google-chrome/Default/Bookmarks",
                     ".config/BraveSoftware/Brave-Browser/Default/History", ".cargo/registry/index/keep.txt",
                     ".gradle/wrapper/keep", ".var/app/org.gnome.Foo/data/keep.db"):
            self.assertTrue(self.exists(kept), f"must survive: {kept}")

    def test_a_running_browser_is_skipped_and_cleaned_once_closed(self):
        cache = ".cache/mozilla/firefox/abc.default/cache2/entries/a"
        out = self.run_tasks(["firefox_cache"], False, running="firefox")
        self.assertIn("skipped", out)
        self.assertTrue(self.exists(cache))
        out = self.run_tasks(["firefox_cache"], False, running="chrome")      # another browser: Firefox is not affected
        self.assertNotIn("skipped", out)
        self.assertFalse(self.exists(".cache/mozilla/firefox/abc.default/cache2"))

    def test_every_browser_guard_knows_its_process_names(self):
        for task, proc in (("chrome_cache", "chrome"), ("chromium_cache", "chromium"), ("edge_cache", "msedge"),
                           ("brave", "brave"), ("vivaldi_cache", "vivaldi-bin"), ("opera_cache", "opera"),
                           ("firefox_cache", "firefox-esr")):
            out = self.run_tasks([task], False, running=proc)
            self.assertIn("skipped", out, f"{task} must stop while {proc} runs")


if __name__ == "__main__":
    unittest.main()
