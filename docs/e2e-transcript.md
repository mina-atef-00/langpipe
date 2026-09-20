# Lesan Pipe end-to-end acceptance transcript

Run at 2026-09-20 16:28 UTC; checkout `/var/home/mina/Programming/portfolio/langpipe/.worktrees/t_9cf15a86` at commit `f42b165`; harness Python 3.14.7. Every step below ran for real in order; a step that failed would abort the run and this transcript would end there. (`mock` sync exercises the tool plumbing hermetically; the Anki sync in step 9 speaks real AnkiConnect HTTP to a local test double, because CI has no Anki installed.)


## PASS: fresh install from a clean state

Created an empty venv, ran `pip install /var/home/mina/Programming/portfolio/langpipe/.worktrees/t_9cf15a86` (non-editable: this builds the wheel, so broken packaging fails here), and the fresh `lesan_pipe --help` exits 0. Console script: `/var/home/mina/.hermes/cache/scratch/lesan_e2e_b4tb5v7c/install-venv/bin/lesan_pipe`.

## PASS: MCP server handshake and tool catalogue

`initialize` reports `{'name': 'lesan_pipe', 'version': '0.1.0'}`; `tools/list` returns exactly the seven tools: lesan_pipe_init, lesan_pipe_plan, lesan_pipe_generate, lesan_pipe_cards, lesan_pipe_review, lesan_pipe_stats, lesan_pipe_sync.

## PASS: tool 1/7: init creates the learner in a temporary database

`lesan_pipe_init` ok.

```
Initialised learner 'E2E' learning Spanish (es).
Loaded pack 'demo-spanish': 56 vocabulary items, 8 grammar points.
Script: latin, tokenizer: word, rtl: False
Seed: 42. Next: `lesan_pipe plan` to see the plan, then `lesan_pipe generate`.
```

## PASS: tool 2/7: plan prints the curriculum

`lesan_pipe_plan` ok.

```
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

## PASS: tool 3/7: generate builds the stage-1 cards

`lesan_pipe_generate` ok.

```
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
... (18 more lines)
```

## PASS: tool 4/7: cards lists stored cards

`lesan_pipe_cards` ok.

```
[1] stage 1 production   due 2026-09-20 interval 0d 'pequeño'
  [2] stage 1 recognition  due 2026-09-20 interval 0d 'hello'
  [3] stage 1 recognition  due 2026-09-20 interval 0d 'you'
  [4] stage 1 production   due 2026-09-20 interval 0d 'gato'
  [5] stage 1 reading      due 2026-09-20 interval 0d 'El perro es grande.'
  [6] stage 1 production   due 2026-09-20 interval 0d 'adiós'
  [7] stage 1 production   due 2026-09-20 interval 0d 'tú'
  [8] stage 1 grammar      due 2026-09-20 interval 0d 'Complete: Yo ___ estudiante.'
  [9] stage 1 recognition  due 2026-09-20 interval 0d 'she'
  [10] stage 1 recognition  due 2026-09-20 interval 0d 'goodbye'
  [11] stage 1 production   due 2026-09-20 interval 0d 'pan'
  [12] stage 1 production   due 2026-09-20 interval 0d 'comer'
  [13] stage 1 recognition  due 2026-09-20 interval 0d 'red'
  [14] stage 1 recognition  due 2026-09-20 interval 0d 'small'
  [15] stage 1 production   due 2026-09-20 interval 0d 'por favor'
  [16] stage 1 production   due 2026-09-20 interval 0d 'gracias'
  [17] stage 1 production   due 2026-09-20 interval 0d 'grande'
  [18] stage 1 recognition  due 2026-09-20 interval 0d 'he'
  [19] stage 1 production   due 2026-09-20 interval 0d 'agua'
  [20] stage 1 recognition  due 2026-09-20 interval 0d 'blue'
  [21] stage 1 recognition  due 2026-09-20 interval 0d 'please'
  [22] stage 1 recognition  due 2026-09-20 interval 0d 'cat'
  [23] stage 1 recognition  due 2026-09-20 interval 0d 'table'
  [24] stage 1 production   due 2026-09-20 interval 0d 'él'
  [25] stage 1 production   due 2026-09-20 interval 0d 'mesa'
  [26] stage 1 production   due 2026-09-20 interval 0d 'hola'
  [27] stage 1 recognition  due 2026-09-20 interval 0d 'I'
  [28] stage 1 recognition  due 2026-09-20 interval 0d 'to drink'
  [29] stage 1 recognition  due 2026-09-20 interval 0d 'house'
  [30] stage 1 recognition  due 2026-09-20 interval 0d 'yes'
  [31] stage 1 production   due 2026-09-20 interval 0d 'bueno'
  [32] stage 1 production   due 2026-09-20 interval 0d 'no'
  [33] stage 1 reading      due 2026-09-20 interval 0d 'Yo como pan.'
  [34] stage 1 production   due 2026-09-20 interval 0d 'casa'
  [35] stage 1 recognition  due 2026-09-20 interval 0d 'day'
  [36] stage 1 grammar      due 2026-09-20 interval 0d 'Complete: Él ___ alto.'
  [37] stage 1 production   due 2026-09-20 interval 0d 'rojo'
  [38] stage 1 production   due 2026-09-20 interval 0d 'sí'
  [39] stage 1 production   due 2026-09-20 interval 0d 'día'
  [40] stage 1 recognition  due 2026-09-20 interval 0d 'to eat'
... (17 more lines)
```

## PASS: tool 5/7: review records a grade-4 SM-2 review

`lesan_pipe_review` ok.

```
Card 1 graded 4: interval 0d -> 1d, ease 2.50 -> 2.50, due 2026-09-21 (review #1).
```

## PASS: tool 6/7: stats reports retention from the review log

`lesan_pipe_stats` ok.

```
Retention
  retention rate:  100.0%
  lapse rate:      0.0%
  passed/lapsed:   1/0 of 1 reviews
Review load forecast
  overdue now:          56
  due in next 7 days:   1
  due in next 30 days:  1
  cards total:          57
Per-stage progress
  stage 1 (bridge): vocab 1/300 (0.3%), grammar 0/20 (0.0%)
  stage 2 (input): vocab 0/800 (0.0%), grammar 0/40 (0.0%)
  stage 3 (expansion): vocab 0/1500 (0.0%), grammar 0/60 (0.0%)
  stage 4 (fluency): vocab 0/2500 (0.0%), grammar 0/80 (0.0%)
```

## PASS: tool 7/7: sync pushes cards through the mock backend

`lesan_pipe_sync` ok.

```
Sync to backend 'mock' (deck 'lesan_pipe'):
  56 notes added.
  note ids: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56]
```

## PASS: real AnkiConnect sync (HTTP, not --mock)

`lesan_pipe_sync` against a live AnkiConnect-shaped HTTP endpoint at `http://127.0.0.1:36161` added 56 notes to deck `lesan_pipe_e2e`; the server confirms 56 notes stored.

```
Sync to backend 'ankiconnect' (deck 'lesan_pipe_e2e'):
  56 notes added.
  note ids: [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155]
```

## PASS: idempotent re-sync adds zero

Re-running the identical sync added 0 notes and the server collection is unchanged at 56: content-keyed duplicate detection holds end to end.

```
Sync to backend 'ankiconnect' (deck 'lesan_pipe_e2e'):
  0 notes added.
  note ids: []
```

_Steps: 11/11 passed._
