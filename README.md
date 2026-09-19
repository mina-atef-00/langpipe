# langpipe

langpipe is a command-line tool that turns a list of words and grammar points into a working study plan. You give it a language pack, it generates practice cards, schedules your reviews with spaced repetition, and then tells you the honest numbers: how much you actually retained, how much you forgot, and what is coming due. The point is not another flashcard app. The point is knowing whether the hours you spend are doing anything.

![python](https://img.shields.io/badge/python-3.11%2B-89b4fa?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-a6e3a1?style=flat-square)
[![CI](https://github.com/mina-atef-00/langpipe/actions/workflows/ci.yml/badge.svg)](https://github.com/mina-atef-00/langpipe/actions/workflows/ci.yml)
![langpipe](https://img.shields.io/badge/langpipe-v0.1-cba6f7?style=flat-square)

| In action | What you are looking at |
|---|---|
| ![langpipe as a Hermes plugin](docs/img/plugin-action.svg) | The langpipe skill loaded in Hermes: the learner interview runs, the SRS-first preset is picked, and the four-stage plan is printed. |
| ![generate and review with SM-2](docs/img/cards-review.svg) | `generate` builds 57 practice cards; repeated `review` runs grow the SM-2 interval from 0d to 130d with a rising ease factor. |
| ![idempotent sync and stats](docs/img/stats-sync.svg) | `sync` pushes 56 notes; a re-run adds 0 — sync is idempotent. `stats` reports retention and the review load forecast. |

## Hermes plugin

langpipe is also a Hermes plugin. The bundled skill runs a guided learner
interview (language, motivation, time budget, deadline, style, history),
matches the answers to a proven preset, then drives the langpipe CLI to
produce the plan, generate practice cards, record reviews, and report
retention analytics:

interview -> plan -> generate -> review -> sync

Install from the local plugin directory:

```bash
cp -r ~/.hermes/plugins/langpipe ~/.hermes/skills/langpipe
```

The skill is a prompt file, not code: it is not part of this repository (it
lives in the Hermes plugin directory, `~/.hermes/plugins/langpipe/SKILL.md`),
and it adds no model inference to the pipeline. Everything it does, it does by
calling the CLI documented below.

See SPEC.md for the technical detail on how the skill and the CLI divide the
work.

## Sixty seconds

Start a learner and load the bundled demo Spanish pack:

```bash
langpipe init --name Mina --lang es --seed 42
```

![langpipe init](docs/img/demo-init.svg)

Generate the practice cards for stage 1:

```bash
langpipe generate --stage 1 --seed 42
```

![langpipe generate](docs/img/demo-generate.svg)

Study a few cards, then record what happened. Grade 3 or above is a pass, below 3 means you forgot it:

```bash
langpipe review 2 --grade 4
```

![langpipe review](docs/img/demo-review.svg)

After a session, see how you are doing:

```bash
langpipe stats
```

![langpipe stats](docs/img/demo-stats.svg)

That is the whole loop. Init once, generate, review as you study, check stats whenever you want to know if it is working.

## Install

You need Python 3.11 or newer.

```bash
git clone <this repo>
cd langpipe
python -m venv .venv
.venv/bin/pip install -e .
```

## Daily use

- `langpipe init` — start a learner and load a language pack (once).
- `langpipe plan` — look at the four-stage curriculum and its targets.
- `langpipe generate` — create the practice cards for a stage.
- `langpipe cards` — list your cards and what is due.
- `langpipe review <card-id> --grade 0-5` — record one review after studying that card.
- `langpipe stats` — retention, lapse rate, upcoming workload, progress per stage.
- `langpipe sync` — push your cards into Anki, if you use both.

It works for any language. The code never branches on which language you are learning; a Spanish pack, an Arabic pack, and a Chinese pack are just different data files. The bundled demo pack is a starter — add your own vocabulary to make it yours.

Want the internal details — how the scheduling math works, what is stored where, how sync stays idempotent? Read [SPEC.md](SPEC.md).

## Status

New tool, early days. The pipeline runs end to end and the test suite is green, but treat it as a project to poke at, not polished software.

What "green" means concretely, so it can be checked rather than believed:
`pytest` runs 56 tests, `ruff check .` is clean, and `mypy` in strict mode
reports no issues; CI (`.github/workflows/ci.yml`) runs those same three on
Python 3.11 for every push.

## License

MIT. See the LICENSE file.
