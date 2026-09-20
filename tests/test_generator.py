"""Deterministic generator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from lesan_pipe.generator import generate_items, load_pack
from lesan_pipe.models import LanguagePack

PACK_PATH = Path(__file__).parent.parent / "src" / "lesan_pipe" / "packs" / "demo-spanish.json"


@pytest.fixture(scope="module")
def pack() -> LanguagePack:
    return load_pack(PACK_PATH)


def test_load_pack_counts(pack: LanguagePack) -> None:
    assert len(pack.vocabulary) == 56
    assert len(pack.grammar) == 8


def test_generator_same_seed_same_output(pack: LanguagePack) -> None:
    a = generate_items(pack, 1, 42)
    b = generate_items(pack, 1, 42)
    assert [(i.template, i.prompt, i.answer) for i in a] == [
        (i.template, i.prompt, i.answer) for i in b
    ]


def test_generator_different_seed_differs(pack: LanguagePack) -> None:
    a = [i.prompt for i in generate_items(pack, 1, 42)]
    b = [i.prompt for i in generate_items(pack, 1, 7)]
    assert a != b
    # same multiset, different order
    assert sorted(a) == sorted(b)


def test_generator_vocab_templates(pack: LanguagePack) -> None:
    vocab_items = [i for i in generate_items(pack, 1, 42) if i.kind == "vocab"]
    templates = {i.template for i in vocab_items}
    assert "recognition" in templates
    assert "production" in templates


def test_generator_reading_card_from_example(pack: LanguagePack) -> None:
    reading = [i for i in generate_items(pack, 1, 42) if i.template == "reading"]
    prompts = {i.prompt for i in reading}
    assert "El perro es grande." in prompts


def test_generator_grammar_examples(pack: LanguagePack) -> None:
    grammar = [i for i in generate_items(pack, 1, 42) if i.kind == "grammar"]
    # stage 1 has two grammar points with two examples each
    assert len(grammar) == 4


def test_generator_count_cap(pack: LanguagePack) -> None:
    items = generate_items(pack, 1, 42, count=10)
    assert len(items) == 10


def test_generator_is_seeded_and_deterministic(pack: LanguagePack) -> None:
    first = [(i.template, i.prompt) for i in generate_items(pack, 1, 1234)]
    second = [(i.template, i.prompt) for i in generate_items(pack, 1, 1234)]
    assert first == second
