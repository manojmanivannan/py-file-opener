"""Command-line entry point for py-file-opener.

Routes file paths to the picker (fzf, with an inquirer fallback), records
frecency, and opens the selection in the user's editor (or xdg-open for
non-text files).
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from py_file_opener.entries import build_entries
from py_file_opener.frecency import (
    bump,
    load_records,
    prune,
    rank,
    recent,
    save_records,
)
from py_file_opener.model import Config, __version__
from py_file_opener.opener import open_paths
from py_file_opener.picker import PickerCancelled, main_select

CACHE_SUBDIR = "py-file-opener"
HISTORY_KEEP = 500


def build_config(args: argparse.Namespace) -> Config:
    cache_base = os.environ.get("XDG_CACHE_HOME")
    cache_dir = (Path(cache_base) if cache_base else Path.home() / ".cache") / CACHE_SUBDIR
    return Config(editor=args.editor or None, cache_dir=cache_dir, no_preview=args.no_preview)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py-file-opener",
        description="Interactively pick and open files in your terminal editor.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("files", nargs="*", metavar="PATH", help="file paths to pick from")
    parser.add_argument("--editor", metavar="CMD", help="editor override, e.g. \"code -w\"")
    parser.add_argument("--no-preview", action="store_true", help="disable the fzf preview pane")
    parser.add_argument(
        "--recent",
        nargs="?",
        const="10",
        metavar="N",
        help="list the N most recently opened paths (default 10)",
    )
    parser.add_argument(
        "--open-recent",
        action="store_true",
        help="open the most recently opened file directly",
    )
    return parser


def valid_files(paths: List[str]) -> List[str]:
    files: List[str] = []
    for path in paths:
        if os.path.isdir(path):
            print(f"skipping directory: {path}", file=sys.stderr)
        else:
            files.append(path)
    return files


def run_recent(args: argparse.Namespace, config: Config) -> int:
    records = load_records(config.cache_dir)
    if args.open_recent:
        paths = recent(records, 1)
        if not paths:
            print("no history yet", file=sys.stderr)
            return 1
        print("Opening:", paths[0])
        return open_paths(paths, config)
    paths = recent(records, int(args.recent or 10))
    for path in paths:
        print(path)
    return 0


def main() -> int:
    args = build_parser().parse_args()
    config = build_config(args)
    files = valid_files(args.files)

    if args.recent or args.open_recent:
        return run_recent(args, config)

    if not files:
        print("py-file-opener: no input files (or use --recent / --open-recent)", file=sys.stderr)
        return 1

    records = load_records(config.cache_dir)
    entries = rank(build_entries(files, config), records)
    if not entries:
        print("py-file-opener: no valid files to open", file=sys.stderr)
        return 1

    if len(entries) == 1:
        chosen = [entries[0].abs_path]
    else:
        try:
            chosen = main_select(entries, config)
        except PickerCancelled:
            return 130
        if not chosen:
            return 130

    save_records(
        config.cache_dir,
        prune(bump(records, chosen)),
    )
    return open_paths(chosen, config)


if __name__ == "__main__":
    sys.exit(main())