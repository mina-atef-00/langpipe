# SPEC

Internal specification for langpipe. The user-facing documentation lives in [README.md](README.md); this document covers how the pipeline actually works.

## Scope

langpipe is a language-agnostic learning pipeline. It takes a language pack (vocabulary and grammar entries in JSON), generates practice cards with a deterministic rule-based generator, schedules reviews with SuperMemo SM-2, computes retention analytics from the review log, and can export to Anki through AnkiConnect. The runtime dependencies are `typer` and `pydantic`; storage is SQLite.

Nothing in the code branches on a language. Language-specific behaviour is data: `script`, `tokenizer`, and `rtl` on the `Language` record, carried in from the pack's `meta` block and shown by `init`.

## SM-2 scheduling

The scheduler ([`src/langpipe/scheduler.py`](src/langpipe/scheduler.py)) implements classic SuperMemo SM-2, described by Piotr Wozniak's SuperMemo algorithm write-up. Anki's default schedule is a modified SM-2, so behaviour will be familiar to Anki users.

Constants:

| Constant | Value | Meaning |
|---|---|---|
| `STARTING_EASE` | 2.5 | ease factor at card creation |
| `MIN_EASE` | 1.3 | ease floor |
| `PASS_THRESHOLD` | 3 | grade >= 3 is a pass; below is a lapse |
| `MAX_GRADE` | 5 | highest grade |

Update rule, applied by `Scheduler.review(card, grade, when=None)`:

1. Validate the grade is in 0..5.
2. If `grade < 3` (lapse): `reps := 0`, `interval := 1`, `lapses += 1`, ease unchanged.
3. If `grade >= 3` (pass):
   - `reps == 0`: `interval := 1`
   - `reps == 1`: `interval := 6`
   - otherwise: `interval := round(previous interval * ease)`
   - `reps += 1`, then update ease:
   ```
   EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
   ```
   clamped so `EF' >= 1.3`. Note the ease is updated only on passes (lapses leave ease unchanged, which also matches SM-2's frequently-glossed behaviour in Wozniak's rules: EF is "undecreased" after lapses).
4. `due := reviewed_at + interval days`.

All timestamps are UTC, stored as naive datetimes (UTC stripped), per `langpipe.models.utcnow()`. The `when` argument is injectable so tests can pin time.

The scheduler is deterministic: the same card state and grade sequence always produces the same intervals and ease factors.

## Data model

Pydantic models in [src/langpipe/models.py](src/langpipe/models.py); SQLite persistence in [src/langpipe/db.py](src/langpipe/db.py). The rest of the code never writes SQL directly.

| Model | Purpose | Key fields |
|---|---|---|
| `Language` | A natural language as data (frozen). | `code`, `name`, `script` (default `latin`), `tokenizer` (`word`), `rtl`, `note` |
| `Deck` | A named collection of notes. | `name`, `language_code` |
| `Note` | A piece of knowledge: a word or grammar point. | `deck_id`, `kind` (`vocab` \| `grammar`), `front`, `back`, `stage`, `pos`, `tags`, `extra` |
| `Card` | A schedulable unit derived from a note. | `note_id`, `template` (`recognition` / `production` / `reading` / `grammar`), `prompt`, `answer`, `stage`, `due`, `interval=0`, `ease=2.5`, `reps=0`, `lapses=0` |
| `ReviewEvent` | One graded review, appended. | `card_id`, `grade`, `reviewed_at`, `interval_before/after`, `ease_before/after` |
| `CurriculumStage` | One phase of the curriculum. | `order`, `name`, `target_vocab`, `target_grammar`, `description` |
| `LearnerState` | The learner and where they are. | `name`, `target_language`, `start_date`, `current_stage=1`, `daily_new_cards=10`, `seed=42` |
| `LanguagePack` | Parsed pack file. | `meta: dict`, `vocabulary: list[VocabularyEntry]`, `grammar: list[GrammarEntry]` |

Design invariant: every review is written to `review_events` with the interval and ease before and after. Analytics never recompute history from a summary; they read the log.

Note `extra` carries a content `key` (`vocab:<l1>` or `grammar:<name>`) used to link generated cards back to notes.

## Curriculum

Four default stages (set at `init` from `langpipe.curriculum.DEFAULT_STAGES`):

1. **bridge** — 300 vocab, 20 grammar. Vocabulary front-load, SRS-heavy schedule.
2. **input** — 800 vocab, 40 grammar. Graded readers and slow audio, sentence mining starts.
3. **expansion** — 1500 vocab, 60 grammar. Native-adjacent content, production begins.
4. **fluency** — 2500 vocab, 80 grammar. Review-only SRS, most time on native content and production.

These override-adjustable targets are printed by `plan` and drive the per-stage progress percentages in `stats`. The bundled demo pack contains only 56 vocabulary items and 8 grammar points, so percentages start small on purpose.

## Generator and language packs

The generator ([src/langpipe/generator.py](src/langpipe/generator.py)) is seeded, rule-based, and produces the same output for the same seed. No language model is involved.

