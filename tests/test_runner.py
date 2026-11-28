import os
import shutil
import subprocess
import sys
import unittest

from tests import helpers
from syscleaner.runner import BEGIN_RE, EST_RE, PRELUDE, build_script, fmt_duration, fmt_size
from syscleaner.tasks import load


class FormatTests(unittest.TestCase):
    def test_duration_is_hh_mm_ss(self):
        got = [fmt_duration(x) for x in (0, 5, 65, 3599, 3661, 86399, -3)]
        self.assertEqual(got, ["00:00:00", "00:00:05", "00:01:05", "00:59:59", "01:01:01", "23:59:59", "00:00:00"])

    def test_sizes(self):
        self.assertEqual(fmt_size(0), "0 B")
        self.assertEqual(fmt_size(1536), "1.5 KB")
        self.assertEqual(fmt_size(5 * 2**20), "5.0 MB")


class ScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by = {t.id: t for t in load()[1]}

    def run_script(self, tasks, dry=False, **kw):
        with helpers.temp_dir() as home:
            return subprocess.run(["bash", "-c", build_script(tasks, dry, **kw)], capture_output=True, text=True,
                                  env=dict(os.environ, HOME=home)).stdout.splitlines()

    def test_progress_markers_continue_across_batches(self):
        out = self.run_script([self.by["thumbs"], self.by["recent_docs"]], offset=3, total=5)
        marks = [BEGIN_RE.match(l).groups() for l in out if BEGIN_RE.match(l)]
        self.assertEqual(marks, [("4", "5", "thumbs"), ("5", "5", "recent_docs")])

    def test_dry_run_prints_an_estimate_marker_per_task(self):
        out = self.run_script([self.by["thumbs"], self.by["npm"]], dry=True)
        est = [EST_RE.match(l).groups() for l in out if EST_RE.match(l)]
        self.assertEqual([e[0] for e in est], ["thumbs", "npm"])

    def test_headless_output_hides_markers(self):
        with helpers.temp_dir() as home:
            r = subprocess.run([sys.executable, "-m", "syscleaner", "--headless", "--dry-run", "--tasks",
                                "thumbs,recent_docs"], capture_output=True, text=True, cwd=str(helpers.ROOT),
                               env=dict(os.environ, HOME=home))
        self.assertNotIn("@@BEGIN", r.stdout)
        self.assertIn("▶", r.stdout)


@unittest.skipUnless(shutil.which("ps"), "needs procps")
class RunningHelperTests(unittest.TestCase):
    def running(self, names):
        return subprocess.run(["bash", "-c", PRELUDE + f"running {names}"]).returncode == 0

    def test_detects_a_live_process_and_ignores_missing_ones(self):
        name = f"sc{os.getpid()}"                      # unique and short (process names are cut at 15 chars)
        with helpers.temp_dir() as d:
            fake = os.path.join(d, name)
            os.symlink(shutil.which("sleep"), fake)
            self.assertFalse(self.running(f"{name} {name}-bin"))
            proc = subprocess.Popen([fake, "30"])
            try:
                for _ in range(30):                    # wait until ps can see the new process
                    if self.running(name):
                        break
                    subprocess.run(["sleep", "0.1"])
                self.assertTrue(self.running(f"nothing-here {name}"))
            finally:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    unittest.main()
