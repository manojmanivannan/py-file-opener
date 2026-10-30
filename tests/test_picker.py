"""Contract tests for py_file_opener.picker."""

import sys

import pytest

from conftest import make_config, make_entry
from py_file_opener.picker import (
    PickerCancelled,
    build_fzf_command,
    build_row,
    main_select,
    parse_fzf_output,
)

_REQUIRED_FLAGS = [
    "--read0",
    "--print0",
    "--multi",
    "--delimiter=\t",
    "--nth=2..",
    "--with-nth=2..",
]


class _RunFzfStub:
    """Record the rows/cmd handed to _run_fzf and return fixed output."""

    def __init__(self, output=b"", returncode=0):
        self.output = output
        self.returncode = returncode
        self.calls = []

    def __call__(self, rows, cmd):
        self.calls.append((rows, cmd))
        return self.output, self.returncode


class _FakeInquirer:
    """sys.modules['inquirer'] stand-in: no real UI, canned answers."""

    def __init__(self, answers=None):
        self.answers = answers
        self.prompts = []

    def Checkbox(self, name, message=None, choices=None):
        self.prompts.append(choices)
        return object()

    def prompt(self, questions):
        return self.answers


# --- build_row --------------------------------------------------------------


def test_build_row_exact_five_columns():
    entry = make_entry(
        "f.py",
        abs_path="/abs/f.py",
        rel_path="f.py",
        size_h="1K",
        mtime_h="Mar 07",
        git_badge="*",
    )

    assert build_row(entry) == "/abs/f.py\tf.py\t1K\tMar 07\t*"


def test_build_row_empty_badge_keeps_fifth_column():
    entry = make_entry("f.py", abs_path="/abs/f.py", rel_path="f.py", git_badge="")

    assert build_row(entry) == "/abs/f.py\tf.py\t1K\tMar 07\t"


# --- build_fzf_command ------------------------------------------------------


def test_build_fzf_command_required_flags_and_preview(tmp_path):
    config = make_config(no_preview=False)
    entries = [make_entry("f.py")]

    cmd = build_fzf_command(entries, config, "/usr/bin/fzf")

    assert cmd[0] == "/usr/bin/fzf"
    for flag in _REQUIRED_FLAGS:
        assert flag in cmd
    # preview flags are the final two elements, in this order
    assert cmd[-2] == "--preview-window=right,50%,border-left"
    assert cmd[-1].startswith("--preview=")
    preview_value = cmd[-1]
    assert "{s1}" in preview_value
    assert "{1}" not in preview_value


def test_build_fzf_command_no_preview_omits_preview_flags(tmp_path):
    config = make_config(no_preview=True)
    entries = [make_entry("f.py")]

    cmd = build_fzf_command(entries, config, "/usr/bin/fzf")

    assert not any(str(flag).startswith("--preview") for flag in cmd)
    for flag in _REQUIRED_FLAGS:
        assert flag in cmd


def test_build_fzf_command_no_omit_rule_is_only_about_preview(tmp_path):
    """no_preview removes exactly the two preview elements, nothing else."""
    full = build_fzf_command([make_entry("f.py")], make_config(no_preview=False), "fzf")
    trimmed = build_fzf_command([make_entry("f.py")], make_config(no_preview=True), "fzf")

    assert trimmed == full[:-2]


# --- parse_fzf_output -------------------------------------------------------


def test_parse_fzf_output_splits_nul_rows():
    output = (
        b"/abs/a\trel a\t1K\tMar 07\t*\x00"
        b"/abs/b\trel b\t2K\tApr 07\t\x00"
    )

    assert parse_fzf_output(output) == ["/abs/a", "/abs/b"]


def test_parse_fzf_output_preserves_selection_order_and_ignores_blanks():
    output = b"/abs/b\tb\x00\x00/abs/a\ta\x00/abs/b\tb2\x00"

    assert parse_fzf_output(output) == ["/abs/b", "/abs/a", "/abs/b"]


def test_parse_fzf_output_empty_bytes():
    assert parse_fzf_output(b"") == []


# --- main_select ------------------------------------------------------------


