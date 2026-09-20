"""SM-2 scheduler tests against hand-computed values."""

from __future__ import annotations

import pytest

from lesan_pipe.models import Card, utcnow
from lesan_pipe.scheduler import Scheduler


def make_card(interval: int = 0, ease: float = 2.5, reps: int = 0) -> Card:
    return Card(
        id=1,
        note_id=1,
        template="recognition",
        prompt="a",
        answer="b",
        stage=1,
        due=utcnow(),
        interval=interval,
        ease=ease,
        reps=reps,
    )


def test_first_pass_interval_1() -> None:
    card, event = Scheduler().review(make_card(), 4)
    assert event.interval_after == 1
    assert card.reps == 1
    assert card.interval == 1


def test_second_pass_interval_6() -> None:
    card, event = Scheduler().review(make_card(interval=1, reps=1), 4)
    assert event.interval_after == 6


def test_third_pass_multiplies_interval() -> None:
    card, event = Scheduler().review(make_card(interval=6, reps=2, ease=2.5), 4)
    assert event.interval_after == 15  # round(6 * 2.5)


def test_lapse_resets_repetitions() -> None:
    card, event = Scheduler().review(make_card(interval=10, reps=3, ease=2.5), 1)
    assert card.reps == 0
    assert card.lapses == 1
    assert event.interval_after == 1


def test_ease_update_grade_5() -> None:
    _, event = Scheduler().review(make_card(), 5)
    assert event.ease_after == pytest.approx(2.6)  # 2.5 + 0.1


def test_ease_update_grade_3() -> None:
    _, event = Scheduler().review(make_card(), 3)
    # 2.5 + 0.1 - 2*(0.08 + 2*0.02) = 2.36
    assert event.ease_after == pytest.approx(2.36)


def test_ease_floor() -> None:
    scheduler = Scheduler()
    card = make_card()
    for _ in range(30):
        card, _ = scheduler.review(card, 0)
    assert card.ease >= 1.3


def test_grade_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        Scheduler().review(make_card(), 6)


def test_due_date_is_interval_days_out() -> None:
    from datetime import datetime, timedelta

    when = datetime(2026, 1, 1, 12, 0, 0)
    card, _ = Scheduler().review(make_card(interval=6, reps=2, ease=2.5), 4, when=when)
    assert card.due == when + timedelta(days=15)
