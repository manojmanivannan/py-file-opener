"""Contract tests for py_file_opener.frecency."""

import json

import pytest

from conftest import NOW, DAY, make_entry
from py_file_opener.frecency import (
    bump,
    load_records,
    prune,
    rank,
    recent,
    save_records,
    score,
)


def _rows(**counts):
    """Build a records map from {"<abs_path>": (<count>, <last>)} pairs."""
    return {path: {"count": count, "last": last} for path, (count, last) in counts.items()}


# --- score ------------------------------------------------------------------


def test_score_none_record_is_baseline():
    assert score(None) == 1.0
    assert score(None, now=NOW) == 1.0


def test_score_fresh_record_equals_count():
    record = {"count": 4, "last": NOW}
    assert score(record, now=NOW) == pytest.approx(4.0)


def test_score_decays_by_elapsed_days():
    record = {"count": 4, "last": NOW - 7 * DAY}
    assert score(record, now=NOW) == pytest.approx(4.0 / (1.0 + 7.0))


def test_score_future_last_clamped_to_zero_age():
    """A last timestamp in the future must not produce a negative age."""
    record = {"count": 4, "last": NOW + 5 * DAY}
    assert score(record, now=NOW) == pytest.approx(4.0)


# --- rank -------------------------------------------------------------------


def test_rank_sets_score_and_sorts_desc():
    entries = [
        make_entry("low.py", abs_path="/abs/low.py"),
        make_entry("high.py", abs_path="/abs/high.py"),
    ]
    records = {"/abs/high.py": {"count": 5, "last": NOW}, "/abs/low.py": {"count": 1, "last": NOW}}

    ranked = rank(entries, records, now=NOW)

    assert [e.rel_path for e in ranked] == ["high.py", "low.py"]
    assert ranked[0].score == pytest.approx(5.0)
    assert ranked[1].score == pytest.approx(1.0)


def test_rank_equal_scores_broken_case_insensitively():
    entries = [
        make_entry("B.py", abs_path="/abs/B.py"),
        make_entry("a.py", abs_path="/abs/a.py"),
    ]
    ranked = rank(entries, {}, now=NOW)

    assert [e.rel_path for e in ranked] == ["a.py", "B.py"]


def test_rank_never_opened_slots_between_fresh_and_ancient():
    entries = [
        make_entry("ancient.py", abs_path="/abs/ancient.py"),
        make_entry("never_b.py", abs_path="/abs/never_b.py"),
        make_entry("fresh.py", abs_path="/abs/fresh.py"),
        make_entry("never_a.py", abs_path="/abs/never_a.py"),
    ]
    records = {
        "/abs/fresh.py": {"count": 3, "last": NOW - DAY},        # 3/2 = 1.5
        "/abs/ancient.py": {"count": 3, "last": NOW - 400 * DAY},  # ~0.0075
    }

    ranked = rank(entries, records, now=NOW)
    scores = {e.rel_path: e.score for e in ranked}

    assert [e.rel_path for e in ranked] == [
        "fresh.py", "never_a.py", "never_b.py", "ancient.py",
    ]
    assert scores["never_a.py"] == pytest.approx(1.0)
    assert scores["ancient.py"] < 1.0 < scores["fresh.py"]


# --- bump -------------------------------------------------------------------


def test_bump_increments_count_and_pins_last(tmp_path):
    records = {"a.py": {"count": 1, "last": 100.0}, "b.py": {"count": 7, "last": 200.0}}

    result = bump(records, ["a.py"], now=NOW)

    assert result["a.py"] == {"count": 2, "last": NOW}
    assert result["b.py"] == {"count": 7, "last": 200.0}  # untouched row preserved


def test_bump_seeds_new_path_from_nothing():
    result = bump({}, ["new.py"], now=NOW)

    assert result == {"new.py": {"count": 1, "last": NOW}}


def test_bump_returns_new_dict_without_mutating_input():
    records = {"a.py": {"count": 1, "last": 100.0}}
    result = bump(records, ["a.py", "b.py"], now=NOW)

    assert result is not records
    assert records == {"a.py": {"count": 1, "last": 100.0}}  # input NOT mutated
    assert result == {
        "a.py": {"count": 2, "last": NOW},
        "b.py": {"count": 1, "last": NOW},
    }


def test_bump_defaults_now_to_real_time():
    result = bump({}, ["a.py"])

    assert result["a.py"]["count"] == 1
    assert result["a.py"]["last"] > 0  # any real epoch works; never None


# --- load / save ------------------------------------------------------------


def test_save_then_load_roundtrip(tmp_path):
    records = _rows(**{"a.py": (3, 123.5), "b.py": (1, 0.0)})

    save_records(tmp_path, records)
    assert load_records(tmp_path) == records


def test_save_creates_missing_cache_dir(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"

    save_records(cache_dir, {"a.py": {"count": 1, "last": 5.0}})

    assert cache_dir.is_dir()
    assert load_records(cache_dir) == {"a.py": {"count": 1, "last": 5.0}}


def test_save_leaves_no_temp_files_behind(tmp_path):
    save_records(tmp_path, {"a.py": {"count": 1, "last": 5.0}})

    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "history.json"]
    assert leftovers == []  # no temp/partial files left by the atomic save
    with open(tmp_path / "history.json", "r", encoding="utf-8") as handle:
        assert json.load(handle) == {"a.py": {"count": 1, "last": 5.0}}


def test_load_missing_file_returns_empty(tmp_path):
    assert load_records(tmp_path) == {}


def test_load_corrupt_json_returns_empty(tmp_path, capsys):
    (tmp_path / "history.json").write_text("{definitely : not json", encoding="utf-8")

    assert load_records(tmp_path) == {}
    assert capsys.readouterr().err  # degraded loudly, not silently


def test_load_wrong_shape_json_returns_empty(tmp_path):
    (tmp_path / "history.json").write_text('["not", "an", "object"]', encoding="utf-8")

    assert load_records(tmp_path) == {}
    # a dict whose rows are not {count: int, last: float} is also rejected
    (tmp_path / "history.json").write_text('{"a.py": {"count": "3", "last": 1.0}}', encoding="utf-8")
    assert load_records(tmp_path) == {}


# --- prune ------------------------------------------------------------------


def test_prune_drops_oldest_beyond_cap():
    records = {
        "a.py": {"count": 1, "last": 100.0},
        "b.py": {"count": 1, "last": 300.0},
        "c.py": {"count": 1, "last": 200.0},
    }

    kept = prune(records, 2)

    assert kept == {"b.py": {"count": 1, "last": 300.0}, "c.py": {"count": 1, "last": 200.0}}


def test_prune_under_cap_returns_everything():
    records = {"a.py": {"count": 2, "last": 1.0}, "b.py": {"count": 1, "last": 2.0}}

    assert prune(records, 500) == records


# --- recent -----------------------------------------------------------------


def test_recent_orders_by_last_desc_and_limits():
    records = {
        "a.py": {"count": 1, "last": 100.0},
        "b.py": {"count": 1, "last": 300.0},
        "c.py": {"count": 1, "last": 200.0},
    }

    assert recent(records, 2) == ["b.py", "c.py"]
    assert recent(records, 50) == ["b.py", "c.py", "a.py"]
    assert recent(records, 0) == []
    assert recent({}, 5) == []