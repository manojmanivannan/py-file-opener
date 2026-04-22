# py-file-opener

A simple CLI tool for interactively opening files in Vim, particularly useful for handling multiple files within a directory. Built with Python 3.11+ and utilizes [uv](https://github.com/astral-sh/uv) for efficient dependency management.

## Features
- Interactive file selection via a terminal menu (using `inquirer`)
- Opens selected file(s) in Vim
- Highlights common directory paths for convenience
- Optimized for fast workflows in the terminal

## Requirements
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (for dependency management)
- Vim (or you can change the editor in `main.py`)

## Installation
Install directly from GitHub using pip:
```sh
pip install git+https://github.com/manojmanivannan/py-file-opener.git
```

## Usage
After installation, use the CLI command:
```sh
py-file-opener <directory> <file1> <file2> ...
```
- Providing a single file opens it directly in Vim.
- If multiple files are specified, you will be prompted to select which one to open.

## Example
```sh
py-file-opener ./src file1.py file2.py file3.py
```


