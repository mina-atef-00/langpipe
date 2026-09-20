"""Data-model tests: serialisation and defaults."""

from __future__ import annotations

from lesan_pipe.models import Card, Language, LearnerState, Note, ReviewEvent, utcnow


def test_language_round_trips_json() -> None:
    lang = Language(code="zh", name="Chinese", script="han", tokenizer="char")
    assert Language.model_validate_json(lang.model_dump_json()) == lang


def test_language_defaults() -> None:
    lang = Language(code="en", name="English")
    assert lang.script == "latin"
    assert lang.tokenizer == "word"
    assert lang.rtl is False


def test_language_is_language_agnostic_data() -> None:
    arabic = Language(code="ar", name="Arabic", script="arab", rtl=True)
    english = Language(code="en", name="English")
    assert arabic.rtl is True
    assert english.rtl is False
    assert arabic.model_dump()["script"] == "arab"


def test_note_defaults() -> None:
    note = Note(id=1, deck_id=1, kind="vocab", front="hello", back="hola", stage=1)
    assert note.tags == []
    assert note.extra == {}


def test_card_defaults() -> None:
    card = Card(
        id=1, note_id=1, template="recognition", prompt="a", answer="b", stage=1, due=utcnow()
    )
    assert card.ease == 2.5
    assert card.interval == 0
    assert card.reps == 0
    assert card.lapses == 0


def test_review_event_round_trips() -> None:
    now = utcnow()
    ev = ReviewEvent(
        id=1,
        card_id=2,
        grade=4,
        reviewed_at=now,
        interval_before=0,
        interval_after=1,
        ease_before=2.5,
        ease_after=2.5,
    )
    assert ReviewEvent.model_validate_json(ev.model_dump_json()) == ev


def test_learner_state_round_trips() -> None:
    learner = LearnerState(id=1, name="Mina", target_language="es", start_date=utcnow(), seed=42)
    assert LearnerState.model_validate_json(learner.model_dump_json()) == learner
