"""End-to-end CLI tests through typer's CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lesan_pipe.cli import app

runner = CliRunner()


def _init(tmp_path: Path, name: str = "x", seed: int = 42):
    db = tmp_path / f"{name}.db"
    result = runner.invoke(app, ["init", "--db", str(db), "--seed", str(seed)])
    assert result.exit_code == 0, result.output
    return db


def test_init_creates_learner(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--db", str(tmp_path / "x.db")])
    assert result.exit_code == 0
    assert "Initialised learner" in result.output
    assert "56 vocabulary items" in result.output
    assert "8 grammar points" in result.output


def test_plan_lists_stages(tmp_path: Path) -> None:
    db = _init(tmp_path, "plan")
    result = runner.invoke(app, ["plan", "--db", str(db)])
    assert result.exit_code == 0
    assert "stage 1 (bridge)" in result.output
    assert "stage 4 (fluency)" in result.output


def test_generate_reports_card_count(tmp_path: Path) -> None:
    db = _init(tmp_path, "gen")
    result = runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    assert result.exit_code == 0
    assert "Generated 57 cards for stage 1" in result.output


def test_review_then_stats(tmp_path: Path) -> None:
    db = _init(tmp_path, "review")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    review = runner.invoke(app, ["review", str(1), "--grade", "4", "--db", str(db)])
    assert review.exit_code == 0
    assert "graded 4" in review.output
    stats = runner.invoke(app, ["stats", "--db", str(db)])
    assert stats.exit_code == 0
    assert "retention rate:  100.0%" in stats.output


def test_stats_before_review_shows_no_data(tmp_path: Path) -> None:
    db = _init(tmp_path, "empty")
    result = runner.invoke(app, ["stats", "--db", str(db)])
    assert result.exit_code == 0
    assert "no reviews recorded yet" in result.output


def test_sync_mock(tmp_path: Path) -> None:
    db = _init(tmp_path, "sync")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    result = runner.invoke(app, ["sync", "--db", str(db), "--mock", "--stage", "1"])
    assert result.exit_code == 0
    # 57 cards exist but two share the same front/back ("no" from two
    # templates); content-keyed duplicate detection collapses them to 56,
    # matching what real Anki would store.
    assert "56 notes added" in result.output

    # Re-sync must be idempotent: the same cards already exist, so zero notes.
    resync = runner.invoke(app, ["sync", "--db", str(db), "--mock", "--stage", "1"])
    assert resync.exit_code == 0
    assert "0 notes added" in resync.output


def test_sync_unreachable_exits_nonzero(tmp_path: Path) -> None:
    db = _init(tmp_path, "syncfail")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    result = runner.invoke(app, ["sync", "--db", str(db), "--url", "http://127.0.0.1:1"])
    assert result.exit_code == 1
    assert "not reachable" in result.output


def test_same_seed_reproduces_plan(tmp_path: Path) -> None:
    db1 = _init(tmp_path, "a")
    db2 = _init(tmp_path, "b")
    g1 = runner.invoke(app, ["generate", "--db", str(db1), "--stage", "1", "--seed", "42"])
    g2 = runner.invoke(app, ["generate", "--db", str(db2), "--stage", "1", "--seed", "42"])
    assert g1.exit_code == 0 and g2.exit_code == 0
    assert g1.output == g2.output


def test_init_missing_pack_fails(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["init", "--db", str(tmp_path / "nope.db"), "--pack", "/does/not/exist.json"]
    )
    assert result.exit_code == 1
    assert "Language pack not found" in result.output


def test_review_out_of_range_grade_fails_cleanly(tmp_path: Path) -> None:
    """An out-of-range grade must be a one-line error, not a ValueError
    traceback from the scheduler."""
    db = _init(tmp_path, "grade")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    result = runner.invoke(app, ["review", "1", "--grade", "9", "--db", str(db)])
    assert result.exit_code == 1
    assert "Grade must be between 0 and 5" in result.output
    assert "Traceback" not in result.output


def test_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    """Re-running init on an existing database must fail, not silently
    delete the learner's data. WHY: init used to unlink() unconditionally,
    so a stray re-init wiped all reviews and scheduling history."""
    db = _init(tmp_path, "guarded", seed=7)
    before = db.read_bytes()
    result = runner.invoke(app, ["init", "--db", str(db)])
    assert result.exit_code == 1
    assert "--force" in result.output
    # The existing database is untouched: same bytes, still usable.
    assert db.read_bytes() == before
    plan = runner.invoke(app, ["plan", "--db", str(db)])
    assert plan.exit_code == 0


def test_init_force_overwrites(tmp_path: Path) -> None:
    db = _init(tmp_path, "forced", seed=7)
    result = runner.invoke(app, ["init", "--db", str(db), "--force", "--seed", "8"])
    assert result.exit_code == 0, result.output
    assert "Initialised learner" in result.output


def test_init_missing_pack_never_touches_db(tmp_path: Path) -> None:
    """A bad --pack path must fail before any database is created or
    deleted. WHY: the old order (unlink, then load pack) destroyed a good
    database when the pack path was typo'd."""
    fresh = tmp_path / "fresh.db"
    result = runner.invoke(app, ["init", "--db", str(fresh), "--pack", "/does/not/exist.json"])
    assert result.exit_code == 1
    assert "Language pack not found" in result.output
    assert not fresh.exists()

    db = _init(tmp_path, "kept")
    before = db.read_bytes()
    result = runner.invoke(
        app, ["init", "--db", str(db), "--force", "--pack", "/does/not/exist.json"]
    )
    assert result.exit_code == 1
    assert db.read_bytes() == before


