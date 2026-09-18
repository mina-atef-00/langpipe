"""Command-line interface for langpipe.

Commands: init, plan, generate, cards, review, stats, sync. Run
``langpipe --help`` for the full list and per-command help.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import typer

from langpipe.analytics import compute_report, render_report
from langpipe.anki import AnkiConnectBackend, MockAnkiBackend, SyncNote
from langpipe.curriculum import DEFAULT_STAGES
from langpipe.db import Database
from langpipe.generator import generate_items, load_pack
from langpipe.models import (
    Card,
    CurriculumStage,
    Deck,
    Language,
    LearnerState,
    Note,
    utcnow,
)
from langpipe.scheduler import Scheduler

app = typer.Typer(
    name="langpipe",
    help="A language-agnostic learning pipeline: curriculum, graded practice, "
    "spaced repetition, and retention analytics.",
    no_args_is_help=True,
)

BUNDLED_PACK = Path(__file__).parent / "packs" / "demo-spanish.json"
DEFAULT_DB = "langpipe.db"


def _open_db(db_path: str) -> Database:
    return Database(db_path)


def _require_learner(db: Database) -> LearnerState:
    learner = db.get_learner()
    if learner is None:
        typer.echo("No learner yet. Run `langpipe init` first.", err=True)
        raise typer.Exit(code=1)
    return learner


def _resolve_pack(db: Database, pack_arg: str | None) -> Path:
    if pack_arg:
        return Path(pack_arg)
    stored = db.get_meta("pack_path")
    if stored:
        return Path(stored)
    return BUNDLED_PACK


@app.command()
def init(
    name: str = typer.Option("Learner", "--name", help="Learner name."),
    lang: str = typer.Option("es", "--lang", help="Target language code (ISO 639-1)."),
    pack: str = typer.Option(
        str(BUNDLED_PACK), "--pack", help="Path to a language pack JSON file."
    ),
    seed: int = typer.Option(42, "--seed", help="Seed for deterministic generation."),
    daily: int = typer.Option(10, "--daily", help="New cards per day target."),
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
) -> None:
    """Create a fresh learner, curriculum, and database from a language pack."""
    db_path = Path(db)
    if db_path.exists():
        db_path.unlink()

    database = _open_db(db)
    try:
        pack_obj = load_pack(pack)
    except FileNotFoundError:
        typer.echo(f"Language pack not found: {pack}", err=True)
        raise typer.Exit(code=1) from None

    meta = pack_obj.meta
    language = Language(
        code=meta.get("language_code", lang),
        name=meta.get("language_name", lang),
        script=meta.get("script", "latin"),
        tokenizer=meta.get("tokenizer", "word"),
        rtl=bool(meta.get("rtl", False)),
        note=meta.get("note", ""),
    )
    database.upsert_language(language)

    deck_id = database.add_deck(
        Deck(id=0, name=meta.get("name", "default"), language_code=language.code)
    )
    database.set_stages(DEFAULT_STAGES)

    for v in pack_obj.vocabulary:
        database.add_note(
            Note(
                id=0,
                deck_id=deck_id,
                kind="vocab",
                front=v.l1,
                back=v.l2,
                stage=v.stage,
                pos=v.pos,
                tags=list(v.tags),
                extra={
                    "key": f"vocab:{v.l1}",
                    "example": v.example,
                    "example_translation": v.example_translation,
                },
            )
        )
    for g in pack_obj.grammar:
        database.add_note(
            Note(
                id=0,
                deck_id=deck_id,
                kind="grammar",
                front=g.name,
                back=g.explanation,
                stage=g.stage,
                tags=["grammar"],
                extra={"key": f"grammar:{g.name}"},
            )
        )

    database.set_learner(
        LearnerState(
            id=1,
            name=name,
            target_language=language.code,
            start_date=utcnow(),
            current_stage=1,
            daily_new_cards=daily,
            seed=seed,
        )
    )
    database.set_meta("pack_path", str(Path(pack).resolve()))
    database.set_meta("pack_name", meta.get("name", "default"))
    database.set_meta("seed", str(seed))

    vocab_count = len(pack_obj.vocabulary)
    grammar_count = len(pack_obj.grammar)
    typer.echo(f"Initialised learner '{name}' learning {language.name} ({language.code}).")
    typer.echo(
        f"Loaded pack '{meta.get('name', 'default')}': "
        f"{vocab_count} vocabulary items, {grammar_count} grammar points."
    )
    typer.echo(f"Script: {language.script}, tokenizer: {language.tokenizer}, rtl: {language.rtl}")
    typer.echo(f"Seed: {seed}. Next: `langpipe plan` to see the plan, then `langpipe generate`.")


@app.command()
def plan(db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path.")) -> None:
    """Print the phased curriculum with targets."""
    database = _open_db(db)
    _require_learner(database)
    stages: list[CurriculumStage] = database.list_stages()
    if not stages:
        typer.echo("No curriculum stages. Run `langpipe init` first.", err=True)
        raise typer.Exit(code=1)
    typer.echo("Curriculum plan")
    for s in stages:
        typer.echo(
            f"  stage {s.order} ({s.name}): {s.target_vocab} vocab, {s.target_grammar} grammar"
        )
        typer.echo(f"      {s.description}")
    database.close()


@app.command()
def generate(
    stage: int = typer.Option(1, "--stage", help="Curriculum stage (1-based)."),
    seed: int = typer.Option(42, "--seed", help="Seed for deterministic generation."),
    count: int = typer.Option(0, "--count", help="Cap on cards (0 = all)."),
    pack: str = typer.Option(None, "--pack", help="Override language pack path."),
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
) -> None:
    """Generate practice cards for a stage from the language pack."""
    database = _open_db(db)
    _require_learner(database)
    pack_obj = load_pack(_resolve_pack(database, pack))
    items = generate_items(pack_obj, stage, seed, count or None)

    notes = database.list_notes()
    key_to_note = {n.extra.get("key"): n.id for n in notes if n.extra.get("key")}

    created: list[Card] = []
    for item in items:
        note_id = key_to_note.get(item.extra.get("key"))
        if note_id is None:
            continue
        card = Card(
            id=0,
            note_id=note_id,
            template=item.template,
            prompt=item.prompt,
            answer=item.answer,
            stage=item.stage,
            due=utcnow(),
        )
        card.id = database.add_card(card)
        created.append(card)

    typer.echo(f"Generated {len(created)} cards for stage {stage} (seed {seed}).")
    for c in created:
        typer.echo(f"  [{c.id}] {c.template:12s} {c.prompt!r} -> {c.answer!r}")
    database.close()


@app.command()
def cards(
    stage: int = typer.Option(0, "--stage", help="Filter by stage (0 = all)."),
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
) -> None:
    """List cards in the database."""
    database = _open_db(db)
    _require_learner(database)
    all_cards = database.list_cards()
    shown = [c for c in all_cards if stage == 0 or c.stage == stage]
    for c in shown:
        typer.echo(
            f"  [{c.id}] stage {c.stage} {c.template:12s} due {c.due.date()} "
            f"interval {c.interval}d {c.prompt!r}"
        )
    database.close()


@app.command()
def review(
    card_id: int = typer.Argument(..., help="Card ID to review."),
    grade: int = typer.Option(..., "--grade", help="Recall grade 0-5 (0 blackout, 5 perfect)."),
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
) -> None:
    """Record a review of one card and reschedule it."""
    database = _open_db(db)
    _require_learner(database)
    card = database.get_card(card_id)
    if card is None:
        typer.echo(f"No card with id {card_id}.", err=True)
        database.close()
        raise typer.Exit(code=1)

    scheduler = Scheduler()
    updated, event = scheduler.review(card, grade)
    database.update_card(updated)
    event_id = database.add_review(event)

    typer.echo(
        f"Card {card_id} graded {grade}: interval {event.interval_before}d -> "
        f"{event.interval_after}d, ease {event.ease_before:.2f} -> {event.ease_after:.2f}, "
        f"due {updated.due.date()} (review #{event_id})."
    )
    database.close()


@app.command()
def stats(db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path.")) -> None:
    """Print the analytics report."""
    database = _open_db(db)
    _require_learner(database)
    typer.echo(render_report(compute_report(database)))
    database.close()


@app.command()
def sync(
    deck: str = typer.Option("langpipe", "--deck", help="Anki deck name."),
    stage: int = typer.Option(0, "--stage", help="Only export this stage (0 = all)."),
    mock: bool = typer.Option(False, "--mock", help="Use the in-memory mock backend."),
    url: str = typer.Option("http://127.0.0.1:8765", "--url", help="AnkiConnect base URL."),
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
) -> None:
    """Export cards to Anki through AnkiConnect (or the mock backend)."""
    database = _open_db(db)
    _require_learner(database)
    all_cards = database.list_cards()
    selected = [c for c in all_cards if stage == 0 or c.stage == stage]
    if not selected:
        typer.echo("No cards to sync. Run `langpipe generate` first.", err=True)
        database.close()
        raise typer.Exit(code=1)

    # Content-keyed duplicate detection: a note's identity is the hash of its
    # front and back. The set of already-synced identities is stored in the
    # database, so re-running sync skips notes the backend already has and is
    # idempotent across runs (a fresh in-memory backend per run still counts).
    def note_key(front: str, back: str) -> str:
        return hashlib.sha256(f"{front}\x1f{back}".encode()).hexdigest()

    synced_key = f"synced_notes:{deck}:{stage}"
    already_synced = {
        k for k in (database.get_meta(synced_key) or "").split(",") if k
    }
    fresh_cards = [c for c in selected if note_key(c.prompt, c.answer) not in already_synced]
    notes = [
        SyncNote(front=c.prompt, back=c.answer, tags=[c.template, f"stage-{c.stage}"])
        for c in fresh_cards
    ]

    backend = MockAnkiBackend() if mock else AnkiConnectBackend(url)
    result = backend.sync(notes, deck)
    if not result.reachable:
        typer.echo(
            f"Sync failed: {result.error}",
            err=True,
        )
        typer.echo(
            "AnkiConnect was not reachable. Start Anki with the AnkiConnect add-on, "
            "or use `--mock` to run against the in-memory backend.",
            err=True,
        )
        database.close()
        raise typer.Exit(code=1)

    # Record the content-keyed note-identity of the notes the backend just
    # accepted, so a later re-sync skips them and stays idempotent.
    synced_key = f"synced_notes:{deck}:{stage}"
    previously_synced = {
        k for k in (database.get_meta(synced_key) or "").split(",") if k
    }
    accepted_hashes = [
        note_key(c.prompt, c.answer)
        for c, ok in zip(fresh_cards, result.accepted, strict=False)
        if ok
    ]
    database.set_meta(
        synced_key,
        ",".join(sorted(previously_synced | set(accepted_hashes))),
    )

    typer.echo(f"Sync to backend '{result.backend}' (deck '{deck}'):")
    typer.echo(f"  {result.notes_added} notes added.")
    typer.echo(f"  note ids: {result.note_ids}")
    database.close()


if __name__ == "__main__":
    app()
