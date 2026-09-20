"""Note identity: a card must bind to its own pack entry, not a same-gloss note.

WHY: ``generate`` used to join cards to notes on the English gloss
(``vocab:<l1>``), which repeats across stages (e.g. 国/stage-1 and 国家/stage-3
are both "country, nation"). The lookup dict kept the last note per gloss, so
stage-1 cards landed on later-stage notes and passing reviews were credited
to the wrong stage in per-stage progress.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lesan_pipe.cli import app
from lesan_pipe.curriculum import DEFAULT_STAGES, progress_for_stage
from lesan_pipe.db import Database

runner = CliRunner()


def _write_collision_pack(path: Path) -> Path:
    """A two-entry pack where one gloss spans two stages (和/stage-1 and
    又/stage-3 are both "and" in the real Chinese pack)."""
    pack = {
        "meta": {
            "name": "collision-probe",
            "language_code": "xx",
            "language_name": "Probe",
            "script": "latin",
            "tokenizer": "word",
            "rtl": False,
        },
        "vocabulary": [
            {"l1": "and", "l2": "和", "stage": 1, "pos": "", "tags": []},
            {"l1": "and", "l2": "又", "stage": 3, "pos": "", "tags": []},
        ],
        "grammar": [],
    }
    path.write_text(json.dumps(pack), encoding="utf-8")
    return path


def test_colliding_gloss_card_binds_to_own_stage(tmp_path: Path) -> None:
    pack_path = _write_collision_pack(tmp_path / "collision.json")
    db_path = tmp_path / "collision.db"
    init = runner.invoke(app, ["init", "--db", str(db_path), "--pack", str(pack_path)])
    assert init.exit_code == 0, init.output

    gen = runner.invoke(app, ["generate", "--db", str(db_path), "--stage", "1", "--seed", "42"])
    assert gen.exit_code == 0, gen.output

    database = Database(str(db_path))
    try:
        notes_by_id = {n.id: n for n in database.list_notes()}
        cards = database.list_cards()
        assert cards, "stage 1 must generate cards"
        # Every stage-1 card must sit on a stage-1 note (the repro query
        # `WHERE n.stage <> 1` must return 0 rows).
        assert all(notes_by_id[c.note_id].stage == 1 for c in cards)

        review = runner.invoke(
            app, ["review", str(cards[0].id), "--grade", "4", "--db", str(db_path)]
        )
        assert review.exit_code == 0, review.output

        assert database.vocab_reviewed_by_stage() == {1: 1}
        assert progress_for_stage(database, DEFAULT_STAGES[0]).vocab_learned == 1
        assert progress_for_stage(database, DEFAULT_STAGES[2]).vocab_learned == 0
    finally:
        database.close()
