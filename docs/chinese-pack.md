# Chinese pack: real-deck coverage vs the Anki-only workflow

The pack `src/lesan_pipe/packs/chinese-hsk1-4.json` is generated from
Mina's real study deck by `scripts/build_chinese_pack.py`:

    python scripts/build_chinese_pack.py [--deck PATH] [--out PATH]

Default deck path: `~/wiki/study/chinese/assets/Chinese_Vocabulary_HSK_1-4.apkg`.

## Source deck (inspected, not assumed)

| Fact | Value |
|---|---|
| File | `Chinese_Vocabulary_HSK_1-4.apkg` (Natural Language Journey, deck ID 1352957654) |
| Notes | 1457 × `Chinese Vocab (HSK)`, 11 fields (Chinese, Image, Pinyin, English, Cloze Sentence, Sentence, Sentence Pinyin, English Sentence, Lesson, Vocab Audio, Sentence Audio) + 1 stray `Basic` note (excluded) |
| Tags | HSK1 × 203, HSK2 × 191, HSK3 × 335, HSK4 × 727, untagged × 1 (死) |
| Lessons | `Lesson 1`–`Lesson 20` only; HSK1/HSK2 notes sit in lessons 1–15, HSK3/HSK4 span 1–20 |
| Card templates | Card 2 = recognition (Chinese → pinyin/English, type-in), Card 3 = cloze/production (English → Chinese) |
| Data gaps in the deck | 城市 has no English sentence; 死 has no tags and no lesson; 755 notes have no image |

Note: the study wiki describes a larger version of this deck (2803
notes, lessons into the hundreds). The file on disk has 1457 notes
across 20 lessons — this pack reflects the disk, and the wiki
discrepancy is flagged, not papered over.

## Deck → pack mapping

| Deck | Pack |
|---|---|
| HSK tag (HSK1..HSK4) | `stage` 1..4; the untagged note → stage 4 + `untagged` tag |
| Lesson field (`Lesson N`) | `lesson-NN` tag (zero-padded, sorts correctly) + file order (stage, lesson, word) |
| English gloss | `l1` (recognition prompt, production answer) |
| Chinese word | `l2` (recognition answer, production prompt) |
| Sentence + English Sentence | `example` / `example_translation`, kept only when both exist (reading card); 城市 yields recognition + production only |
| Audio, images, pinyin, cloze text | NOT carried (see gaps) |

Pack meta: `language_code zh`, `script han`, `tokenizer char`.
Grammar list is empty: the deck is vocabulary-only and grammar stays
AI-owned per the skill's grounding rules (same division as Anki-only).

## Stage coverage vs the pipeline plan (300 / 800 / 1500 / 2500)

`plan` prints the four default curriculum stages; the pack fills them
with HSK levels one-to-one:

| Stage | Plan target | Pack content | Coverage |
|---|---|---|---|
| 1 bridge | 300 vocab | 203 (HSK1) | 68% |
| 2 input | 800 vocab | 191 (HSK2) | 24% |
| 3 expansion | 1500 vocab | 335 (HSK3) | 22% |
| 4 fluency | 2500 vocab | 728 (HSK4 + 1 untagged) | 29% |

Targets are adjustable defaults (SPEC: "override-adjustable"), not
promises the pack must fill — the honest reading is per-stage: the
whole of HSK N is in stage N, nothing invented to pad the numbers.
Lesson pacing (unlock 3–5 lessons per block, in order) is expressed by
the `lesson-NN` tags plus file order; the generator's within-stage
order is alphabetical-by-gloss and seeded-shuffled, so lesson-block
unlocks read the pack/tags, not the shuffled output.

## Anki-only vs pipeline, feature by feature

| Anki-only workflow | Pipeline with this pack | Verdict |
|---|---|---|
| Recognition + cloze cards per note (2915 cards) | Recognition + production + reading per entry (4370 cards: 609 / 573 / 1004 / 2184 per stage) | Pipeline covers both deck templates; reading cards reuse the deck sentences |
| Manual suspend/unsuspend per lesson block | `generate --stage N`, lesson blocks via `lesson-NN` tags | At least as good; stage select is one command |
| No plan numbers | `plan` prints 300/800/1500/2500 stages; `stats` tracks per-stage recall | Pipeline adds what Anki never had |
| Idempotent by Anki's duplicate check | Content-keyed sync ledger; full-deck mock sync adds 4291 notes, re-sync adds 0 | Equivalent; verified on the real pack |
| Native audio on every card, images on ~700 | Text only | GAP: the pipeline does not carry media. Audio-first study still needs Anki |
| Grammar via wiki lookups (agent-owned) | Same (grammar list empty, skill-owned) | Parity |

## Known limits (not hidden)

* Media gap above — the one dimension where Anki-only still wins.
* 37 English glosses cover 2+ Chinese words each (e.g. 星期天/星期日
  both "sunday"). Both notes are kept; each card links to its own entry
  via the stage-qualified content key. Same ambiguity exists
  in the deck itself.
* Full-deck sync collapses 79 identical front/back pairs (mostly
  repeated example sentences) — the same duplicates Anki would refuse.
* Deck gaps carried faithfully: 城市 (no translation → no reading
  card), 死 (untagged → stage 4).
