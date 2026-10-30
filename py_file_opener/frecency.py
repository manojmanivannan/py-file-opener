"""Frecency history: persistence, bumping, pruning, scoring and ranking.

History is stored at `<cache_dir>/history.json` as a JSON object mapping an
absolute path to a row `{"count": int, "last": float}`. All time-dependent
functions accept an injectable `now` so callers (and tests) can pin time.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from .model import Entry

HISTORY_FILE = "history.json"
DAY_SECONDS = 86400.0
RecordMap = Dict[str, Dict[str, float]]


def load_records(cache_dir: Path) -> RecordMap:
    """Load the history file, tolerating absence and corruption."""
    path = cache_dir / HISTORY_FILE
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        print(f"py-file-opener: unreadable history, starting fresh: {path}", file=sys.stderr)
        return {}
    if not isinstance(data, dict) or not all(
        isinstance(row, dict) and isinstance(row.get("count"), int) for row in data.values()
    ):
        print(f"py-file-opener: unreadable history, starting fresh: {path}", file=sys.stderr)
        return {}
    return data


def save_records(cache_dir: Path, records: RecordMap) -> None:
    """Atomically persist `records` to `<cache_dir>/history.json`."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_dir / f"{HISTORY_FILE}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(records, handle)
    os.replace(tmp_path, cache_dir / HISTORY_FILE)


def bump(records: RecordMap, paths: List[str], now: Optional[float] = None) -> RecordMap:
    """Return a new records map with each path in `paths` opened once more."""
    timestamp = time.time() if now is None else now
    bumped: RecordMap = {path: dict(row) for path, row in records.items()}
    for path in paths:
        row = bumped.get(path)
        if row is None:
            bumped[path] = {"count": 1, "last": timestamp}
        else:
            row["count"] = int(row.get("count", 0)) + 1
            row["last"] = timestamp
    return bumped


def prune(records: RecordMap, cache_dir_keep: int = 500) -> RecordMap:
    """Return a new map keeping the `cache_dir_keep` most recent rows."""
    if cache_dir_keep >= len(records):
        return records
    keep = sorted(records.items(), key=lambda item: item[1].get("last", 0.0), reverse=True)
    return dict(keep[:cache_dir_keep])


def score(record: Optional[Dict[str, float]], now: Optional[float] = None) -> float:
    """Score one history row; never-opened paths score a flat 1.0."""
    if record is None or record.get("last") is None or record.get("count") is None:
        return 1.0
    at = time.time() if now is None else now
    age_days = max(0.0, (at - float(record["last"])) / DAY_SECONDS)
    return int(record["count"]) / (1.0 + age_days)


def rank(entries: List[Entry], records: RecordMap, now: Optional[float] = None) -> List[Entry]:
    """Return a new list of entries, scored and sorted frecency-first."""
    ranked: List[Entry] = []
    for entry in entries:
        entry.score = score(records.get(entry.abs_path), now=now)
        ranked.append(entry)
    return sorted(ranked, key=lambda e: (-e.score, e.rel_path.lower()))


def recent(records: RecordMap, n: int = 10, now: Optional[float] = None) -> List[str]:
    """Return up to `n` absolute paths, most recently opened first."""
    del now  # accepted for symmetry with the other time-dependent helpers
    if n <= 0:
        return []
    ordered = sorted(records.items(), key=lambda item: item[1].get("last", 0.0), reverse=True)
    return [path for path, _row in ordered[:n]]