def _entries():
    return [
        make_entry("a.py", abs_path="/abs/a.py", rel_path="a.py", size_h="1K", mtime_h="Mar 07"),
        make_entry("b.py", abs_path="/abs/b.py", rel_path="b.py", size_h="2K", mtime_h="Apr 08"),
    ]


def test_main_select_missing_fzf_falls_back_to_inquirer(monkeypatch):
    run_fzf = _RunFzfStub()
    monkeypatch.setattr("py_file_opener.picker._run_fzf", run_fzf)
    monkeypatch.setitem(sys.modules, "inquirer", _FakeInquirer(answers=None))

    with pytest.raises(PickerCancelled):
        main_select(
            _entries(),
            make_config(),
            which=lambda name: None,
            stdin_isatty=False,
            stdout_isatty=True,
        )

    assert run_fzf.calls == []  # fzf was never attempted


def test_main_select_non_interactive_stdout_falls_back(monkeypatch, capsys):
    run_fzf = _RunFzfStub()
    monkeypatch.setattr("py_file_opener.picker._run_fzf", run_fzf)
    monkeypatch.setitem(sys.modules, "inquirer", _FakeInquirer(answers=None))

    with pytest.raises(PickerCancelled):
        main_select(
            _entries(),
            make_config(),
            which=lambda name: "/usr/bin/" + name,
            stdin_isatty=True,
            stdout_isatty=False,
        )

    assert run_fzf.calls == []
    assert "non-interactive" in capsys.readouterr().err


def test_main_select_rc_zero_returns_abs_paths_in_fzf_order(monkeypatch):
    output = b"/abs/b\tb.py\t2K\tApr 08\t\x00/abs/a\ta.py\t1K\tMar 07\t\x00"
    run_fzf = _RunFzfStub(output=output, returncode=0)
    monkeypatch.setattr("py_file_opener.picker._run_fzf", run_fzf)

    chosen = main_select(
        _entries(),
        make_config(no_preview=False),
        which=lambda name: "/usr/bin/" + name,
        stdin_isatty=True,
        stdout_isatty=True,
    )

    assert chosen == ["/abs/b", "/abs/a"]
    rows, cmd = run_fzf.calls[0]
    assert rows == [build_row(e) for e in _entries()]
    assert cmd[0] == "/usr/bin/fzf"
    assert "--preview-window=right,50%,border-left" in cmd


@pytest.mark.parametrize("returncode", [1, 130, 2])
def test_main_select_nonzero_rc_raises_cancelled(monkeypatch, returncode):
    run_fzf = _RunFzfStub(output=b"/abs/a\ta\x00", returncode=returncode)
    monkeypatch.setattr("py_file_opener.picker._run_fzf", run_fzf)

    with pytest.raises(PickerCancelled):
        main_select(
            _entries(),
            make_config(),
            which=lambda name: "/usr/bin/" + name,
            stdin_isatty=True,
            stdout_isatty=True,
        )


def test_main_select_inquirer_answers_map_back_to_abs_paths(monkeypatch):
    entries = _entries()
    fake = _FakeInquirer(
        answers={
            "files": [
                "{rel}  ({size}, {mtime})".format(
                    rel=entries[1].rel_path, size=entries[1].size_h, mtime=entries[1].mtime_h
                ),
                "{rel}  ({size}, {mtime})".format(
                    rel=entries[0].rel_path, size=entries[0].size_h, mtime=entries[0].mtime_h
                ),
            ]
        }
    )
    monkeypatch.setitem(sys.modules, "inquirer", fake)

    chosen = main_select(
        entries, make_config(), which=lambda name: None, stdin_isatty=False,
    )

    # selection order preserved, mapped back through the display strings
    assert chosen == ["/abs/b.py", "/abs/a.py"]
    assert fake.prompts and len(fake.prompts[0]) == 2


def test_main_select_empty_entries_raises_immediately(monkeypatch):
    monkeypatch.setitem(sys.modules, "inquirer", _FakeInquirer(answers=None))

    with pytest.raises(PickerCancelled):
        main_select([], make_config(), which=lambda name: "/usr/bin/" + name)