"""Shared test helpers: import path and an isolated config/state area (tests never touch the real ~)."""
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The tests compare English texts, so the program language is pinned to English no matter which locale the
# developer's machine uses. Tests of the language logic itself run in a clean subprocess (see clean_env()).
os.environ["SYSCLEANER_LANG"] = "en"

# Everything the app reads/writes by XDG convention goes to a throw-away folder.
_SANDBOX = tempfile.mkdtemp(prefix="syscleaner-tests-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SANDBOX, "config")
os.environ["XDG_STATE_HOME"] = os.path.join(_SANDBOX, "state")


@contextmanager
def temp_dir():
    with tempfile.TemporaryDirectory(prefix="syscleaner-t-") as d:
        yield d


@contextmanager
def env(**values):
    """Temporarily set (or with None remove) environment variables."""
    old = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def clean_env(extra=None):
    """Environment for a subprocess without any locale / SysCleaner variables."""
    e = dict(os.environ)
    for k in ("SYSCLEANER_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        e.pop(k, None)
    e.update(extra or {})
    return e
