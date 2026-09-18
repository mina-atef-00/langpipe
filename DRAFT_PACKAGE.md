# langpipe: draft package review

This is a draft for the owner to review before anything is published. Nothing has been pushed. There is no git remote. The repo lives only at `/home/mina/Programming/portfolio/langpipe`.

## File tree

```
langpipe/
├── .github/
│   └── workflows/
│       └── ci.yml                    # ruff + mypy + pytest on push/PR
├── .gitignore
├── LICENSE                           # MIT
├── README.md
├── pyproject.toml                    # pinned deps, ruff + mypy config
├── src/
│   └── langpipe/
│       ├── __init__.py
│       ├── analytics.py              # retention, lapse, forecast, progress
│       ├── anki.py                   # AnkiConnect client + mock backend
│       ├── cli.py                    # typer CLI
│       ├── curriculum.py             # staged plan + progress computation
│       ├── db.py                     # SQLite persistence
│       ├── generator.py              # deterministic seeded generator
│       ├── models.py                 # Pydantic data model
│       ├── scheduler.py              # SM-2
│       └── packs/
│           └── demo-spanish.json     # bundled example language pack
└── tests/
    ├── conftest.py
    ├── test_analytics.py
    ├── test_anki.py
    ├── test_cli.py
    ├── test_generator.py
    ├── test_models.py
    └── test_scheduler.py
```

## The README

Reproduced in full, as it sits in the repo.

```markdown
# langpipe

A language-agnostic learning pipeline. It turns a phased curriculum and a small vocabulary file into graded practice, schedules reviews, and tells you whether your retention is actually improving.

## The problem

Self-study language learning has a measurement gap. Learners pick a goal (say, reach B1 in six months), grind flashcards, and have no way to check whether the hours are doing anything. Retention is the number that matters, and most setups never compute it. A pile of cards is not a curriculum, and a calendar is not progress.

langpipe closes that loop. It models a phased curriculum with explicit vocabulary and grammar targets, generates graded practice from a vocabulary file, schedules reviews with spaced repetition, and computes retention, lapse rate, review load, and per-stage progress from the actual review log. English, Arabic, Chinese, and anything else are all just data. Nothing in the code branches on a language.

## What it does

- A Pydantic data model for languages, decks, notes, cards, curriculum stages, review events, and learner state, persisted in SQLite.
- A phased curriculum (bridge, input, expansion, fluency) with per-stage vocabulary and grammar targets.
- A deterministic, seeded, rule-based generator that turns a language pack into practice cards. Same seed, same output. No language model involved.
- A spaced-repetition scheduler (SuperMemo SM-2) that records every review.
- Analytics computed from the review log: retention rate, lapse rate, review load for the next 7 and 30 days, and per-stage progress.
- An Anki bridge over AnkiConnect with a pluggable backend: an in-memory mock for tests and a real HTTP client for a running Anki. If Anki is not reachable, the sync command fails loudly.
- A typer CLI: `init`, `plan`, `generate`, `cards`, `review`, `stats`, `sync`.

## Install

Requires Python 3.11 or newer.

```
git clone <this repo>
cd langpipe
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/langpipe --help
```

The `dev` extra installs pytest, ruff, and mypy. The runtime dependencies are just typer and pydantic.

## Quick start

A worked example, from a fresh database to a stats report.

```
$ langpipe init --name Mina --lang es --seed 42
Initialised learner 'Mina' learning Spanish (es).
Loaded pack 'demo-spanish': 56 vocabulary items, 8 grammar points.
Script: latin, tokenizer: word, rtl: False
Seed: 42. Next: `langpipe plan` to see the plan, then `langpipe generate`.
```

`init` creates a fresh SQLite database, loads the bundled demo language pack as notes, and writes the curriculum and learner state.

```
$ langpipe plan
Curriculum plan
  stage 1 (bridge): 300 vocab, 20 grammar
      Vocabulary front-load. Nothing is comprehensible yet, so the schedule is SRS-heavy. Custom texts use only words already studied.
  stage 2 (input): 800 vocab, 40 grammar
      Graded readers and slow audio become usable. Sentence mining starts.
  stage 3 (expansion): 1500 vocab, 60 grammar
      Native-adjacent content opens up. Production (writing, speaking) begins.
  stage 4 (fluency): 2500 vocab, 80 grammar
      Review-only SRS; most time on native content and production.
