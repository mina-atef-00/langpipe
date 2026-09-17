"""Shared fixtures for the langpipe test suite."""

from __future__ import annotations

from datetime import datetime

import pytest

from langpipe.db import Database
from langpipe.models import Card, utcnow


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture
def card_factory():
    def _make(
        due: datetime | None = None,
        interval: int = 0,
        ease: float = 2.5,
        reps: int = 0,
        note_id: int = 1,
        stage: int = 1,
    ) -> Card:
        return Card(
            id=0,
            note_id=note_id,
            template="recognition",
            prompt="a",
            answer="b",
            stage=stage,
            due=utcnow() if due is None else due,
            interval=interval,
            ease=ease,
            reps=reps,
        )

    return _make