A language pack is a JSON file with `meta`, `vocabulary`, and `grammar` sections. The bundled example is `src/langpipe/packs/demo-spanish.json`. Vocabulary entries have `l1`, `l2`, `stage`, optional `pos`, `tags`, and optional `example` / `example_translation`. Grammar entries have `name`, `stage`, `explanation`, and `examples` (prompt/answer pairs).

`generate --stage N --seed S` emits, per vocabulary item: a recognition card (L1 -> L2), a production card (L2 -> L1), and a reading card when the item carries an example sentence. Each grammar example becomes a grammar card. New cards are created due immediately (`due = utcnow()`).

`meta` fields: `language_code`, `language_name`, `script`, `tokenizer`, `rtl`, `note`. A Chinese pack sets `script: han`, `tokenizer: char`; an Arabic pack sets `script: arab`, `tokenizer: word`, `rtl: true`. Configuration is carried to the `Language` record and shown by `init`; it does not change generation or scheduling.

## CLI reference

`langpipe` is a typer app ([src/langpipe/cli.py](src/langpipe/cli.py)). All commands accept `--db <path>` (default `langpipe.db` in the working directory).

| Command | Options | What it does |
|---|---|---|
| `init` | `--name` (default `Learner`), `--lang` (`es`), `--pack` (bundled demo), `--seed` (42), `--daily` (10), `--db` | Deletes the database file if present, then creates learner, deck, curriculum stages, one note per pack entry, and learner state. Stores `pack_path`, `pack_name`, `seed` in meta. |
| `plan` | `--db` | Prints the curriculum with per-stage targets and descriptions. |
| `generate` | `--stage` (1), `--seed` (42), `--count` (0 = all), `--pack` (override), `--db` | Loads the pack, expands stage vocabulary and grammar into cards, links each card to the note by content key, and prints them. |
| `cards` | `--stage` (0 = all), `--db` | Lists cards with id, template, due date, and interval. |
| `review` | `--grade` (required 0-5), `--db` | Applies SM-2 to one card, updates it, appends a `ReviewEvent`, prints interval/ease transition. |
| `stats` | `--db` | Prints the analytics report. |
| `sync` | `--deck` (`langpipe`), `--stage` (0 = all), `--mock`, `--url` (`http://127.0.0.1:8765`), `--db` | Exports cards through a pluggable backend; see next section. |

Commands other than `init` exit with code 1 and a stderr message when the database has no learner yet (`langpipe init` first). `sync` exits non-zero when AnkiConnect is unreachable instead of silently pretending.

## Analytics

`compute_report` ([src/langpipe/analytics.py](src/langpipe/analytics.py)) reads the database and produces the rendered report printed by `stats`:

- **Retention rate** — passes divided by total reviews.
- **Lapse rate** — grades below 3 divided by total reviews.
- **Review load forecast** — cards overdue now, due within 7 days, due within 30 days, total cards.
- **Per-stage progress** — distinct studied vocabulary and grammar per stage against the stage targets.

All figures are derived from the actual `review_events` log and current card schedule, not recomputed from summaries.

## Sync and idempotency

`sync` exports cards to a pluggable backend. The backend protocol (`AnkiBackend`) is `is_available()` plus `sync(notes, deck) -> SyncResult`, with two implementations ([src/langpipe/anki.py](src/langpipe/anki.py)):

- `MockAnkiBackend` — an in-memory fake for tests and demonstration. Reports reachable, dedupes on `(front, back)`, returns assigned note ids.
- `AnkiConnectBackend` — a real HTTP client for Anki's AnkiConnect add-on (default `http://127.0.0.1:8765`). On unreachable server, `SyncResult.reachable = False` with an error, and the CLI reports the failure and exits non-zero loudly.

Idempotency across runs: sync is idempotent since the content-key dedupe fix. A note's identity is the SHA-256 hash of `"front\x1fback"`. The CLI keeps the set of already-synced identities per `(deck, stage)` in the database (`synced_notes:<deck>:<stage>` meta), filters out cards whose content key is already there before the round-trip, sends only the rest, and records the content keys the backend accepted. The real AnkiConnect client additionally asks Anki which notes are duplicates via `canAddNotes` and submits only the ones that can be added.

Running the same sync twice adds all notes the first time and zero the second. The duplicate key is note content only: two cards differing in template or tags but sharing the same front and back count as one note — the same note Anki itself would refuse to duplicate.

Each synced card carries tags `[template, stage-<n>]`.

## Determinism claim

Two independent sources of output are both deterministic:

1. **Card generation** — seeded (`--seed`, default 42) and rule-based. Same pack, same stage, same seed produce identical cards every run; no randomness beyond the seed, no model inference.
2. **Scheduling** — pure arithmetic on card state and the grade sequence. Same grades over the same sequence produce the same intervals, ease factors, and due dates (given the same review timestamps, which are injectable for tests).

What is intentionally non-deterministic is only the wall-clock `utcnow()` used for `due` dates at real review time, which is data, not algorithm.
