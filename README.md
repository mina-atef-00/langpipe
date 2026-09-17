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
  57 notes added.
  note ids: [1, 2, 3, ... 57]
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
