"""Contract tests for py_file_opener.opener."""

import subprocess

import pytest

from conftest import make_config
from py_file_opener.opener import edit, is_gui_open, open_paths, resolve_editor


class _Recorder:
    """Callable that records argv (+ kwargs) and returns a fixed exit code."""

    def __init__(self, returncode=0):
        self.calls = []
        self.returncode = returncode

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.returncode


def _which_stub(missing=()):
    """A shutil.which stand-in: every binary resolves except `missing` names."""

    def _which(name):
        if name in missing:
            return None
        return "/usr/bin/" + name

    return _which


# --- resolve_editor ---------------------------------------------------------


def test_resolve_editor_prefers_config_editor_shlex_split():
    argv = resolve_editor(make_config(editor="code -w"), environ={})

    assert argv == ["code", "-w"]


def test_resolve_editor_falls_back_to_visual():
    argv = resolve_editor(make_config(editor=None), environ={"VISUAL": "subl -w"})

    assert argv == ["subl", "-w"]


def test_resolve_editor_falls_back_to_editor_without_visual():
    argv = resolve_editor(make_config(editor=None), environ={"EDITOR": "vi"})

    assert argv == ["vi"]


def test_resolve_editor_treats_empty_env_values_as_unset():
    argv = resolve_editor(
        make_config(editor=None), environ={"VISUAL": "", "EDITOR": "  "}
    )

    assert argv == ["vim"]


def test_resolve_editor_defaults_to_vim():
    argv = resolve_editor(make_config(editor=None), environ={})

    assert argv == ["vim"]


# --- is_gui_open ------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/tmp/x/y.png", "/tmp/x/y.pdf", "/tmp/x/y.jpg", "/tmp/x/y.mp4", "/tmp/x/y.mkv"],
)
def test_is_gui_open_true_for_known_ext_sets(path):
    assert is_gui_open(path) is True


@pytest.mark.parametrize("path", ["/tmp/x/y.pdf", "/tmp/x/y.PNG", "/tmp/x/y.WebM"])
def test_is_gui_open_case_insensitive(path):
    assert is_gui_open(path) is True


@pytest.mark.parametrize(
    "path", ["/tmp/x/y.py", "/tmp/x/y.txt", "/tmp/x/y.pdfx", "/tmp/x/"]
)
def test_is_gui_open_false_for_text_and_unknown(path):
    assert is_gui_open(path) is False


@pytest.mark.parametrize("path", ["/tmp/x/noext", "/tmp/x/.hidden"])
def test_is_gui_open_false_without_extension(path):
    assert is_gui_open(path) is False


# --- edit -------------------------------------------------------------------


def test_edit_propagates_editor_exit_code():
    runner = _Recorder(returncode=7)
    config = make_config(editor="vim")

    assert edit(["/a/f.py"], config, runner=runner, which=_which_stub()) == 7
    assert runner.calls == [(["vim", "/a/f.py"], {})]


def test_edit_single_path_adds_no_tab_flag():
    runner = _Recorder()
    config = make_config(editor="vim")

    edit(["/a/f.py"], config, runner=runner, which=_which_stub())

    assert "-p" not in runner.calls[0][0]


def test_edit_two_paths_vim_gets_p_flag_before_paths():
    runner = _Recorder()
    config = make_config(editor="vim")

    edit(["/a/f1.py", "/a/f2.py"], config, runner=runner, which=_which_stub())

    assert runner.calls[0][0] == ["vim", "-p", "/a/f1.py", "/a/f2.py"]


def test_edit_vim_with_extra_args_flag_goes_right_after_editor():
    runner = _Recorder()
    config = make_config(editor="vim -u NONE")

    edit(["/a/f1.py", "/a/f2.py"], config, runner=runner, which=_which_stub())

    argv, = [c[0] for c in runner.calls]
    assert argv[0] == "vim"
    assert argv[1] == "-p"
    assert argv[2:] == ["-u", "NONE", "/a/f1.py", "/a/f2.py"]


def test_edit_code_with_two_paths_never_gets_p_flag():
    runner = _Recorder()
    config = make_config(editor="code -w")

    edit(["/a/f1.py", "/a/f2.py"], config, runner=runner, which=_which_stub())

    argv, = [c[0] for c in runner.calls]
    assert argv == ["code", "-w", "/a/f1.py", "/a/f2.py"]
    assert "-p" not in argv


def test_edit_missing_editor_returns_127(capsys):
    runner = _Recorder()
    config = make_config(editor="definitely-missing-ed")

    code = edit(
        ["/a/f.py"],
        config,
        runner=runner,
        which=lambda name: None,
    )

    assert code == 127
    assert runner.calls == []  # nothing was launched
    assert "definitely-missing-ed" in capsys.readouterr().err


# --- open_paths -------------------------------------------------------------


def test_open_paths_splits_gui_to_launcher_text_to_editor():
    runner = _Recorder(returncode=7)
    launcher = _Recorder()
    config = make_config(editor="vim")

    code = open_paths(
        ["/tmp/x/y.pdf", "/tmp/x/y.py"],
        config,
        runner=runner,
        launcher=launcher,
        which=_which_stub(),
        environ={},
    )

    assert code == 7
    assert launcher.calls == [
        (
            ["xdg-open", "/tmp/x/y.pdf"],
            {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "start_new_session": True,
            },
        )
    ]
    editor_argv, = [c[0] for c in runner.calls]
    assert editor_argv == ["vim", "/tmp/x/y.py"]
    assert "/tmp/x/y.pdf" not in editor_argv  # the pdf never reached the editor


def test_open_paths_missing_xdg_open_degrades_gui_to_editor(capsys):
    runner = _Recorder(returncode=3)
    launcher = _Recorder()
    config = make_config(editor="vim")

    code = open_paths(
        ["/tmp/x/y.pdf", "/tmp/x/y.py"],
        config,
        runner=runner,
        launcher=launcher,
        which=_which_stub(missing=("xdg-open",)),
        environ={},
    )

    assert launcher.calls == []            # launcher never attempted
    assert code == 3
    argv, = [c[0] for c in runner.calls]   # both files routed to the editor
    assert argv[0] == "vim"
    assert "/tmp/x/y.pdf" in argv and "/tmp/x/y.py" in argv
    assert "xdg-open" in capsys.readouterr().err


def test_open_paths_gui_only_never_runs_editor():
    runner = _Recorder()
    launcher = _Recorder()
    config = make_config(editor="vim")

    code = open_paths(
        ["/tmp/x/y.png", "/tmp/x/y.mkv"],
        config,
        runner=runner,
        launcher=launcher,
        which=_which_stub(),
        environ={},
    )

    assert code == 0
    assert runner.calls == []
    assert [c[0][0] for c in launcher.calls] == ["xdg-open", "xdg-open"]


def test_open_paths_gui_only_with_missing_xdg_open_still_opens_in_editor():
    runner = _Recorder(returncode=5)
    launcher = _Recorder()
    config = make_config(editor="vim")

    code = open_paths(
        ["/tmp/x/y.png"],
        config,
        runner=runner,
        launcher=launcher,
        which=_which_stub(missing=("xdg-open",)),
        environ={},
    )

    assert launcher.calls == []
    assert code == 5
    argv, = [c[0] for c in runner.calls]
    assert argv == ["vim", "/tmp/x/y.png"]