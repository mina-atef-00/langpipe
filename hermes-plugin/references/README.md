# references/ — grounding citations for the lesan_pipe skill

The skill (`skills/lesan_pipe/SKILL.md`) promises that cited sources live in
the plugin's `references/` directory so the chain is followable. This
directory is that path. It holds citations and lookup notes, not
redistributed content: check each licence before downloading anything,
and keep the learner's library local.

## Index

| File | Covers the skill's claim that ... |
|---|---|
| `srs.md` | presets use Wozniak SM-2, Anki defaults, spaced-repetition retention research |
| `acquisition.md` | presets rest on Krashen's input hypothesis, the output hypothesis, the graded-reader tradition, shadowing practice |
| `frequency.md` | frequency-first rests on Zipf's law and the vocabulary-coverage finding; ordering follows real frequency lists |
| `frameworks.md` | levels are CEFR / HSK / JLPT (+ DELE, DELF); exam-track follows the board's published specification |
| `grammar.md` | grammar sequencing cites a named reference (standard grammar, textbook series, or official syllabus) |
| `shortlist.md` | per-learner resource shortlist template, until `lesan_pipe sources` ships in the CLI |

## Conventions

- Every entry gives author / year / title at minimum. URLs are lookup
  aids: verify before downloading, and if a link is dead search the title.
- Anything not personally verified is marked `UNVERIFIED` in the
  learner-facing shortlist — never asserted as firm.
- Word-count-per-level targets always carry their source (usually the
  exam board's specification in `frameworks.md`, or Nation's milestones
  in `frequency.md`). A number without a source is a draft, not a claim.
- Version-pinning: frameworks and specifications change (HSK 2.0 vs 3.0,
  CEFR Companion Volume 2020). Record which version a plan was built
  against in the shortlist entry.
