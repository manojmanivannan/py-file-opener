"""Core data models for py-file-opener."""

import dataclasses
from pathlib import Path
from typing import Optional

__version__ = "0.2.0"


@dataclasses.dataclass
class Entry:
    """One candidate file row shown to the user."""

    abs_path: str
    rel_path: str
    size_h: str
    mtime_h: str
    git_badge: str
    score: float = 1.0


@dataclasses.dataclass
class Config:
    """Runtime configuration derived from CLI flags and the environment."""

    editor: Optional[str]
    cache_dir: Path
    no_preview: bool