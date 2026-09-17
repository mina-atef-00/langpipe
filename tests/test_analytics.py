"""Analytics tests against a hand-computed fixture."""

from __future__ import annotations

from datetime import datetime, timedelta

from langpipe.analytics import compute_report
from langpipe.curriculum import DEFAULT_STAGES, progress_for_stage
from langpipe.db import Database
from langpipe.models import Card, Deck, LearnerState, Note, utcnow
from langpipe.scheduler import Scheduler


def _seed_learner(db: Database, now: datetime) -> int:
    db.set_stages(DEFAULT_STAGES)
    db.set_learner(LearnerState(id=1, name="Mina", target_language="es", start_date=now))
    return db.add_deck(Deck(id=0, name="deck", language_code="es"))


def _add_note_card(db: Database, deck_id: int, kind: str, front: str, stage: int) -> int:
    note_id = db.add_note(
        Note(id=0, deck_id=deck_id, kind=kind, front=front, back="x", stage=stage)
    )
    return db.add_card(
        Card(
            id=0,
            note_id=note_id,
            template="recognition",
            prompt=front,
            answer="x",
            stage=stage,
            due=utcnow(),
        )
    )


def _record(db: Database, card_id: int, grade: int, when: datetime) -> None:
    card = db.get_card(card_id)
    assert card is not None
    updated, event = Scheduler().review(card, grade, when=when)
    db.update_card(updated)
    db.add_review(event)


def test_retention_and_lapse_hand_computed(db: Database) -> None:
    now = datetime(2026, 1, 10, 12, 0, 0)
    deck_id = _seed_learner(db, now)
    card_ids = [
        _add_note_card(db, deck_id, "vocab", "w1", 1),
        _add_note_card(db, deck_id, "vocab", "w2", 1),
        _add_note_card(db, deck_id, "vocab", "w3", 1),
        _add_note_card(db, deck_id, "vocab", "w4", 1),
    ]
    for card_id, grade in zip(card_ids, [4, 1, 5, 3], strict=True):
        _record(db, card_id, grade, now)

    report = compute_report(db, now=now)
    assert report.total_reviews == 4
    assert report.passed_reviews == 3
    assert report.lapsed_reviews == 1
    assert report.retention_rate == 0.75
    assert report.lapse_rate == 0.25


def test_forecast_hand_computed(db: Database) -> None:
    now = datetime(2026, 1, 10, 12, 0, 0)
    for due in [
        now - timedelta(days=1),  # overdue
        now + timedelta(days=3),  # inside 7
        now + timedelta(days=10),  # inside 30, outside 7
        now + timedelta(days=40),  # outside 30
    ]:
        db.add_card(
            Card(
                id=0,
                note_id=1,
                template="recognition",
                prompt="a",
                answer="b",
                stage=1,
                due=due,
            )
        )

    report = compute_report(db, now=now)
    assert report.backlog == 1
    assert report.forecast_7d == 1
    assert report.forecast_30d == 2


def test_progress_hand_computed(db: Database) -> None:
    now = datetime(2026, 1, 10, 12, 0, 0)
    deck_id = _seed_learner(db, now)
    c1 = _add_note_card(db, deck_id, "vocab", "w1", 1)
    c2 = _add_note_card(db, deck_id, "vocab", "w2", 1)
    c3 = _add_note_card(db, deck_id, "vocab", "w3", 1)
    g1 = _add_note_card(db, deck_id, "grammar", "ser", 1)

    # w1 passes, w2 lapses (so only w1 counts as learned), w3 passes, grammar passes
    _record(db, c1, 4, now)
    _record(db, c2, 1, now)
    _record(db, c3, 5, now)
    _record(db, g1, 3, now)

    stage1 = db.list_stages()[0]
    progress = progress_for_stage(db, stage1)
    assert progress.vocab_learned == 2  # w1 and w3
    assert progress.grammar_learned == 1
    assert progress.vocab_pct == 0.7  # 2 / 300 * 100
    assert progress.grammar_pct == 5.0  # 1 / 20 * 100


def test_empty_report_has_no_retention(db: Database) -> None:
    now = datetime(2026, 1, 10, 12, 0, 0)
    db.set_stages(DEFAULT_STAGES)
    report = compute_report(db, now=now)
    assert report.retention_rate is None
    assert report.lapse_rate is None
    assert report.total_reviews == 0
    assert report.backlog == 0
    assert report.forecast_7d == 0
    assert report.forecast_30d == 0