```

`generate` expands the stage-1 vocabulary and grammar into cards. Each vocabulary item yields a recognition card (English to Spanish), a production card (Spanish to English), and a reading card when the pack carries an example sentence.

```
$ langpipe generate --stage 1 --seed 42
Generated 57 cards for stage 1 (seed 42).
  [1] production   'pequeño' -> 'small'
  [2] recognition  'hello' -> 'hola'
  [3] recognition  'you' -> 'tú'
  [4] production   'gato' -> 'cat'
  [5] reading      'El perro es grande.' -> 'The dog is big.'
  [6] production   'adiós' -> 'goodbye'
  [8] grammar      'Complete: Yo ___ estudiante.' -> 'soy'
  ...
```

`review` records a graded review and reschedules the card. A grade of 3 or above is a pass, below 3 is a lapse.

```
$ langpipe review 2 --grade 4
Card 2 graded 4: interval 0d -> 1d, ease 2.50 -> 2.50, due 2026-09-18 (review #1).
$ langpipe review 3 --grade 1
Card 3 graded 1: interval 0d -> 1d, ease 2.50 -> 2.50, due 2026-09-18 (review #2).
$ langpipe review 4 --grade 5
Card 4 graded 5: interval 0d -> 1d, ease 2.50 -> 2.60, due 2026-09-18 (review #3).
$ langpipe review 8 --grade 3
Card 8 graded 3: interval 0d -> 1d, ease 2.50 -> 2.36, due 2026-09-18 (review #4).
```

`stats` prints the report. Retention and lapse come from the four reviews above; the forecast comes from the card schedule.

```
$ langpipe stats
Retention
  retention rate:  75.0%
  lapse rate:      25.0%
  passed/lapsed:   3/1 of 4 reviews
Review load forecast
  overdue now:          53
  due in next 7 days:   4
  due in next 30 days:  4
  cards total:          57
Per-stage progress
  stage 1 (bridge): vocab 2/300 (0.7%), grammar 1/20 (5.0%)
  stage 2 (input): vocab 0/800 (0.0%), grammar 0/40 (0.0%)
  stage 3 (expansion): vocab 0/1500 (0.0%), grammar 0/60 (0.0%)
  stage 4 (fluency): vocab 0/2500 (0.0%), grammar 0/80 (0.0%)
```

`sync` pushes cards to Anki. Without a running Anki, use the in-memory backend:

```
$ langpipe sync --mock --stage 1
Sync to backend 'mock' (deck 'langpipe'):
  56 notes added.
  note ids: [1, 2, 3, 4, ... 56]
```

With a real Anki running the AnkiConnect add-on, drop `--mock`. If the server is not reachable, the command reports the failure and exits with a non-zero code instead of pretending.

## Language packs

A language pack is a JSON file with three sections: `meta`, `vocabulary`, and `grammar`. The bundled `src/langpipe/packs/demo-spanish.json` is a working example with 56 vocabulary items and 8 grammar points spread over the four stages.

```json
{
  "meta": {
    "name": "demo-spanish",
    "language_code": "es",
    "language_name": "Spanish",
    "script": "latin",
    "tokenizer": "word",
    "rtl": false,
    "note": "human-readable note about the language"
  },
  "vocabulary": [
    {"l1": "hello", "l2": "hola", "stage": 1, "pos": "greeting", "tags": ["core"]},
    {"l1": "dog", "l2": "perro", "stage": 1, "pos": "noun",
     "example": "El perro es grande.", "example_translation": "The dog is big."}
  ],
  "grammar": [
    {
      "name": "ser (permanent to be)",
      "stage": 1,
      "explanation": "Ser describes permanent qualities and identity.",
      "examples": [
        {"prompt": "Complete: Yo ___ estudiante.", "answer": "soy"}
      ]
    }
  ]
}
```

Fields:

- `l1` is the language the learner already knows, `l2` the target language.
- `stage` is the curriculum stage (1 to 4).
- `example` and `example_translation` are optional. When present, the generator emits a reading card.
- Grammar examples are prompt/answer pairs. Each one becomes a card.

The `meta` block is where language-specific behaviour lives. The generator never branches on a language code. A Chinese pack would set `script` to `han` and `tokenizer` to `char`. An Arabic pack would set `script` to `arab`, `tokenizer` to `word`, and `rtl` to `true`. That configuration is carried through to the `Language` record and shown by `init`. It does not change how generation or scheduling works.

## The scheduling algorithm

langpipe implements SuperMemo SM-2, the classic spaced-repetition algorithm. The original description is Piotr Wozniak's SuperMemo algorithm write-up (the SM-2 section), and Anki's default schedule is a modified SM-2, so the behaviour will be familiar to Anki users.

Rules:

- A review is graded 0 to 5, where 0 is complete blackout and 5 is perfect recall.
- Below 3 is a lapse: repetitions reset to 0 and the card is due again in one day.
- A pass sets the interval: 1 day on the first pass, 6 days on the second, and `round(previous interval * ease factor)` after that.
- The ease factor starts at 2.5 and updates after every review using Wozniak's formula:

```
EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
```

- The ease factor is floored at 1.3 so a struggling card can still recover.

Every review is written to the `review_events` table with the interval and ease before and after, so the analytics never recompute history from a summary; they read the log.

## Status

This is a new tool, not a mature project. The pipeline runs end to end, the test suite passes, and lint and type checks are clean. The demo pack is a starter: its targets (300 to 2500 words) far exceed the 56 bundled items, so progress percentages start small on purpose. Add your own pack to make it useful.

## License

MIT. See the LICENSE file.
```

## Verbatim evidence

Every claim below is backed by real command output captured from a clean run.

### init

```
$ langpipe init --name Mina --lang es --seed 42
Initialised learner 'Mina' learning Spanish (es).
Loaded pack 'demo-spanish': 56 vocabulary items, 8 grammar points.
Script: latin, tokenizer: word, rtl: False
Seed: 42. Next: `langpipe plan` to see the plan, then `langpipe generate`.
```

### plan

```
$ langpipe plan
Curriculum plan
  stage 1 (bridge): 300 vocab, 20 grammar
      Vocabulary front-load. Nothing is comprehensible yet, so the schedule is SRS-heavy. Custom texts use only words already studied.
  stage 2 (input): 800 vocab, 40 grammar
      Graded readers and slow audio become usable. Sentence mining starts.
  stage 3 (expansion): 1500 vocab, 60 grammar
      Native-adjacent content opens up. Production (writing, speaking) begins.
  stage 4 (fluency): 2500 vocab, 80 grammar
      Review-only SRS; most time on native content and production.
```

### generate (full output, 57 cards)

```
$ langpipe generate --stage 1 --seed 42
Generated 57 cards for stage 1 (seed 42).
  [1] production   'pequeño' -> 'small'
  [2] recognition  'hello' -> 'hola'
  [3] recognition  'you' -> 'tú'
  [4] production   'gato' -> 'cat'
  [5] reading      'El perro es grande.' -> 'The dog is big.'
  [6] production   'adiós' -> 'goodbye'
  [7] production   'tú' -> 'you'
  [8] grammar      'Complete: Yo ___ estudiante.' -> 'soy'
  [9] recognition  'she' -> 'ella'
  [10] recognition  'goodbye' -> 'adiós'
  [11] production   'pan' -> 'bread'
  [12] production   'comer' -> 'to eat'
  [13] recognition  'red' -> 'rojo'
  [14] recognition  'small' -> 'pequeño'
  [15] production   'por favor' -> 'please'
  [16] production   'gracias' -> 'thank you'
  [17] production   'grande' -> 'big'
  [18] recognition  'he' -> 'él'
  [19] production   'agua' -> 'water'
  [20] recognition  'blue' -> 'azul'
  [21] recognition  'please' -> 'por favor'
  [22] recognition  'cat' -> 'gato'
  [23] recognition  'table' -> 'mesa'
  [24] production   'él' -> 'he'
  [25] production   'mesa' -> 'table'
  [26] production   'hola' -> 'hello'
  [27] recognition  'I' -> 'yo'
  [28] recognition  'to drink' -> 'beber'
  [29] recognition  'house' -> 'casa'
  [30] recognition  'yes' -> 'sí'
  [31] production   'bueno' -> 'good'
  [32] production   'no' -> 'no'
  [33] reading      'Yo como pan.' -> 'I eat bread.'
  [34] production   'casa' -> 'house'
  [35] recognition  'day' -> 'día'
  [36] grammar      'Complete: Él ___ alto.' -> 'es'
  [37] production   'rojo' -> 'red'
  [38] production   'sí' -> 'yes'
  [39] production   'día' -> 'day'
  [40] recognition  'to eat' -> 'comer'
  [41] grammar      'Complete: el libro ___ (red)' -> 'rojo'
  [42] recognition  'big' -> 'grande'
  [43] recognition  'no' -> 'no'
  [44] reading      'La casa es pequeña.' -> 'The house is small.'
  [45] production   'azul' -> 'blue'
  [46] production   'ella' -> 'she'
  [47] production   'beber' -> 'to drink'
  [48] recognition  'book' -> 'libro'
  [49] grammar      'Complete: la casa ___ (small)' -> 'pequeña'
  [50] recognition  'bread' -> 'pan'
  [51] recognition  'dog' -> 'perro'
  [52] production   'perro' -> 'dog'
  [53] recognition  'good' -> 'bueno'
  [54] recognition  'water' -> 'agua'
  [55] production   'yo' -> 'I'
  [56] production   'libro' -> 'book'
  [57] recognition  'thank you' -> 'gracias'
```

### review (four graded reviews)

```
$ langpipe review 2 --grade 4
Card 2 graded 4: interval 0d -> 1d, ease 2.50 -> 2.50, due 2026-09-18 (review #1).
$ langpipe review 3 --grade 1
Card 3 graded 1: interval 0d -> 1d, ease 2.50 -> 2.50, due 2026-09-18 (review #2).
$ langpipe review 4 --grade 5
Card 4 graded 5: interval 0d -> 1d, ease 2.50 -> 2.60, due 2026-09-18 (review #3).
$ langpipe review 8 --grade 3
Card 8 graded 3: interval 0d -> 1d, ease 2.50 -> 2.36, due 2026-09-18 (review #4).
```

### stats

```
$ langpipe stats
Retention
  retention rate:  75.0%
  lapse rate:      25.0%
  passed/lapsed:   3/1 of 4 reviews
Review load forecast
  overdue now:          53
  due in next 7 days:   4
  due in next 30 days:  4
  cards total:          57
Per-stage progress
  stage 1 (bridge): vocab 2/300 (0.7%), grammar 1/20 (5.0%)
  stage 2 (input): vocab 0/800 (0.0%), grammar 0/40 (0.0%)
  stage 3 (expansion): vocab 0/1500 (0.0%), grammar 0/60 (0.0%)
  stage 4 (fluency): vocab 0/2500 (0.0%), grammar 0/80 (0.0%)
```

### sync (mock backend)

```
$ langpipe sync --mock --stage 1
Sync to backend 'mock' (deck 'langpipe'):
  56 notes added.
  note ids: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56]
```

### sync is idempotent (running it again)

```
$ langpipe sync --mock --stage 1
Sync to backend 'mock' (deck 'langpipe'):
  0 notes added.
  note ids: []
```

### sync with no Anki running (failure detected, non-zero exit)

```
$ langpipe sync --url http://127.0.0.1:1
Sync failed: AnkiConnect not reachable at http://127.0.0.1:1
AnkiConnect was not reachable. Start Anki with the AnkiConnect add-on, or use `--mock` to run against the in-memory backend.
```

The command exits with code 1.

### determinism (fresh database, same seed, identical plan)

```
$ langpipe init --db /tmp/lp1.db --seed 42
$ langpipe generate --db /tmp/lp1.db --stage 1 --seed 42 > /tmp/det1.txt
$ langpipe init --db /tmp/lp2.db --seed 42
$ langpipe generate --db /tmp/lp2.db --stage 1 --seed 42 > /tmp/det2.txt
$ diff /tmp/det1.txt /tmp/det2.txt
RESULT: identical plans
```

A different seed produces a different (but same-multiset) ordering, verified by test.

### quality gates

```
$ ruff check .
All checks passed!

$ mypy
Success: no issues found in 9 source files

$ pytest
41 passed in 0.16s
```

41 tests across six files: data model (7), generator (8), scheduler (9), analytics (5), Anki bridge (4), CLI (9).

## What is verified working

- Data model round-trips through JSON and SQLite; Pydantic v2, strict mypy clean.
- Curriculum plan with four stages and per-stage targets; progress computed from the review log.
- Deterministic seeded generator; two fresh databases with the same seed produce byte-identical plans.
- SM-2 scheduler verified against hand-computed intervals (1, 6, 15) and ease updates (2.6 for grade 5, 2.36 for grade 3).
- Analytics verified against a hand-computed fixture (retention 0.75, lapse 0.25, forecast 1/2, progress 2 vocab / 1 grammar).
- Mock Anki backend stores and returns notes; real backend reports unreachable cleanly.
- CLI commands all run and print the output shown above.
- ruff, mypy, and pytest all clean.

## What is not yet done

- The Anki bridge is one-way: it exports langpipe notes to Anki but does not read Anki review history back. Retention analytics use langpipe's own log, not Anki's.
- The real AnkiConnect backend is only exercised on the unreachable path in tests. There is no live Anki in CI, so the happy path against a running Anki is untested here.
- The generator does not create new sentences. Reading cards come from example sentences that a pack author writes by hand.
- The demo pack is a starter (56 words) against targets of 300 to 2500. It demonstrates the mechanism, not a complete course.
- Retention is a single aggregate number. There is no split by card age (young vs mature), and no per-day learning curve yet.
- The review-load forecast counts already-scheduled cards only; it does not model future new-card introductions at the daily-new-cards rate.

## Proposed GitHub description

"langpipe is a language-agnostic learning pipeline. Model a phased curriculum, generate graded practice from a vocabulary file, schedule reviews with SM-2 spaced repetition, and measure retention from the review log. Works with a real Anki via AnkiConnect or an in-memory backend. No language model involved; same seed gives the same plan."

Proposed topics: `language-learning`, `spaced-repetition`, `srs`, `anki`, `ankiconnect`, `python`, `cli`, `education`, `retention`, `sqlite`, `pydantic`, `typer`.

## What a skeptical reviewer would attack

The honest weak points, not dressed up.

1. The methodology predates the tool. The phased-curriculum, graded-input, spaced-repetition, retention-measurement approach already exists as written documentation and as a third-party flashcard deck. This repository is the first implementation of it as a runnable program. It is a new tool. There is no prior user history, no cohort data, and no evidence from actual study sessions, because none exists yet. The README says this, but a reviewer who wants numbers will find none.

2. The demo pack is a toy. Fifty-six words against a 300-to-2500-word plan means the progress bars start at 0.0%. A reviewer will correctly note that the tool has never been used to take anyone from zero to any proficiency level.

3. Generation is not generation in the LLM sense. The "reading" cards are hand-written example sentences in the pack file. The generator expands and orders them deterministically; it does not compose new graded text. Anyone expecting auto-generated comprehensible input will be disappointed.

4. Retention is self-reported. A learner grades their own recall 0 to 5. There is no objective check, and a learner can game the numbers by marking everything perfect. This is a real limitation of the measurement, not just of the code.

5. The Anki integration is thin. It exports notes and detects when Anki is absent. It does not import review history, synchronize two ways, or reconcile schedules. A reviewer looking for a serious Anki workflow will see a one-way pipe. Sync itself is idempotent: a note's identity is its content, so re-running the same sync adds zero notes (the mock keys on (front, back), the real backend uses AnkiConnect's `canAddNotes`, and the CLI filters already-accepted notes from its database).

6. The SM-2 implementation is textbook. That is a feature for clarity, but a reviewer comparing it to Anki's tuned scheduler (fuzz factors, graduating/easy intervals, per-deck options) will find it basic.

7. Test coverage is honest but not exhaustive. The hand-computed fixtures pin the arithmetic, and determinism is proven, but there are no property tests over long review sequences and no test against a live AnkiConnect server.

None of these are hidden. The README's status section and this document state the maturity plainly. The claim the project makes is narrow: the pipeline runs, the maths is correct against fixtures, and generation is reproducible. That claim is backed by the evidence above.
