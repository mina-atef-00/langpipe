"""SQLite persistence for langpipe.

A thin layer over the standard-library sqlite3 module. Every row maps to a
Pydantic model from :mod:`langpipe.models`. Datetimes are stored as ISO-8601
strings in UTC; tags and extra fields are stored as JSON.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from langpipe.models import (
    Card,
    CurriculumStage,
    Deck,
    Language,
    LearnerState,
    Note,
    ReviewEvent,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS languages (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    script TEXT NOT NULL,
    tokenizer TEXT NOT NULL,
    rtl INTEGER NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    language_code TEXT NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    stage INTEGER NOT NULL,
    pos TEXT NOT NULL,
    tags TEXT NOT NULL,
    extra TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL,
    template TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    stage INTEGER NOT NULL,
    due TEXT NOT NULL,
    interval INTEGER NOT NULL,
    ease REAL NOT NULL,
    reps INTEGER NOT NULL,
    lapses INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    grade INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL,
    interval_before INTEGER NOT NULL,
    interval_after INTEGER NOT NULL,
    ease_before REAL NOT NULL,
    ease_after REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS curriculum_stages (
    ord INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    target_vocab INTEGER NOT NULL,
    target_grammar INTEGER NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learner_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    target_language TEXT NOT NULL,
    start_date TEXT NOT NULL,
    current_stage INTEGER NOT NULL,
    daily_new_cards INTEGER NOT NULL,
    seed INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Database:
    """Handles the SQLite connection and all queries."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- languages ---------------------------------------------------------

    def upsert_language(self, lang: Language) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO languages VALUES (?, ?, ?, ?, ?, ?)",
            (lang.code, lang.name, lang.script, lang.tokenizer, int(lang.rtl), lang.note),
        )
        self._conn.commit()

    def get_language(self, code: str) -> Language | None:
        row = self._conn.execute("SELECT * FROM languages WHERE code = ?", (code,)).fetchone()
        if row is None:
            return None
        return Language(
            code=row["code"],
            name=row["name"],
            script=row["script"],
            tokenizer=row["tokenizer"],
            rtl=bool(row["rtl"]),
            note=row["note"],
        )

    # -- decks -------------------------------------------------------------

    def add_deck(self, deck: Deck) -> int:
        cur = self._conn.execute(
            "INSERT INTO decks (name, language_code, description) VALUES (?, ?, ?)",
            (deck.name, deck.language_code, deck.description),
        )
        self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def get_deck(self, deck_id: int) -> Deck | None:
        row = self._conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        if row is None:
            return None
        return Deck(
            id=row["id"],
            name=row["name"],
            language_code=row["language_code"],
            description=row["description"],
        )

    def list_decks(self) -> list[Deck]:
        rows = self._conn.execute("SELECT * FROM decks ORDER BY id").fetchall()
        return [
            Deck(
                id=r["id"],
                name=r["name"],
                language_code=r["language_code"],
                description=r["description"],
            )
            for r in rows
        ]

    # -- notes -------------------------------------------------------------

    def add_note(self, note: Note) -> int:
        cur = self._conn.execute(
            "INSERT INTO notes (deck_id, kind, front, back, stage, pos, tags, extra) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note.deck_id,
                note.kind,
                note.front,
                note.back,
                note.stage,
                note.pos,
                json.dumps(note.tags),
                json.dumps(note.extra),
            ),
        )
        self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def list_notes(self) -> list[Note]:
        rows = self._conn.execute("SELECT * FROM notes ORDER BY id").fetchall()
        return [self._note_from_row(r) for r in rows]

    def list_notes_by_stage(self, stage: int) -> list[Note]:
        rows = self._conn.execute(
            "SELECT * FROM notes WHERE stage = ? ORDER BY id", (stage,)
        ).fetchall()
        return [self._note_from_row(r) for r in rows]

    def count_notes_by_kind_stage(self, kind: str) -> dict[int, int]:
        rows = self._conn.execute(
            "SELECT stage, COUNT(*) AS n FROM notes WHERE kind = ? GROUP BY stage", (kind,)
        ).fetchall()
        return {int(r["stage"]): int(r["n"]) for r in rows}

    def _note_from_row(self, r: sqlite3.Row) -> Note:
        return Note(
            id=r["id"],
            deck_id=r["deck_id"],
            kind=r["kind"],
            front=r["front"],
            back=r["back"],
            stage=r["stage"],
            pos=r["pos"],
            tags=json.loads(r["tags"]),
            extra=json.loads(r["extra"]),
        )

    # -- cards -------------------------------------------------------------

    def add_card(self, card: Card) -> int:
        cur = self._conn.execute(
            "INSERT INTO cards (note_id, template, prompt, answer, stage, due, interval, "
            "ease, reps, lapses) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                card.note_id,
                card.template,
                card.prompt,
                card.answer,
                card.stage,
                _iso(card.due),
                card.interval,
                card.ease,
                card.reps,
                card.lapses,
            ),
        )
        self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def get_card(self, card_id: int) -> Card | None:
        row = self._conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            return None
        return self._card_from_row(row)

    def list_cards(self) -> list[Card]:
        rows = self._conn.execute("SELECT * FROM cards ORDER BY id").fetchall()
        return [self._card_from_row(r) for r in rows]

    def list_cards_by_stage(self, stage: int) -> list[Card]:
        rows = self._conn.execute(
            "SELECT * FROM cards WHERE stage = ? ORDER BY id", (stage,)
        ).fetchall()
        return [self._card_from_row(r) for r in rows]

    def update_card(self, card: Card) -> None:
        self._conn.execute(
            "UPDATE cards SET due = ?, interval = ?, ease = ?, reps = ?, lapses = ? WHERE id = ?",
            (_iso(card.due), card.interval, card.ease, card.reps, card.lapses, card.id),
        )
        self._conn.commit()

    def _card_from_row(self, r: sqlite3.Row) -> Card:
        return Card(
            id=r["id"],
            note_id=r["note_id"],
            template=r["template"],
            prompt=r["prompt"],
            answer=r["answer"],
            stage=r["stage"],
            due=_parse_dt(r["due"]),
            interval=r["interval"],
            ease=r["ease"],
            reps=r["reps"],
            lapses=r["lapses"],
        )

    # -- review events -----------------------------------------------------

    def add_review(self, event: ReviewEvent) -> int:
        cur = self._conn.execute(
            "INSERT INTO review_events (card_id, grade, reviewed_at, interval_before, "
            "interval_after, ease_before, ease_after) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.card_id,
                event.grade,
                _iso(event.reviewed_at),
                event.interval_before,
                event.interval_after,
                event.ease_before,
                event.ease_after,
            ),
        )
        self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def list_reviews(self) -> list[ReviewEvent]:
        rows = self._conn.execute("SELECT * FROM review_events ORDER BY id").fetchall()
        return [
            ReviewEvent(
                id=r["id"],
                card_id=r["card_id"],
                grade=r["grade"],
                reviewed_at=_parse_dt(r["reviewed_at"]),
                interval_before=r["interval_before"],
                interval_after=r["interval_after"],
                ease_before=r["ease_before"],
                ease_after=r["ease_after"],
            )
            for r in rows
        ]

    # -- curriculum stages -------------------------------------------------

    def set_stages(self, stages: list[CurriculumStage]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO curriculum_stages VALUES (?, ?, ?, ?, ?)",
            [(s.order, s.name, s.target_vocab, s.target_grammar, s.description) for s in stages],
        )
        self._conn.commit()

    def list_stages(self) -> list[CurriculumStage]:
        rows = self._conn.execute("SELECT * FROM curriculum_stages ORDER BY ord").fetchall()
        return [
            CurriculumStage(
                order=r["ord"],
                name=r["name"],
                target_vocab=r["target_vocab"],
                target_grammar=r["target_grammar"],
                description=r["description"],
            )
            for r in rows
        ]

    # -- learner state -----------------------------------------------------

    def set_learner(self, learner: LearnerState) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO learner_state VALUES (1, ?, ?, ?, ?, ?, ?)",
            (
                learner.name,
                learner.target_language,
                _iso(learner.start_date),
                learner.current_stage,
                learner.daily_new_cards,
                learner.seed,
            ),
        )
        self._conn.commit()

    def get_learner(self) -> LearnerState | None:
        row = self._conn.execute("SELECT * FROM learner_state WHERE id = 1").fetchone()
        if row is None:
            return None
        return LearnerState(
            id=row["id"],
            name=row["name"],
            target_language=row["target_language"],
            start_date=_parse_dt(row["start_date"]),
            current_stage=row["current_stage"],
            daily_new_cards=row["daily_new_cards"],
            seed=row["seed"],
        )

    def update_learner(self, **fields: Any) -> None:
        learner = self.get_learner()
        if learner is None:
            raise RuntimeError("no learner; run init first")
        updated = learner.model_copy(update=fields)
        self.set_learner(updated)

    # -- meta --------------------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
        self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    # -- analytics helpers -------------------------------------------------

    def vocab_reviewed_by_stage(self) -> dict[int, int]:
        """Count distinct vocabulary notes per stage that have at least one
        passing review (grade >= 3)."""
        rows = self._conn.execute(
            """
            SELECT n.stage, COUNT(DISTINCT n.id) AS n
            FROM notes n
            JOIN cards c ON c.note_id = n.id
            JOIN review_events r ON r.card_id = c.id
            WHERE n.kind = 'vocab' AND r.grade >= 3
            GROUP BY n.stage
            """
        ).fetchall()
        return {int(r["stage"]): int(r["n"]) for r in rows}

    def grammar_reviewed_by_stage(self) -> dict[int, int]:
        """Count distinct grammar notes per stage with a passing review."""
        rows = self._conn.execute(
            """
            SELECT n.stage, COUNT(DISTINCT n.id) AS n
            FROM notes n
            JOIN cards c ON c.note_id = n.id
            JOIN review_events r ON r.card_id = c.id
            WHERE n.kind = 'grammar' AND r.grade >= 3
            GROUP BY n.stage
            """
        ).fetchall()
        return {int(r["stage"]): int(r["n"]) for r in rows}

    def cards_due_between(self, start: datetime, end: datetime) -> list[Card]:
        rows = self._conn.execute(
            "SELECT * FROM cards WHERE due >= ? AND due <= ? ORDER BY due",
            (_iso(start), _iso(end)),
        ).fetchall()
        return [self._card_from_row(r) for r in rows]

    def count_due_before(self, when: datetime) -> int:
        """Cards whose due date is strictly before `when` (overdue backlog)."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM cards WHERE due < ?", (_iso(when),)
        ).fetchone()
        return int(row["n"])

    def iter_reviews(self) -> Iterator[ReviewEvent]:
        yield from self.list_reviews()
