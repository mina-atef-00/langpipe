"""Build the Chinese (HSK 1-4) language pack from the real Anki deck.

Reads the Natural Language Journey ``Chinese_Vocabulary_HSK_1-4.apkg``
(a standard Anki zip: ``collection.anki21`` SQLite + media) and emits
``src/lesan_pipe/packs/chinese-hsk1-4.json``.

Mapping (documented, deterministic):
* one pack entry per "Chinese Vocab (HSK)" note (11 fields);
* ``stage`` = HSK level from the note tags (HSK1..HSK4). The single
  untagged note lands in stage 4 with an ``untagged`` tag;
* lesson order is preserved twice: the file lists entries by
  (stage, lesson, chinese), and every entry keeps a zero-padded
  ``lesson-NN`` tag alongside its verbatim ``HSK#`` tag;
* ``l1`` = English gloss, ``l2`` = Chinese (same convention as the
  demo Spanish pack: recognition is L1 -> L2, production L2 -> L1);
* ``example`` / ``example_translation`` = deck Sentence / English
  Sentence, kept only when both are present (one note lacks the
  translation, so it yields recognition + production but no reading
  card);
* audio, images, pinyin, and cloze sentences stay in the .apkg: the
  repo ships the mechanism, not the content, and a text JSON pack
  cannot carry 78 MB of media. See docs/chinese-pack.md.

Stdlib only. Usage:

    python scripts/build_chinese_pack.py [--deck PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DECK = Path.home() / "wiki/study/chinese/assets/Chinese_Vocabulary_HSK_1-4.apkg"
DEFAULT_OUT = REPO / "src/lesan_pipe/packs/chinese-hsk1-4.json"

MODEL_NAME = "Chinese Vocab (HSK)"
LESSON_RE = re.compile(r"^Lesson\s+(\d+)\s*$")
HSK_RE = re.compile(r"^HSK([1-4])$")
FIELD_SEP = "\x1f"

META = {
    "name": "chinese-hsk1-4",
    "language_code": "zh",
    "language_name": "Chinese",
    "script": "han",
    "tokenizer": "char",
    "rtl": False,
    "note": (
        "Generated from the Natural Language Journey HSK 1-4 deck "
        "(Anki deck ID 1352957654, note type 'Chinese Vocab (HSK)') by "
        "scripts/build_chinese_pack.py. Stage = HSK level from the note "
        "tags; lesson order is preserved in file order and in lesson-NN "
        "tags. Recognition cards read English -> Chinese, production "
        "cards Chinese -> English, reading cards use the deck example "
        "sentences. Deck audio/images are not carried (see "
        "docs/chinese-pack.md); grammar is AI-owned per the skill's "
        "grounding rules, so the grammar list is empty."
    ),
}


def _extract_collection(apkg: Path, tmpdir: str) -> Path:
    with zipfile.ZipFile(apkg) as zf:
        names = zf.namelist()
        for candidate in ("collection.anki21", "collection.anki2"):
            if candidate in names:
                return Path(zf.extract(candidate, tmpdir))
    raise ValueError(f"{apkg} has no collection database (saw: {names[:5]}...)")


def _read_notes(db_path: Path) -> list[dict[str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        models = json.loads(conn.execute("select models from col").fetchone()[0])
        mid = next(m for m, mdef in models.items() if mdef["name"] == MODEL_NAME)
        fields = [f["name"] for f in models[mid]["flds"]]
        notes = []
        for tags, flds in conn.execute("select tags, flds from notes where mid = ?", (mid,)):
            parts = flds.split(FIELD_SEP)
            if len(parts) != len(fields):
                print(f"WARN: skipping note with {len(parts)} fields (expected {len(fields)})")
                continue
            note = dict(zip(fields, (p.strip() for p in parts), strict=True))
            note["_tags"] = tags.split()
            notes.append(note)
        return notes
    finally:
        conn.close()


def _stage_and_tags(note: dict[str, str]) -> tuple[int, list[str], int | None]:
    levels = sorted({int(m.group(1)) for t in note["_tags"] if (m := HSK_RE.match(t))})
    if len(levels) > 1:
        word = note["Chinese"]
        print(f"WARN: multi-HSK {word!r} {note['_tags']}: using HSK{levels[0]}")
    hsk = levels[0] if levels else None
    tags = [f"HSK{hsk}"] if hsk else ["untagged"]
    m = LESSON_RE.match(note.get("Lesson", ""))
    lesson = int(m.group(1)) if m else None
    if lesson is not None:
        tags.append(f"lesson-{lesson:02d}")
    return (hsk or 4, tags, lesson)


def build(deck_path: Path) -> tuple[dict, dict[str, int]]:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = _extract_collection(deck_path, tmpdir)
        notes = _read_notes(db_path)

    entries = []
    stats: dict[str, int] = {"notes": len(notes), "untagged": 0, "no_example": 0}
    for note in notes:
        stage, tags, lesson = _stage_and_tags(note)
        if "untagged" in tags:
            stats["untagged"] += 1
        example, example_translation = note["Sentence"], note["English Sentence"]
        if not (example and example_translation):
            stats["no_example"] += 1
            example, example_translation = "", ""
        entries.append(
            {
                "l1": note["English"],
                "l2": note["Chinese"],
                "stage": stage,
                "pos": "",
                "tags": tags,
                "example": example,
                "example_translation": example_translation,
                "_lesson": lesson or 999,
            }
        )
        stats[f"stage-{stage}"] = stats.get(f"stage-{stage}", 0) + 1

    entries.sort(key=lambda e: (e["stage"], e["_lesson"], e["l2"]))
    for e in entries:
        del e["_lesson"]

    # Duplicate report: identical English glosses share a generator content
    # key, so flag them rather than silently dropping cards later.
    seen: dict[str, str] = {}
    for e in entries:
        if e["l1"] in seen and seen[e["l1"]] != e["l2"]:
            print(f"WARN: gloss {e['l1']!r} maps to both {seen[e['l1']]!r} and {e['l2']!r}")
        seen.setdefault(e["l1"], e["l2"])
    stats["distinct_l1"] = len(seen)

    return {"meta": META, "vocabulary": entries, "grammar": []}, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Chinese HSK pack from the Anki deck.")
    parser.add_argument("--deck", type=Path, default=DEFAULT_DECK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.deck.exists():
        raise SystemExit(f"deck not found: {args.deck} (pass --deck PATH)")

    pack, stats = build(args.deck)
    args.out.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KiB)")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")


if __name__ == "__main__":
    main()
