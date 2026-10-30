"""Interactive file selection: fzf first (fast, multi-select, previewed), inquirer fallback.

Row format piped to fzf is five TAB-separated columns
(abs_path, rel_path, size_h, mtime_h, git_badge); fzf displays and matches only
column 2 onward (--nth/--with-nth=2..) so the hidden abs_path is never fuzzed against.
Selection results are always returned as abs paths, in the order the user picked them.
PickerCancelled is raised on any cancel/failure path; the CLI maps it to exit 130.
"""

import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from py_file_opener.model import Config, Entry


class PickerCancelled(Exception):
    """User cancelled the picker (ESC, Ctrl-C, no match) or it could not run."""


def _row(entry: Entry, rel_width: int, size_width: int) -> str:
    """Render one Entry with columns padded to the given batch widths.

    Padding (rel left-aligned, size right-aligned) is what makes the fzf
    columns line up -- fzf renders tabs as a fixed gap but never aligns
    variable-width fields itself.
    """
    return "{abs}\t{rel}\t{size}\t{mtime}\t{git}".format(
        abs=entry.abs_path,
        rel=entry.rel_path.ljust(rel_width),
        size=entry.size_h.rjust(size_width),
        mtime=entry.mtime_h,
        git=entry.git_badge,
    )


def build_row(entry: Entry) -> str:
    """Render one Entry as the five-column TAB-separated row fed to fzf.

    Batch-level column padding is applied by build_rows; a lone row pads to
    its own field widths, i.e. is unpadded.
    """
    return _row(entry, len(entry.rel_path), len(entry.size_h))


def build_rows(entries: List[Entry]) -> List[str]:
    """Render entries as rows with columns padded to batch-wide widths."""
    rel_width = max(len(entry.rel_path) for entry in entries)
    size_width = max(len(entry.size_h) for entry in entries)
    return [_row(entry, rel_width, size_width) for entry in entries]


def build_fzf_command(entries: List[Entry], config: Config, fzf_path: str) -> List[str]:
    """Build the fzf argv. Flag order is stable; tests assert this exact list.

    Note: the --preview value intentionally contains literal {s1} and is built with
    plain string concatenation (never an f-string), so the braces reach fzf verbatim.
    """
    argv = [
        fzf_path,
        "--read0",
        "--print0",
        "--multi",
        "--delimiter=\t",
        "--nth=2..",
        "--with-nth=2..",
        "--header=[TAB] mark · [ENTER] open · [ESC] cancel",
        "--no-multi-line",
        "--tiebreak=length",
    ]
    if not config.no_preview:
        argv.append("--preview-window=right,50%,border-left")
        argv.append(
            "--preview=sh -c 'bat --color=always {s1} 2>/dev/null"
            " || head -n 200 {s1}'"
        )
    return argv


def parse_fzf_output(output: bytes) -> List[str]:
    """Parse fzf's --print0 stdout into abs paths, preserving tab (selection) order."""
    abs_paths = []
    for row in output.split(b"\x00"):
        if not row:
            continue
        first = row.split(b"\t", 1)[0]
        abs_paths.append(first.decode("utf-8"))
    return abs_paths


def _run_fzf(rows: List[str], cmd: List[str]) -> Tuple[bytes, int]:
    """Feed rows (NUL-terminated) to fzf and return (raw stdout bytes, returncode).

    Module-level seam so tests can exercise the pipe/format logic without launching fzf.
    """
    payload = b"".join(row.encode("utf-8") + b"\x00" for row in rows)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, _ = proc.communicate(payload)
    return out, proc.returncode


def main_select(
    entries: List[Entry],
    config: Config,
    which=shutil.which,
    stdin_isatty: Optional[bool] = None,
    stdout_isatty: Optional[bool] = None,
) -> List[str]:
    """Return the selected abs paths (in selection order) or raise PickerCancelled."""
    if not entries:
        raise PickerCancelled("nothing to select")

    if stdin_isatty is None:
        stdin_isatty = sys.stdin.isatty()
    if stdout_isatty is None:
        stdout_isatty = sys.stdout.isatty()

    fzf_path = which("fzf")
    if fzf_path and stdin_isatty and stdout_isatty:
        cmd = build_fzf_command(entries, config, fzf_path)
        try:
            out, code = _run_fzf(build_rows(entries), cmd)
        except OSError as exc:
            print("picker: fzf failed to run: %s" % exc, file=sys.stderr)
            raise PickerCancelled(str(exc))
        if code == 0:
            return parse_fzf_output(out)
        if code in (1, 130):
            raise PickerCancelled("cancelled (fzf exit %d)" % code)
        print("picker: fzf exited %d" % code, file=sys.stderr)
        raise PickerCancelled("fzf exit %d" % code)

    if not (stdin_isatty and stdout_isatty):
        print("picker: non-interactive stream", file=sys.stderr)
    return _inquirer_select(entries)


def _inquirer_select(entries: List[Entry]) -> List[str]:
    """Multi-select via inquirer.Checkbox, mapped back to abs paths. Import is lazy."""
    try:
        import inquirer
    except (KeyboardInterrupt, Exception) as exc:  # noqa: B902 - missing import = cancel
        raise PickerCancelled(str(getattr(exc, "args", [None])[0] or exc))

    display_to_abs = {}
    choices = []
    for entry in entries:
        display = "{rel}  ({size}, {mtime})".format(
            rel=entry.rel_path, size=entry.size_h, mtime=entry.mtime_h
        )
        if display in display_to_abs:  # duplicate rel_paths: disambiguate with abs_path
            display = "{abs}  ({size}, {mtime})".format(
                abs=entry.abs_path, size=entry.size_h, mtime=entry.mtime_h
            )
        display_to_abs[display] = entry.abs_path
        choices.append(display)

    question = inquirer.Checkbox(
        "files",
        message="Space to mark · Enter to open · Ctrl-C to cancel",
        choices=choices,
    )
    try:
        answers = inquirer.prompt([question])
        selected = answers["files"] if answers else None
    except (KeyboardInterrupt, Exception) as exc:  # noqa: B902 - any prompt failure = cancel
        raise PickerCancelled(str(getattr(exc, "args", [None])[0] or exc))
    if not selected:
        raise PickerCancelled("no files selected")
    return [display_to_abs[display] for display in selected]