# py-file-opener

A simple CLI tool to interactively open files in Vim, especially useful when working with multiple files in a directory. Built with Python 3.11+ and uses [uv](https://github.com/astral-sh/uv) for fast dependency management.

## Features
- Interactive file selection using a terminal menu (via `inquirer`)
- Opens selected file(s) in Vim
- Highlights common directory paths
- Designed for fast workflows in the terminal

## Requirements
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (for dependency management)
- Vim (or change the editor in `main.py`)


## Installation
You can install directly from GitHub using pip:
```sh
pip install git+https://github.com/yourusername/py-file-opener.git
```

## Usage
After installation, use the CLI command:
```sh
py-file-opener <directory> <file1> <file2> ...
```
- If only one file is provided, it opens directly in Vim.
- If multiple files are provided, you'll be prompted to select which one to open.

## Example
```sh
python main.py ./src file1.py file2.py file3.py
```

## Development
- Dependencies are managed with [uv](https://github.com/astral-sh/uv).
- Main dependencies: `inquirer`
- To add more dependencies:
  ```sh
  uv pip install <package>
  ```

## License
MIT
