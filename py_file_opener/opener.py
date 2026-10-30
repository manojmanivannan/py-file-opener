"""Editor / xdg-open launching for py-file-opener.

resolve_editor() picks the editor command line (config.editor -> $VISUAL ->
$EDITOR -> "vim"), always shlex.split so multi-token values like "code -w"
work.  is_gui_open() classifies a path by extension only.  edit() runs the
editor synchronously and propagates its exit code; open_paths() splits a
selection per file and hands GUI-suitable files to xdg-open fire-and-forget
(never waited on, so GUI apps cannot block the CLI) while everything else
goes to the editor.  All side-effectful callables (subprocess runner,
Popen launcher, shutil.which, environ mapping) are default-injected
parameters so tests can pass fakes without monkeypatching.
"""

import os
import shlex
import shutil
import subprocess
import sys
from typing import List, Mapping, Optional

from py_file_opener.model import Config


_IMAGE_EXTS = frozenset(
    ["png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp", "tiff", "tif", "avif", "heic"]
)
_DOC_EXTS = frozenset(
    ["pdf", "ps", "dvi", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf", "epub"]
)
_MEDIA_EXTS = frozenset(
    ["mp3", "flac", "ogg", "oga", "opus", "wav", "m4a", "mp4", "mkv", "avi", "mov", "webm"]
)
_GUI_EXTS = _IMAGE_EXTS | _DOC_EXTS | _MEDIA_EXTS

# Editors whose "-p" flag opens each file in its own tab (vim family only).
_TAB_EDITORS = frozenset(["vim", "nvim", "gvim", "view"])


def resolve_editor(
    config: Config,
    environ: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """Return the editor argv, honouring config.editor then $VISUAL / $EDITOR.

    Multi-token values ("code -w") are shlex.split into argv tokens.
    """
    env = os.environ if environ is None else environ
    candidate = ""
    if config.editor is not None and config.editor.strip():
        candidate = config.editor.strip()
    else:
        for name in ("VISUAL", "EDITOR"):
            value = env.get(name)
            if value is not None and value.strip():
                candidate = value.strip()
                break
    if not candidate:
        candidate = "vim"
    return shlex.split(candidate)


def is_gui_open(path: str) -> bool:
    """True if the path's extension marks a file a GUI viewer should open.

    Extension lookup only (no file(1)); case-insensitive; dotfiles and
    extension-less paths are False.
    """
    ext = os.path.splitext(path)[1]
    if not ext:
        return False
    return ext[1:].lower() in _GUI_EXTS


def _arg_message(paths: List[str]) -> str:
    if len(paths) == 1:
        return paths[0]
    return ", ".join(os.path.basename(p) for p in paths)


def edit(
    paths: List[str],
    config: Config,
    runner=subprocess.call,
    which=shutil.which,
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    """Open paths in the resolved editor; synchronous, returns its exit code."""
    argv = resolve_editor(config, environ)
    if not which(argv[0]):
        print("py-file-opener: editor not found on PATH: " + argv[0], file=sys.stderr)
        return 127
    if len(paths) > 1 and os.path.basename(argv[0]) in _TAB_EDITORS:
        argv = argv[:1] + ["-p"] + argv[1:]
    print("Opening:", _arg_message(paths))
    return runner(argv + paths)


def open_paths(
    paths: List[str],
    config: Config,
    runner=subprocess.call,
    launcher=subprocess.Popen,
    which=shutil.which,
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    """Split a selection per file: GUI files to xdg-open (fire-and-forget),
    the rest to the editor.  Returns the editor's exit code (0 if none ran).
    """
    gui = [p for p in paths if is_gui_open(p)]
    text = [p for p in paths if not is_gui_open(p)]

    # Resolve xdg-open availability up front so a missing binary degrades
    # GUI files into the editor BEFORE the editor is ever launched.
    xdg_open = which("xdg-open") if gui else None
    remaining = []
    for path in gui:
        if xdg_open:
            launcher(
                ["xdg-open", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            print(
                "py-file-opener: xdg-open not found, opening in editor: " + path,
                file=sys.stderr,
            )
            remaining.append(path)  # degrade, never drop the file
    if remaining:
        text.extend(remaining)

    if text:
        return edit(text, config, runner, which, environ)
    return 0