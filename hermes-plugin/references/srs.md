# Spaced repetition (SRS-first and Maintenance presets)

Basis for the SRS-first preset (recognition + production cards, high
review load, 6-12 month horizon) and the Maintenance preset
(review-only, no new cards).

## SM-2

- Wozniak, P. (1990). *Optimization of learning*. Master's thesis,
  University of Technology in Poznan. The SM-2 algorithm: quality grades
  0-5 drive easiness-factor updates and inter-repetition intervals.
- Wozniak, P. & Gorzelanczyk, E. (1994). *Optimization of repetition
  spacing in the practice of learning*. Acta Neurobiologiae
  Experimentalis 54: 59-62. Empirical basis for the spacing schedule.
- Algorithm summary as published by SuperMemo
  (supermemo.com — search "SM-2 algorithm"; verify the exact page before
  linking to a learner, `UNVERIFIED` until checked).
- lesan_pipe implements SM-2 in `src/lesan_pipe/scheduler.py`; the code owns
  every interval number. Never recompute SRS arithmetic by hand.

## Anki defaults

- Anki Manual, Deck Options: https://docs.ankiweb.net/deck-options.html
  — the defaults the SRS-first preset refers to (learning steps,
  graduating interval, easy bonus, lapse handling). Anki's defaults
  change across versions: record the Anki version alongside any preset
  that cites them.
- Anki FAQ: https://faqs.ankiweb.net/ — user-level grounding for
  learners who already use Anki (e.g. why reviews pile up, what
  "leech" means).

## Retention research (Maintenance preset)

- The maintenance claim is only that spaced review preserves recall
  better than massed review or no review — see the SM-2 literature
  above and the testing-effect literature (e.g. Roediger & Karpicke,
  2006, *Test-enhanced learning*, Psychological Science 17(4)).
  Preset review loads are operational choices, not research constants:
  derive them from the learner's review tolerance and the CLI's
  retention/lapse stats, and say so.
