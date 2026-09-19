"""End-to-end CLI tests through typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from langpipe.cli import app

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
