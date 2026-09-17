"""Pydantic data model for langpipe.

Everything the pipeline touches is described here as a serialisable model. The
SQLite layer in :mod:`langpipe.db` reads and writes these models; the rest of the
code never talks to SQL directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (stored in SQLite as UTC)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Language(BaseModel):
    """A natural language as data.

    The only language-specific parts are `script` (writing system) and
    `tokenizer` (how text is split). Nothing else in langpipe branches on the
    language; a Chinese pack, an Arabic pack, and an English pack differ only in
    these two fields and in the content of their pack file.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    script: str = "latin"
    tokenizer: str = "word"
    rtl: bool = False
    note: str = ""


class Deck(BaseModel):
    """A named collection of notes, one per study unit."""

    id: int
    name: str
    language_code: str
    description: str = ""


class Note(BaseModel):
    """A single piece of knowledge: a word or a grammar point.

    Fields carry the language content. `kind` is "vocab" or "grammar". `stage`
    is the curriculum stage the note belongs to.
    """

    id: int
    deck_id: int
    kind: str  # "vocab" | "grammar"
    front: str
    back: str
    stage: int
    pos: str = ""
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Card(BaseModel):
    """A schedulable review unit derived from a note.

    `template` names the card direction: "recognition" (L1 -> L2) or
    "production" (L2 -> L1). The scheduler updates `due`, `interval`, `ease`,
    `reps`, and `lapses` from the review log.
    """

    id: int
    note_id: int
    template: str
    prompt: str
    answer: str
    stage: int
    due: datetime
    interval: int = 0
    ease: float = 2.5
    reps: int = 0
    lapses: int = 0


class ReviewEvent(BaseModel):
    """One graded review of one card."""

    id: int
    card_id: int
    grade: int  # 0..5
    reviewed_at: datetime
    interval_before: int
    interval_after: int
    ease_before: float
    ease_after: float


class CurriculumStage(BaseModel):
    """One phase of the curriculum with vocabulary and grammar targets."""

    order: int
    name: str
    target_vocab: int
    target_grammar: int
    description: str = ""


class LearnerState(BaseModel):
    """The learner and where they are in the plan."""

    id: int
    name: str
    target_language: str
    start_date: datetime
    current_stage: int = 1
    daily_new_cards: int = 10
    seed: int = 42


class VocabularyEntry(BaseModel):
    """A vocabulary item in a language pack file."""

    l1: str
    l2: str
    stage: int
    pos: str = ""
    tags: list[str] = Field(default_factory=list)
    example: str = ""
    example_translation: str = ""


class GrammarEntry(BaseModel):
    """A grammar point in a language pack file, with example Q/A pairs."""

    name: str
    stage: int
    explanation: str = ""
    examples: list[dict[str, str]] = Field(default_factory=list)


class LanguagePack(BaseModel):
    """A parsed language pack file: metadata plus vocabulary and grammar."""

    meta: dict[str, Any]
    vocabulary: list[VocabularyEntry]
    grammar: list[GrammarEntry]
