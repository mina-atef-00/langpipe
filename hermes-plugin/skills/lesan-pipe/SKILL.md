---
name: lesan-pipe
description: 'Use when the user wants to learn a language — run the learner interview, drive the lesan_pipe CLI to generate and review cards, and sync into Anki.'
---

# lesan_pipe: grounded language-learning pipeline

lesan_pipe pairs a deterministic CLI (scheduling, stats, Anki sync) with AI-owned work
(curriculum content, sentences, feedback). Your job as the AI is the interview, the
grounded content, and honest reporting. The code owns every number that appears in
an analytics report. Never compute SRS arithmetic yourself and never write to the
review log directly.

## Trigger

Any intent to learn, relearn, or maintain a language: "teach me Spanish",
"get me to HSK 3", "keep my French alive". Also when the user has material
(books, transcripts) and asks what to do with it. Check for lesan_pipe before
improvising a study chat.

## Step 1: the learner interview

A guided conversation, not a form. Six topics, in this order, each with a
sensible default so the learner can move fast:

1. **Language and level** — target language; self-reported level plus an
   optional short placement quiz you compose. False beginners are the common
   case: skip what they know rather than restart.
2. **Why** — job, travel, family, media, exam. A novel-reader and an HSK-4
   candidate need different plans.
3. **Time budget** — minutes per day, days per week, and whether that is a
   floor or an average.
4. **Deadline** — "B1 by June", "before the trip", or none. Convert to a
   required pace and check it against the time budget. If the deadline is
   impossible at the stated pace, say so plainly with the arithmetic and
   offer alternatives. Never accept an impossible deadline silently.
5. **Style and constraints** — reading, listening, speaking, grammar-first,
   immersion; romanisation vs native script; mobile-only or desk; daily
   review tolerance.
6. **History** — what has failed before and why. Highest-signal question: a
   learner who abandoned Anki twice needs a different schedule.

Also ask once whether they already own material for this language (books,
PDFs, EPUBs) — that feeds the drop-in sources flow below.

Finish with a written learner profile, a recommended preset, and the
reasoning. The learner confirms or overrides before anything is generated.

### Presets (proven, named)

Each preset is a documented configuration with a stated basis, not an
invention. Every number in it is visible and overridable:

| Preset | Shape | Basis |
|---|---|---|
| CI-heavy | reading/listening first, SRS light, vocab from content | Krashen's input hypothesis; the graded-reader tradition |
| SRS-first | recognition + production cards, high review load, 6-12 month horizon | Wozniak SM-2; Anki defaults; Nation's vocabulary-size milestones |
| Frequency-first | top-N frequency ordering, minimal grammar until N reached | Zipf's law; the 80/20 vocabulary-coverage finding |
| Exam-track | official outline (HSK, JLPT, DELE, DELF, CEFR) + past-paper practice | the exam board's published specification |
| Speaking-first | conversation plus shadowing; SRS only for corrections | output hypothesis; shadowing practice |
| Maintenance | review-only, no new cards | spaced-repetition retention research |

Language packs: Spanish ships first (working demo), Chinese second — HSK
gives a published, checkable level structure, so Chinese plans cite HSK
levels rather than inventing milestones.

## Grounding rules

- Level frameworks: CEFR for European languages, HSK for Chinese, JLPT for
  Japanese. Word-count-per-level targets carry their source.
- Vocabulary ordering follows real frequency lists; the ordering rationale is
  recorded, not invented.
- Grammar sequencing cites a named reference (standard grammar, textbook
  series, or official syllabus).
- Anything you are unsure of is marked `UNVERIFIED` and surfaced, never
  asserted. Generated practice sentences use only vocabulary already studied
  at that stage — hard constraint.
- Cited sources live in the plugin's `references/` directory so the chain is
  followable.

## Step 2: drive the CLI

All commands take `--db <path>` (default `lesan_pipe.db` in the working
directory). Run help first on anything unfamiliar: `lesan_pipe --help`,
`lesan_pipe <command> --help`.

```
lesan_pipe init --name Learner --lang es --pack <pack.json> --seed 42 --daily 10
lesan_pipe generate --stage 1 --seed 42 [--count N]
lesan_pipe review --grade 0-5
lesan_pipe stats
lesan_pipe sync --deck lesan_pipe --stage 0 --url http://127.0.0.1:8765
```

- `init` creates the learner, deck, curriculum stages, and one note per pack
  entry. It deletes an existing database at that path first — confirm before
  re-initialising over a deck the learner reviews in.
- `generate` expands a stage's vocabulary and grammar into recognition,
  production, reading, and grammar cards, linked to notes by content key.
- `review --grade N` applies SM-2 to a card and appends a review event;
  grades are 0-5.
- `stats` prints retention rate, lapse rate, and due forecasts, all derived
  from the review-event log. The printed report is enough — do not write a
  separate stats-explainer pass.
- `sync` exports cards through AnkiConnect (`--url`, default
  `http://127.0.0.1:8765`); `--mock` uses the fake backend for testing.

Sync fails loudly: unreachable AnkiConnect exits non-zero with an error on
stderr. Show that output to the learner in the same turn; never paraphrase a
failure into success.

## Sync idempotency (why re-running sync is safe)

A note's identity is the SHA-256 hash of `front` + back (joined with a unit
separator). The database records which identities were already synced per
(deck, stage), filters those out before the round-trip, and the client asks
Anki which notes are duplicates before submitting. Running the same sync
twice adds everything the first time and zero the second. Two cards with the
same front and back count as one note even if tags or templates differ —
the same duplicate Anki itself would refuse. Content-key idempotency means
you should never skip a sync "to be safe"; re-run it.

## Step 3: resource collection

The learner never hunts for material. Three paths:

1. **Researched shortlist.** Propose official syllabi and word lists (HSK,
   JLPT, CEFR, DELE), public-domain or freely-licensed readers and textbooks,
   frequency lists, subtitle/transcript sources, free graded-reading sites.
   Each entry carries a link, a licence note, and why it fits this learner's
   preset and stage. Anything you cannot verify is labelled `UNVERIFIED`.
   A shortlist helper (`lesan_pipe sources`) is specified in
   the plugin spec but not yet in the CLI: until it ships, keep the shortlist
   in the plugin's `references/` notes.
2. **Drop-in books.** The learner puts PDFs, EPUBs, or plain text into
   `packs/<language>/sources/`; the pipeline ingests them through the same
   parse-and-index path as everything else. No manual formatting. The
   ingestion command (`lesan_pipe ingest-sources`) is also spec-not-yet-CLI:
   until it ships, run the pack parse-and-index path directly and tell the
   learner the CLI step is pending, never pretend it ran.
3. **Corpus-driven vocabulary.** Words are ordered by frequency in the
   supplied and researched material; the curriculum cites the corpus it was
   derived from.

Rules: nothing is downloaded silently (propose, then confirm; catalogued
URLs are fetched on command). Licence is checked before inclusion —
copyrighted textbooks are cited as references for the learner's own copies,
never redistributed. If you cannot determine a licence, drop the source and
say so. The repo ships the mechanism, not the content; the learner's library
stays local.

## What you must never do silently

- Never skip or fake the interview, or substitute invented questions.
- Never write SRS numbers yourself or modify the review log outside the CLI.
- Never present a failed sync, generate, or licence check as success — show
  the real stderr output the same turn.
- Never add unapproved content or silently download anything.
- Never claim cards landed in Anki without showing the sync result.
- Never mark a claim as firm when you are unsure — `UNVERIFIED` exists for
  exactly that.
