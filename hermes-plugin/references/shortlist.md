# Learner shortlist (until `lesan_pipe sources` ships)

The skill specifies a shortlist helper (`lesan_pipe sources`) that is
not yet in the CLI. Until it ships, keep the shortlist in these
notes — one section per learner — and never pretend the command ran.

## Template (copy per learner)

```markdown
## <name> — <language> — <preset> — <date>

Framework + version: (e.g. HSK 2.0 Level 2; CEFR B1 Companion 2020)
Frequency list + version: (see frequency.md)
Grammar reference + edition/chapters: (see grammar.md)

| # | Resource | Link | Licence | Why this learner/stage | Status |
|---|----------|------|---------|------------------------|--------|
| 1 | ... | ... | ... | ... | verified / UNVERIFIED |
```

## Rules (from the skill)

- Each entry carries a link, a licence note, and why it fits this
  learner's preset and stage. Anything unverifiable is labelled
  `UNVERIFIED`.
- Nothing is downloaded silently: propose, then confirm; catalogued
  URLs are fetched on command.
- Licence is checked before inclusion. Copyrighted textbooks are
  cited as references for the learner's own copies, never
  redistributed. If a licence cannot be determined, drop the source
  and say so.
- Prefer: official syllabi and word lists (HSK, JLPT, CEFR, DELE —
  see `frameworks.md`), public-domain or freely-licensed readers
  and textbooks, published frequency lists, subtitle/transcript
  sources, free graded-reading sites (see `acquisition.md`,
  `frequency.md`).
- The repo ships the mechanism, not the content; the learner's
  library stays local.
