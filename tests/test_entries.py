"""Contract tests for py_file_opener.entries."""

import os
import time
from types import SimpleNamespace

import pytest

from conftest import NOW, make_config, make_stat_result
from py_file_opener.entries import build_entries, common_and_rel


def _quiet_git_run(returncode=1, stdout=""):
    """A `run` stub that (by default) reports 'not inside a git repo'."""

    def _run(cmd, **kwargs):
        return SimpleNamespace(stdout=stdout, returncode=returncode, stderr="")

    return _run


# --- common_and_rel ---------------------------------------------------------


def test_common_and_rel_old_bug_repro(tmp_path):
    """The exact v0.1 bug: repeated component in the sub-tree is NOT a root echo.

    String-matching-based root trimming once reassembled "<root>/y/x/f.py" by
    replacing the basename; commonpath must keep these two paths apart cleanly.
    """
    root = tmp_path / "x"
    (root / "y" / "x").mkdir(parents=True)
    (root / "z" / "x").mkdir(parents=True)
    f1 = root / "y" / "x" / "f.py"
    f2 = root / "z" / "x" / "g.py"
    f1.write_text("f")
    f2.write_text("g")

    shared_root, pairs = common_and_rel([str(f1), str(f2)])

    assert shared_root == str(root)
    mapping = dict(pairs)
    assert mapping[str(f1)] == "y/x/f.py"
    assert mapping[str(f2)] == "z/x/g.py"


def test_common_and_rel_path_repeating_root_components(tmp_path):
    """Doubled root components survive: /a/b/a/b/f.py keeps its full rel path.

    The old v0.1 `str.replace` stripping collapsed repeated root components
    (turning /a/b/a/b/f.py into f.py under the wrong root); the commonpath
    implementation must not.
    """
    root = tmp_path / "a" / "b"
    (root / "a" / "b").mkdir(parents=True)
    target = root / "a" / "b" / "f.py"
    target.write_text("f")
    sibling = root / "c" / "g.py"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("g")

    shared_root, pairs = common_and_rel([str(target), str(sibling)])

    assert shared_root == str(root)
    mapping = dict(pairs)
    assert mapping[str(target)] == os.path.join("a", "b", "f.py")
    assert mapping[str(sibling)] == os.path.join("c", "g.py")


def test_common_and_rel_single_path():
    """Single path: root falls back to its dirname (kept a directory)."""
    root, pairs = common_and_rel(["/some/where/f.py"])

    assert len(pairs) == 1
    abs_path, rel_path = pairs[0]
    assert abs_path == os.path.abspath("/some/where/f.py")
    assert root == os.path.dirname(abs_path)
    assert not os.path.isabs(rel_path)
    assert os.path.join(root, rel_path) == abs_path


def test_common_and_rel_mixed_rel_abs_does_not_raise():
    """Raw relative input alongside absolute: abspath-first must normalize."""
    root, pairs = common_and_rel(["relative/f.py", "/etc/hostname"])

    assert len(pairs) == 2
    for abs_path, rel_path in pairs:
        assert os.path.isabs(abs_path)
        assert not os.path.isabs(rel_path)
        assert os.path.join(root, rel_path) == abs_path


def test_common_and_rel_empty_paths_raises():
    with pytest.raises(ValueError):
        common_and_rel([])


# --- build_entries ----------------------------------------------------------


def test_build_entries_size_h(tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 5120)
    small = tmp_path / "small.bin"
    small.write_bytes(b"abcde")

    entries = build_entries(
        [str(big), str(small)], make_config(), run=_quiet_git_run()
    )
    by_rel = {e.rel_path: e for e in entries}

    assert "K" in by_rel["big.bin"].size_h
    assert "K" not in by_rel["small.bin"].size_h


def test_build_entries_mtime_h_matches_stat_stub(tmp_path):
    target = tmp_path / "f.py"
    target.write_text("f")

    def stat_fn(path):
        return make_stat_result(size=100, mtime=NOW)

    entries = build_entries(
        [str(target)], make_config(), stat_fn=stat_fn, run=_quiet_git_run()
    )

    assert len(entries) == 1
    assert entries[0].mtime_h == time.strftime("%b %d", time.localtime(NOW))


def test_build_entries_missing_path_skipped(tmp_path, capsys):
    good = tmp_path / "good.py"
    good.write_text("g")
    missing = str(tmp_path / "missing.py")

    def stat_fn(path):
        if path == missing:
            raise FileNotFoundError(2, "No such file or directory", path)
        return make_stat_result(size=1, mtime=NOW)

    entries = build_entries(
        [missing, str(good)], make_config(), stat_fn=stat_fn, run=_quiet_git_run()
    )

    assert [e.rel_path for e in entries] == ["good.py"]
    assert "missing" in capsys.readouterr().err


def test_build_entries_tab_in_path_dropped(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("g")
    tabbed = str(tmp_path / "bad\tpath.py")

    entries = build_entries(
        [tabbed, str(good)], make_config(), run=_quiet_git_run()
    )

    assert [e.rel_path for e in entries] == ["good.py"]


def test_build_entries_tab_flagged_to_stderr(tmp_path, capsys):
    good = tmp_path / "good.py"
    good.write_text("g")
    tabbed = str(tmp_path / "bad\tpath.py")

    build_entries([tabbed, str(good)], make_config(), run=_quiet_git_run())

    err = capsys.readouterr().err
    assert "tab" in err.lower()


def test_build_entries_leaves_non_git_paths_unbadged(tmp_path):
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("a")
    f2.write_text("b")
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0, stderr="")

    entries = build_entries([str(f1), str(f2)], make_config(), run=run)

    assert all(e.git_badge == "" for e in entries)
    # 0..2 git invocations are the contract ceiling (rev-parse + porcelain).
    assert 0 <= len(calls) <= 2


def test_build_entries_git_badges_modified_and_untracked(tmp_path):
    f_mod = tmp_path / "y.py"
    f_untracked = tmp_path / "z.py"
    f_outside = tmp_path / "w.py"
    for f in (f_mod, f_untracked, f_outside):
        f.write_text("f")
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if "rev-parse" in cmd:
            return SimpleNamespace(stdout=str(tmp_path) + "\n", returncode=0, stderr="")
        return SimpleNamespace(
            stdout=" M y.py\n?? z.py\n", returncode=0, stderr=""
        )

    entries = build_entries(
        [str(f_mod), str(f_untracked), str(f_outside)], make_config(), run=run
    )
    badges = {e.rel_path: e.git_badge for e in entries}

    assert len(calls) <= 2
    assert badges["y.py"] == "*"   # modified (porcelain " M")
    assert badges["z.py"] == "~"   # untracked (porcelain "??")
    assert badges["w.py"] == ""    # not in the porcelain → clean


def test_build_entries_sorts_by_rel_path_case_insensitive(tmp_path):
    zeta = tmp_path / "Zeta.py"
    alpha = tmp_path / "alpha.py"
    zeta.write_text("1")
    alpha.write_text("2")

    entries = build_entries([str(zeta), str(alpha)], make_config(), run=_quiet_git_run())

    # ASCII order would put "Zeta.py" first (Z < a); case-insensitive must not.
    assert [e.rel_path for e in entries] == ["alpha.py", "Zeta.py"]