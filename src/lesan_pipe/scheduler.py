"""Spaced-repetition scheduler.

Implements the SuperMemo SM-2 algorithm, the best-known spaced-repetition
schedule and the basis of most modern SRS software. The original description is
Piotr Wozniak's "Application of a computer to improve the results obtained in
working with the SuperMemo method" (1990) and the SM-2 section of his SuperMemo
algorithm description. Anki's default schedule is a modified SM-2.

Rules, following Wozniak:

* A review is graded 0-5 (0 = complete blackout, 5 = perfect recall).
* A grade below 3 is a lapse: repetitions reset to 0 and the card is due
  again after one day.
* A grade of 3 or above is a pass:
    - first pass  -> interval 1 day
    - second pass -> interval 6 days
    - later pass  -> interval = round(previous interval * ease factor)
* The ease factor starts at 2.5 and is updated after every review:

    EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))

  and is floored at 1.3 so a card never becomes permanently stuck.

The schedule is deterministic: given the same grade sequence, it produces the
same intervals and ease factors.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from lesan_pipe.models import Card, ReviewEvent, utcnow

MIN_EASE = 1.3
STARTING_EASE = 2.5
PASS_THRESHOLD = 3
MAX_GRADE = 5


class Scheduler:
    """Pure SM-2 scheduler. Stateless apart from the card it is applied to."""

    def review(
        self, card: Card, grade: int, when: datetime | None = None
    ) -> tuple[Card, ReviewEvent]:
        """Apply one review to `card`, returning the updated card and the event.

        `when` is the review timestamp (defaults to now); it is injectable so
        tests can pin time.
        """
        if not 0 <= grade <= MAX_GRADE:
            raise ValueError(f"grade must be between 0 and {MAX_GRADE}, got {grade}")

        reviewed_at = utcnow() if when is None else when

        ease_before = card.ease
        interval_before = card.interval

        if grade < PASS_THRESHOLD:
            card.reps = 0
            card.interval = 1
            card.lapses += 1
        else:
            if card.reps == 0:
                card.interval = 1
            elif card.reps == 1:
                card.interval = 6
            else:
                card.interval = round(card.interval * card.ease)
            card.reps += 1
            card.ease = self._update_ease(card.ease, grade)

        card.due = reviewed_at + timedelta(days=card.interval)

        event = ReviewEvent(
            id=0,
            card_id=card.id,
            grade=grade,
            reviewed_at=reviewed_at,
            interval_before=interval_before,
            interval_after=card.interval,
            ease_before=ease_before,
            ease_after=card.ease,
        )
        return card, event

    @staticmethod
    def _update_ease(ease: float, grade: int) -> float:
        delta = 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)
        return max(MIN_EASE, round(ease + delta, 4))
