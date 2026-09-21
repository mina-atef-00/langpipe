"""Command-line interface for lesan_pipe.

Commands: init, plan, generate, cards, review, stats, sync. Run
``lesan_pipe --help`` for the full list and per-command help.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import typer

from lesan_pipe.analytics import compute_report, render_report
from lesan_pipe.anki import AnkiConnectBackend, MockAnkiBackend, SyncNote
from lesan_pipe.curriculum import DEFAULT_STAGES
from lesan_pipe.db import Database
from lesan_pipe.generator import generate_items, grammar_note_key, load_pack, vocab_note_key
from lesan_pipe.models import (
    Card,
    CurriculumStage,
    Deck,
    Language,
    LearnerState,
    Note,
    utcnow,
)
from lesan_pipe.scheduler import Scheduler

app = typer.Typer(
    name="lesan_pipe",
    help="A language-agnostic learning pipeline: curriculum, graded practice, "
    "spaced repetition, and retention analytics.",
    no_args_is_help=True,
)

BUNDLED_PACK = Path(__file__).parent / "packs" / "demo-spanish.json"
DEFAULT_DB = "lesan_pipe.db"


def _open_db(db_path: str) -> Database:
    return Database(db_path)


def _open_existing_db(db_path: str) -> Database:
    """Open an existing database, failing without creating one.

    ``Database`` creates the SQLite file on connect, so commands that
    require a prior ``init`` must check first: a typo'd ``--db`` path
    must error, not scatter an empty database file as a side effect.
    """
    if not Path(db_path).exists():
        typer.echo(
            f"No database found at {db_path}. Run `lesan_pipe init` first.",
            err=True,
        )
        raise typer.Exit(code=1)
    return Database(db_path)


def _require_learner(db: Database) -> LearnerState:
    learner = db.get_learner()
    if learner is None:
        typer.echo("No learner yet. Run `lesan_pipe init` first.", err=True)
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
    force: bool = typer.Option(
        False, "--force", help="Overwrite the existing database if one exists."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human-readable text."
    ),
) -> None:
    """Create a fresh learner, curriculum, and database from a language pack.

    Refuses to delete an existing database unless --force is given. The
    language pack is validated before any existing database is touched,
    so a bad --pack path never destroys good data.
    """
    try:
        pack_obj = load_pack(pack)
    except FileNotFoundError:
        typer.echo(f"Language pack not found: {pack}", err=True)
        raise typer.Exit(code=1) from None

    db_path = Path(db)
    if db_path.exists() and not force:
        typer.echo(
            f"Database already exists: {db}. Use --force to overwrite it.",
            err=True,
        )
        raise typer.Exit(code=1)
    if db_path.exists():
        db_path.unlink()

    database = _open_db(db)

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
                    "key": vocab_note_key(v.stage, v.l1, v.l2),
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
                extra={"key": grammar_note_key(g.stage, g.name)},
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
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "learner": name,
                    "language_code": language.code,
                    "language_name": language.name,
                    "pack": meta.get("name", "default"),
                    "vocab_count": vocab_count,
                    "grammar_count": grammar_count,
                    "seed": seed,
                    "db": db,
                },
                indent=2,
            )
        )
        return
    typer.echo(f"Initialised learner '{name}' learning {language.name} ({language.code}).")
    typer.echo(
        f"Loaded pack '{meta.get('name', 'default')}': "
        f"{vocab_count} vocabulary items, {grammar_count} grammar points."
    )
    typer.echo(f"Script: {language.script}, tokenizer: {language.tokenizer}, rtl: {language.rtl}")
    typer.echo(
        f"Seed: {seed}. Next: `lesan_pipe plan` to see the plan, then `lesan_pipe generate`."
    )


@app.command()
def plan(
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human-readable text."
    ),
) -> None:
    """Print the phased curriculum with targets.

    Never creates the database: if no database exists yet, this fails
    instead of leaving an empty file behind.
    """
    database = _open_existing_db(db)
    _require_learner(database)
    stages: list[CurriculumStage] = database.list_stages()
    if not stages:
        typer.echo("No curriculum stages. Run `lesan_pipe init` first.", err=True)
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "stages": [
                        {
                            "order": s.order,
                            "name": s.name,
                            "target_vocab": s.target_vocab,
                            "target_grammar": s.target_grammar,
                            "description": s.description,
                        }
                        for s in stages
                    ]
                },
                indent=2,
            )
        )
        database.close()
        return
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
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human-readable text."
    ),
) -> None:
    """Generate practice cards for a stage from the language pack."""
    database = _open_existing_db(db)
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

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "stage": stage,
                    "seed": seed,
                    "count": len(created),
                    "cards": [
                        {
                            "id": c.id,
                            "template": c.template,
                            "prompt": c.prompt,
                            "answer": c.answer,
                        }
                        for c in created
                    ],
                },
                indent=2,
            )
        )
        database.close()
        return
    typer.echo(f"Generated {len(created)} cards for stage {stage} (seed {seed}).")
    for c in created:
        typer.echo(f"  [{c.id}] {c.template:12s} {c.prompt!r} -> {c.answer!r}")
    database.close()


@app.command()
def cards(
    stage: int = typer.Option(0, "--stage", help="Filter by stage (0 = all)."),
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human-readable text."
    ),
) -> None:
    """List cards in the database."""
    database = _open_existing_db(db)
    _require_learner(database)
    all_cards = database.list_cards()
    shown = [c for c in all_cards if stage == 0 or c.stage == stage]
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "cards": [
                        {
                            "id": c.id,
                            "stage": c.stage,
                            "template": c.template,
                            "prompt": c.prompt,
                            "answer": c.answer,
                            "due": c.due.isoformat(),
                            "interval": c.interval,
                            "ease": c.ease,
                            "reps": c.reps,
                            "lapses": c.lapses,
                        }
                        for c in shown
                    ]
                },
                indent=2,
            )
        )
        database.close()
        return
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
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human-readable text."
    ),
) -> None:
    """Record a review of one card and reschedule it."""
    if not 0 <= grade <= 5:
        typer.echo(f"Grade must be between 0 and 5, got {grade}.", err=True)
        raise typer.Exit(code=1)

    database = _open_existing_db(db)
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

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "card_id": card_id,
                    "grade": grade,
                    "review_id": event_id,
                    "interval_before": event.interval_before,
                    "interval_after": event.interval_after,
                    "ease_before": event.ease_before,
                    "ease_after": event.ease_after,
                    "due": updated.due.isoformat(),
                },
                indent=2,
            )
        )
        database.close()
        return
    typer.echo(
        f"Card {card_id} graded {grade}: interval {event.interval_before}d -> "
        f"{event.interval_after}d, ease {event.ease_before:.2f} -> {event.ease_after:.2f}, "
        f"due {updated.due.date()} (review #{event_id})."
    )
    database.close()


@app.command()
def stats(
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human-readable text."
    ),
) -> None:
    """Print the analytics report."""
    database = _open_existing_db(db)
    _require_learner(database)
    report = compute_report(database)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "total_reviews": report.total_reviews,
                    "passed_reviews": report.passed_reviews,
                    "lapsed_reviews": report.lapsed_reviews,
                    "retention_rate": report.retention_rate,
                    "lapse_rate": report.lapse_rate,
                    "total_cards": report.total_cards,
                    "backlog": report.backlog,
                    "forecast_7d": report.forecast_7d,
                    "forecast_30d": report.forecast_30d,
                    "stages": [
                        {
                            "order": s.stage.order,
                            "name": s.stage.name,
                            "target_vocab": s.stage.target_vocab,
                            "target_grammar": s.stage.target_grammar,
                            "vocab_learned": s.vocab_learned,
                            "grammar_learned": s.grammar_learned,
                            "vocab_pct": s.vocab_pct,
                            "grammar_pct": s.grammar_pct,
                        }
                        for s in report.stages
                    ],
                },
                indent=2,
            )
        )
        database.close()
        return
    typer.echo(render_report(report))
    database.close()


@app.command()
def sync(
    deck: str = typer.Option("lesan_pipe", "--deck", help="Anki deck name."),
    stage: int = typer.Option(0, "--stage", help="Only export this stage (0 = all)."),
    mock: bool = typer.Option(False, "--mock", help="Use the in-memory mock backend."),
    url: str = typer.Option("http://127.0.0.1:8765", "--url", help="AnkiConnect base URL."),
    db: str = typer.Option(DEFAULT_DB, "--db", help="SQLite database path."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human-readable text."
    ),
) -> None:
    """Export cards to Anki through AnkiConnect (or the mock backend)."""
    database = _open_existing_db(db)
    _require_learner(database)
    all_cards = database.list_cards()
    selected = [c for c in all_cards if stage == 0 or c.stage == stage]
    if not selected:
        typer.echo("No cards to sync. Run `lesan_pipe generate` first.", err=True)
        database.close()
        raise typer.Exit(code=1)

    # Content-keyed duplicate detection: a note's identity is the hash of its
    # front and back. The set of already-synced identities is stored in the
    # database, so re-running sync skips notes the backend already has and is
    # idempotent across runs (a fresh in-memory backend per run still counts).
    def note_key(front: str, back: str) -> str:
        return hashlib.sha256(f"{front}\x1f{back}".encode()).hexdigest()

    def ledger(database: Database, deck_name: str) -> set[str]:
        """Content keys already synced to this deck.

        Read from *every* `synced_notes:<deck>:*` record, not just the one for
        the stage filter used on this run. The stage component is bookkeeping
        (what a given run exported); note identity is per deck, so filtering on
        a single stage key would re-send, and on the mock backend re-add, notes
        that a different stage filter had already pushed.
        """
        prefix = f"synced_notes:{deck_name}:"
        keys: set[str] = set()
        for key, value in database.meta_entries():
            if key.startswith(prefix):
                keys.update(k for k in value.split(",") if k)
        return keys

    synced_key = f"synced_notes:{deck}:{stage}"
    already_synced = ledger(database, deck)
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
    # accepted, so a later re-sync skips them and stays idempotent. Only notes
    # the backend actually wrote are recorded: a note it refused is left out of
    # the ledger so the next run retries it.
    previously_synced = ledger(database, deck)
    accepted_hashes = [
        note_key(c.prompt, c.answer)
        for c, ok in zip(fresh_cards, result.accepted, strict=False)
        if ok
    ]
    database.set_meta(
        synced_key,
        ",".join(sorted(previously_synced | set(accepted_hashes))),
    )

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "backend": result.backend,
                    "deck": deck,
                    "stage": stage,
                    "notes_added": result.notes_added,
                    "note_ids": result.note_ids,
                    "notes_refused": result.notes_refused,
                    "error": result.error,
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"Sync to backend '{result.backend}' (deck '{deck}'):")
        typer.echo(f"  {result.notes_added} notes added.")
        typer.echo(f"  note ids: {result.note_ids}")
    if result.notes_refused:
        typer.echo(
            f"Sync incomplete: {result.error}. "
            f"{result.notes_refused} note(s) were refused by Anki and are NOT recorded "
            "as synced; re-run sync to retry them.",
            err=True,
        )
        database.close()
        raise typer.Exit(code=1)
    database.close()


if __name__ == "__main__":
    app()
