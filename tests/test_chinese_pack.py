"""Chinese HSK pack: the real-deck pack expresses the study plan.

The pack ``src/lesan_pipe/packs/chinese-hsk1-4.json`` is generated from
the Natural Language Journey HSK 1-4 Anki deck by
``scripts/build_chinese_pack.py`` (the .apkg itself lives outside the
repo, so these tests pin the COMMITTED artifact, not the deck).

WHY these tests exist: they are the acceptance proof that the pipeline
covers Mina's Chinese plan at least as well as the Anki-only workflow
it replaces -- HSK levels as stages, lesson order kept for pacing,
every entry generating recognition + production + reading cards.
"""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lesan_pipe.cli import app
from lesan_pipe.generator import generate_items, load_pack
from lesan_pipe.models import LanguagePack

PACK_PATH = Path(__file__).parent.parent / "src" / "lesan_pipe" / "packs" / "chinese-hsk1-4.json"
runner = CliRunner()


@pytest.fixture(scope="module")
def pack() -> LanguagePack:
    return load_pack(PACK_PATH)


def test_pack_is_han_script_char_tokenizer(pack: LanguagePack) -> None:
    """Chinese must declare its own script/tokenizer: the generator never
    branches on language code, so these two meta fields are the ONLY
    thing that makes this pack Chinese to the pipeline."""
    assert pack.meta["language_code"] == "zh"
    assert pack.meta["script"] == "han"
    assert pack.meta["tokenizer"] == "char"


def test_stage_counts_match_deck_hsk_tags(pack: LanguagePack) -> None:
    """Stage = HSK level, with the deck's exact distribution. WHY: if a
    rebuild silently dropped or restaged notes, pacing against the HSK
    levels would lie."""
    counts = {stage: 0 for stage in (1, 2, 3, 4)}
    for v in pack.vocabulary:
        counts[v.stage] += 1
    assert counts == {1: 203, 2: 191, 3: 335, 4: 728}
    assert len(pack.vocabulary) == 1457


def test_lesson_order_preserved_within_stage(pack: LanguagePack) -> None:
    """File order within a stage is non-decreasing lesson: the weekly
    unlock rhythm (3-5 lessons per block) reads the pack in order."""

    def lesson(entry) -> int:
        for tag in entry.tags:
            if tag.startswith("lesson-"):
                return int(tag.split("-")[1])
        return 999

    for stage, group in groupby(pack.vocabulary, key=lambda v: v.stage):
        lessons = [lesson(v) for v in group]
        assert lessons == sorted(lessons), f"stage {stage} out of lesson order"


def test_lesson_tags_cover_lessons_01_to_20(pack: LanguagePack) -> None:
    tags = {t for v in pack.vocabulary for t in v.tags if t.startswith("lesson-")}
    assert tags == {f"lesson-{n:02d}" for n in range(1, 21)}


def test_every_entry_tagged_hsk_or_documented_untagged(pack: LanguagePack) -> None:
    """Exactly one deck note (死) carries no HSK tag and no lesson; it is
    kept in stage 4 as 'untagged', never silently dropped or invented
    into a level."""
    untagged = [v for v in pack.vocabulary if "untagged" in v.tags]
    assert len(untagged) == 1
    assert untagged[0].l2 == "死"
    assert untagged[0].stage == 4
    for v in pack.vocabulary:
        assert any(t in ("HSK1", "HSK2", "HSK3", "HSK4", "untagged") for t in v.tags)


def test_spot_check_nihao(pack: LanguagePack) -> None:
    entry = next(v for v in pack.vocabulary if v.l2 == "你好")
    assert entry.l1 == "hello"
    assert entry.stage == 1
    assert "HSK1" in entry.tags and "lesson-01" in entry.tags
    assert entry.example == "你好！"
    assert entry.example_translation == "Hello!"


def test_missing_translation_yields_no_reading_card(pack: LanguagePack) -> None:
    """城市 lacks an English sentence in the deck. It must still yield
    recognition + production cards but no reading card: inventing the
    missing translation would violate the grounding rules."""
    items = [i for i in generate_items(pack, 3, 42) if i.answer == "城市" or i.prompt == "城市"]
    assert {i.template for i in items} == {"recognition", "production"}


def test_stage_generates_three_cards_per_entry(pack: LanguagePack) -> None:
    """Stage 1 (203 entries, all with example sentences) expands to
    203 x 3 cards: recognition (EN->ZH) + production (ZH->EN) +
    reading (sentence). This is the parity-with-Anki claim: the deck's
    two templates per note are fully expressed."""
    items = generate_items(pack, 1, 42)
    assert len(items) == 203 * 3
    # Same seed reproduces the exact sequence (deterministic pipeline).
    again = [(i.template, i.prompt, i.answer) for i in generate_items(pack, 1, 42)]
    assert [(i.template, i.prompt, i.answer) for i in items] == again


def test_chinese_end_to_end(tmp_path) -> None:
    """Full pipeline on the real pack: init reports han/char and 1457
    items, plan lists the four stages, generate + mock sync work, and
    re-sync adds zero (idempotent on real data)."""
    db = tmp_path / "zh.db"
    init = runner.invoke(
        app, ["init", "--db", str(db), "--pack", str(PACK_PATH), "--lang", "zh", "--name", "Mina"]
    )
    assert init.exit_code == 0, init.output
    assert "1457 vocabulary items" in init.output
    assert "Script: han, tokenizer: char" in init.output

    plan = runner.invoke(app, ["plan", "--db", str(db)])
    assert plan.exit_code == 0
    assert "stage 1 (bridge): 300 vocab" in plan.output
    assert "stage 4 (fluency): 2500 vocab" in plan.output

    gen = runner.invoke(app, ["generate", "--db", str(db), "--stage", "1", "--seed", "42"])
    assert gen.exit_code == 0
    assert "Generated 609 cards for stage 1" in gen.output

    sync = runner.invoke(app, ["sync", "--db", str(db), "--mock", "--stage", "1"])
    assert sync.exit_code == 0, sync.output
    assert "notes added" in sync.output

    resync = runner.invoke(app, ["sync", "--db", str(db), "--mock", "--stage", "1"])
    assert resync.exit_code == 0
    assert "0 notes added" in resync.output