def test_plan_missing_db_fails_without_creating_file(tmp_path: Path) -> None:
    """plan on a missing database must error, not create an empty file.
    WHY: Database() connects (creating the file) on open, so a typo'd
    --db path used to scatter empty databases as a side effect."""
    missing = tmp_path / "missing.db"
    result = runner.invoke(app, ["plan", "--db", str(missing)])
    assert result.exit_code == 1
    assert "init" in result.output
    assert not missing.exists()


def test_read_commands_missing_db_fail_without_creating_file(tmp_path: Path) -> None:
    for argv in (
        ["generate", "--stage", "1"],
        ["cards"],
        ["review", "1", "--grade", "4"],
        ["stats"],
        ["sync", "--mock"],
    ):
        missing = tmp_path / "missing.db"
        result = runner.invoke(app, [*argv, "--db", str(missing)])
        assert result.exit_code == 1, argv
        assert not missing.exists(), argv


def test_init_json(tmp_path: Path) -> None:
    db = tmp_path / "init.json.db"
    result = runner.invoke(app, ["init", "--db", str(db), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["vocab_count"] == 56
    assert payload["grammar_count"] == 8
    assert payload["language_code"] == "es"


def test_plan_json(tmp_path: Path) -> None:
    db = _init(tmp_path, "planjson")
    result = runner.invoke(app, ["plan", "--db", str(db), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [s["name"] for s in payload["stages"]] == ["bridge", "input", "expansion", "fluency"]
    assert all("target_vocab" in s and "description" in s for s in payload["stages"])


def test_generate_json(tmp_path: Path) -> None:
    db = _init(tmp_path, "genjson")
    result = runner.invoke(
        app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["count"] == 57
    assert len(payload["cards"]) == 57
    assert all("prompt" in c and "answer" in c for c in payload["cards"])


def test_cards_json(tmp_path: Path) -> None:
    db = _init(tmp_path, "cardsjson")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    result = runner.invoke(app, ["cards", "--db", str(db), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["cards"]) == 57
    assert all("due" in c and "interval" in c for c in payload["cards"])


def test_review_json(tmp_path: Path) -> None:
    db = _init(tmp_path, "reviewjson")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    result = runner.invoke(app, ["review", "1", "--grade", "4", "--db", str(db), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["card_id"] == 1
    assert payload["grade"] == 4
    assert payload["review_id"] == 1
    assert payload["interval_before"] == 0
    assert payload["interval_after"] >= 1
    assert payload["ease_before"] == 2.5
    assert isinstance(payload["due"], str)


def test_stats_json(tmp_path: Path) -> None:
    db = _init(tmp_path, "statsjson")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    runner.invoke(app, ["review", "1", "--grade", "4", "--db", str(db)])
    result = runner.invoke(app, ["stats", "--db", str(db), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["total_reviews"] == 1
    assert payload["retention_rate"] == 1.0
    assert len(payload["stages"]) == 4


def test_sync_json(tmp_path: Path) -> None:
    db = _init(tmp_path, "syncjson")
    runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    result = runner.invoke(app, ["sync", "--db", str(db), "--mock", "--stage", "1", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["notes_added"] == 56
    assert payload["backend"] == "mock"
