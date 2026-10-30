# py-file-opener

py-file-opener is a terminal tool for interactively picking one or several files
from a set and opening them in your editor. It is built for zsh `fo()`-style
workflows: find candidate files by pattern, hand them to the picker, choose
interactively, and edit.

## Features

- fzf-powered selection with live filtering, when `fzf` is on `PATH`
- Preview pane while picking (`bat` when available, `head` otherwise);
  disable with `--no-preview`
- Multi-select (TAB to mark), opened as editor tabs with `vim -p`
- Editor chain: `--editor` flag → `$VISUAL` → `$EDITOR` → `vim`; multi-token
  values such as `"code -w"` are supported
- Non-text files (images, PDFs/office docs, audio/video) open via `xdg-open`,
  non-blocking, even inside a multi-select
- Frecency-sorted picker (frequently and recently opened files rank higher),
  backed by `~/.cache/py-file-opener/history.json`
- Graceful degradation: without `fzf` a checkbox UI (via `inquirer`) is used;
  without `xdg-open` the file is routed to the editor instead. All optional
  tools are plain `PATH` lookups, never hard build dependencies.

## Usage

```sh
py-file-opener <path> [<path> ...]
```

Each positional argument must be an existing file. A directory is not accepted
as a positional — expand it yourself before calling, e.g. with `fd`:

```sh
py-file-opener $(fd -e py)
```

| Flag | Effect |
| --- | --- |
| `--editor CMD` | Editor to launch, e.g. `--editor "code -w"` |
| `--no-preview` | Disable the preview pane |
| `--recent [N]` | List the most recently opened paths (default N=10) |
| `--open-recent` | Directly open the most recently opened file |
| `--version` | Print the version and exit |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success (the editor's own exit code is propagated) |
| 1 | Usage error |
| 130 | Cancelled (ESC or Ctrl-C in the picker) |

## Example session

```zsh
# pick from files changed on this branch, with preview
$ git diff --name-only | xargs py-file-opener
> Select one or more files (TAB to mark, ENTER to open)
  │ src/cli.py                │ src/cli.py (preview)
  │ [x] src/main.py           │ def main():
  │ [x] src/preview.py        │     ...
  ↓ src/history.py            │
  ...
# ENTER opens both marked files as tabs
$ vim -p src/main.py src/preview.py
```

## Notes

- The preview pane uses `bat` and falls back to plain `head`.
- Inside a git repo, picker entries carry a status badge: `*` for modified
  files, `~` for untracked ones.
- History lives in `~/.cache/py-file-opener/history.json`, is capped at 500
  entries, and stores only absolute paths.

## Development

```sh
uv sync
uv run pytest    # tests live in tests/
```

## Nix packaging

py-file-opener is built with `buildPythonApplication` in a dotfiles repo.
Runtime companions (`fzf`, `bat`, `xdg-open`, `vim`, `git`) are ordinary
`PATH` lookups resolved at call time — no `wrapProgram`, no extra Python
dependencies.