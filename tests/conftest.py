"""Shared constants and factories for the py-file-opener test suite.

Kept deliberately thin: only contract-level helpers live here so test
modules stay readable.  No fixtures with cross-test state; every helper is
side-effect free and scoped to what the caller passes in.
"""

import os
import sys
from pathlib import Path

# Bootstrap the repo root onto sys.path so the suite runs both with the
# project installed (uv sync) and straight from a source checkout.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from py_file_opener.model import Config, Entry  # noqa: E402

# Fixed epoch for deterministic frecency math (a Sunday, so %b %d = "Nov 14").
NOW = 1700000000.0

# One day in seconds, for readability in decay tests.
DAY = 86400.0


def make_entry(name="b.py", **overrides):
    """Build an Entry from a single `name` kwarg, overridable per field."""
    defaults = dict(
        abs_path="/abs/" + name,
        rel_path=name,
        size_h="1K",
        mtime_h="Mar 07",
        git_badge="",
        score=1.0,
    )
    defaults.update(overrides)
    return Entry(**defaults)


def make_stat_result(size, mtime):
    """Build an os.stat_result with a real st_size and st_mtime; rest filler.

    Uses the 10-field raw tuple form: (st_mode, st_ino, st_dev, st_nlink,
    st_uid, st_gid, st_size, st_atime, st_mtime, st_ctime).
    """
    return os.stat_result((0o100644, 0, 0, 1, 0, 0, size, mtime, mtime, mtime))


def make_config(editor=None, cache_dir=None, no_preview=False):
    """Build a Config, defaulting cache_dir to a harmless nonexistent path."""
    return Config(
        editor=editor,
        cache_dir=cache_dir if cache_dir is not None else Path("/nonexistent/py-file-opener-test"),
        no_preview=no_preview,
    )