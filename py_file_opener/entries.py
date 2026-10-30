"""Build display entries from raw path lists.

Turns the raw paths given on the CLI into `Entry` rows: absolute/relative
path pair, human size, human mtime, and a git status badge (when the common
root sits inside a git working tree).
"""

import os
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional, Tuple

from .model import Config, Entry

_SIZE_UNITS = ("", "K", "M", "G")


def common_and_rel(paths: List[str]) -> Tuple[str, List[Tuple[str, str]]]:
    """Return the common root plus (abs_path, rel_path) pairs for `paths`.

    Paths are made absolute first (so mixed relative/absolute input works),
    and symlinks are preserved as spelled (no realpath). The common root may
    be a base root such as "/" when the paths do not really share a tree.
    """
    if not paths:
        raise ValueError("no paths given")
    abs_paths = [os.path.abspath(p) for p in paths]
    root = os.path.commonpath(abs_paths)
    if root in abs_paths:
        # A single (or fully-duplicated) path list yields the file itself as
        # the common path; keep the root a directory for display sanity.
        root = os.path.dirname(root)
    return root, [(a, os.path.relpath(a, root)) for a in abs_paths]


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    unit_index = 0
    while value >= 1024.0 and unit_index < len(_SIZE_UNITS) - 1:
        value /= 1024.0
        unit_index += 1
    text = f"{value:.1f}" if value % 1.0 else str(int(value))
    return f"{text}{_SIZE_UNITS[unit_index]}"


def _human_mtime(timestamp: float) -> str:
    return time.strftime("%b %d", time.localtime(timestamp))


def _git_toplevel(run: Callable, root: str) -> Optional[str]:
    """Return the git toplevel for `root`, or None when outside a repo."""
    try:
        proc = run(
            ["git", "-C", root, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    toplevel = proc.stdout.strip()
    return toplevel or None


def _git_status_map(run: Callable, toplevel: str) -> Dict[str, str]:
    """Map repo-relative paths to status badges ("~" untracked, "*" dirty)."""
    try:
        proc = run(
            ["git", "-C", toplevel, "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return {}
    if proc.returncode != 0:
        return {}
    badges: Dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        code = line[:2]
        path = line[2:].strip()
        if path.startswith('"') and path.endswith('"') and len(path) >= 2:
            path = path[1:-1]
        if "->" in path:
            path = path.split("->")[-1].strip()
        badges[path] = "~" if code.startswith("??") else "*"
    return badges


def _badge_for(abs_path: str, toplevel: str, badges: Dict[str, str]) -> str:
    try:
        under = os.path.commonpath([toplevel, abs_path]) == toplevel
    except ValueError:
        return ""
    if not under:
        return ""
    return badges.get(os.path.relpath(abs_path, toplevel), "")


def build_entries(
    paths: List[str],
    config: Config,
    stat_fn: Callable[[str], os.stat_result] = os.stat,
    run: Callable = subprocess.run,
) -> List[Entry]:
    """Build `Entry` rows for `paths`, dropping missing or tab-bearing ones."""
    del config  # accepted for signature stability; entries carry no config state
    _root, pairs = common_and_rel(paths)

    usable: List[Tuple[str, str, os.stat_result]] = []
    for abs_path, rel_path in pairs:
        if "\t" in rel_path or "\t" in abs_path:
            print(f"py-file-opener: skipping tab in path: {abs_path}", file=sys.stderr)
            continue
        try:
            st = stat_fn(abs_path)
        except OSError:
            print(f"py-file-opener: skipping missing: {abs_path}", file=sys.stderr)
            continue
        usable.append((abs_path, rel_path, st))
    if not usable:
        return []

    # _root is directory-guaranteed by common_and_rel (single-file input
    # falls back to dirname), so it is safe to hand to git -C.
    toplevel = _git_toplevel(run, _root)
    badges: Dict[str, str] = {}
    if toplevel is None:
        badge_map: Dict[str, str] = {}
    else:
        badge_map = _git_status_map(run, toplevel)

    entries: List[Entry] = []
    for abs_path, rel_path, st in usable:
        badge = _badge_for(abs_path, toplevel, badge_map) if toplevel else ""
        entries.append(
            Entry(
                abs_path=abs_path,
                rel_path=rel_path,
                size_h=_human_size(st.st_size),
                mtime_h=_human_mtime(st.st_mtime),
                git_badge=badge,
            )
        )
    return sorted(entries, key=lambda e: e.rel_path.lower())