"""Deterministic practice-content generator.

The generator is rule-based. It never calls a language model. It reads a
language pack (vocabulary plus grammar definitions), selects the entries for a
given curriculum stage, and expands each one into practice cards:

* vocabulary entry            -> recognition card (L1 -> L2), production card
                                (L2 -> L1), and a reading card if the entry
                                carries an example sentence
* grammar example (prompt/answer) -> one translation or cloze card

Ordering is deterministic: entries are sorted by a stable key, then the final
list is shuffled with a seeded RNG. The same seed and the same pack always
produce the same sequence of items, which is what makes the generator testable
and reproducible.

Language-specific behaviour lives entirely in the pack's `meta` block (script,
tokenizer, RTL). The generator never branches on a language code.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lesan_pipe.models import GrammarEntry, LanguagePack, VocabularyEntry

RECOGNITION = "recognition"
PRODUCTION = "production"
READING = "reading"
GRAMMAR = "grammar"


def vocab_note_key(stage: int, l1: str, l2: str) -> str:
    """Stable identity for a vocabulary note: one pack entry, one key.

    The English gloss (``l1``) repeats across stages (e.g. 国/stage-1 and
    国家/stage-3 are both "country, nation") and even within a stage
    (e.g. two stage-1 entries for 多), so a gloss-only key collapses
    distinct notes and mis-attributes cards. The (stage, l1, l2) triple
    is unique within a pack, which keeps the ``generate`` note lookup 1:1.
    ``front``/``back`` are untouched, so sync identity (SHA-256 of
    front+back) is stable.
    """
    return f"vocab:{stage}\x1f{l1}\x1f{l2}"


def grammar_note_key(stage: int, name: str) -> str:
    """Stable identity for a grammar note: one pack entry, one key."""
    return f"grammar:{stage}\x1f{name}"


@dataclass(frozen=True)
class GeneratedItem:
    """One practice card to be materialised as a note plus a card."""

    kind: str  # "vocab" | "grammar"
    front: str
    back: str
    stage: int
    template: str
    prompt: str
    answer: str
    pos: str = ""
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def load_pack(path: str | Path) -> LanguagePack:
    """Parse a language pack file (JSON)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return LanguagePack.model_validate(raw)


def _vocab_key(v: VocabularyEntry) -> tuple[int, str, str]:
    return (v.stage, v.l1, v.l2)


def _grammar_key(g: GrammarEntry) -> tuple[int, str]:
    return (g.stage, g.name)


def _items_for_vocab(v: VocabularyEntry) -> list[GeneratedItem]:
    items = [
        GeneratedItem(
            kind="vocab",
            front=v.l1,
            back=v.l2,
            stage=v.stage,
            template=RECOGNITION,
            prompt=v.l1,
            answer=v.l2,
            pos=v.pos,
            tags=list(v.tags),
            extra={
                "key": vocab_note_key(v.stage, v.l1, v.l2),
                "example": v.example,
                "example_translation": v.example_translation,
            },
        ),
        GeneratedItem(
            kind="vocab",
            front=v.l2,
            back=v.l1,
            stage=v.stage,
            template=PRODUCTION,
            prompt=v.l2,
            answer=v.l1,
            pos=v.pos,
            tags=list(v.tags),
            extra={"key": vocab_note_key(v.stage, v.l1, v.l2)},
        ),
    ]
    if v.example:
        items.append(
            GeneratedItem(
                kind="vocab",
                front=v.example,
                back=v.example_translation,
                stage=v.stage,
                template=READING,
                prompt=v.example,
                answer=v.example_translation,
                pos=v.pos,
                tags=list(v.tags),
                extra={"key": vocab_note_key(v.stage, v.l1, v.l2)},
            )
        )
    return items


def _items_for_grammar(g: GrammarEntry) -> list[GeneratedItem]:
    items: list[GeneratedItem] = []
    for ex in g.examples:
        prompt = ex.get("prompt", "")
        answer = ex.get("answer", "")
        if not prompt or not answer:
            continue
        items.append(
            GeneratedItem(
                kind="grammar",
                front=prompt,
                back=answer,
                stage=g.stage,
                template=GRAMMAR,
                prompt=prompt,
                answer=answer,
                tags=["grammar"],
                extra={
                    "key": grammar_note_key(g.stage, g.name),
                    "name": g.name,
                    "explanation": g.explanation,
                },
            )
        )
    return items


def generate_items(
    pack: LanguagePack, stage: int, seed: int, count: int | None = None
) -> list[GeneratedItem]:
    """Generate the practice items for one stage, deterministically.

    `count` caps the number of items returned (after shuffling). The shuffle is
    seeded, so `generate_items(pack, 1, 42)` is byte-for-byte reproducible.
    """
    vocab = sorted(
        (v for v in pack.vocabulary if v.stage == stage),
        key=_vocab_key,
    )
    grammar = sorted(
        (g for g in pack.grammar if g.stage == stage),
        key=_grammar_key,
    )

    items: list[GeneratedItem] = []
    for v in vocab:
        items.extend(_items_for_vocab(v))
    for g in grammar:
        items.extend(_items_for_grammar(g))

    rng = random.Random(seed)
    rng.shuffle(items)

    if count is not None:
        items = items[:count]
    return items
