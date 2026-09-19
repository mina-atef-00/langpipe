"""Anki bridge over AnkiConnect, with an in-memory mock.

The bridge has a pluggable backend. Two backends ship:

* :class:`MockAnkiBackend` keeps notes in memory so the test suite and CLI work
  without Anki installed.
* :class:`AnkiConnectBackend` talks to a running Anki instance through the
  AnkiConnect HTTP add-on (https://git.sr.ht/~foosoft/anki-connect).

The client uses the standard library only (urllib), so no HTTP framework is a
dependency. When the server is not reachable the backend reports it and the CLI
fails loudly instead of pretending the sync happened.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

ANKICONNECT_URL = "http://127.0.0.1:8765"
REQUEST_TIMEOUT = 3.0
ANKI_MODEL = "Basic"


@dataclass(frozen=True)
class SyncNote:
    front: str
    back: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyncResult:
    backend: str
    reachable: bool
    deck: str
    notes_added: int
    note_ids: list[int]
    # accepted[i] is True iff the backend accepted notes[i]; False entries are
    # duplicates the backend skipped. Same length as the submitted notes list.
    accepted: list[bool] = field(default_factory=list)
    error: str | None = None
    # notes the backend was willing to take but then refused at write time.
    # Non-zero means the sync was partial: the caller must not record those
    # notes as synced, and should report the failure instead of claiming
    # success.
    notes_refused: int = 0


class AnkiBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def sync(self, notes: list[SyncNote], deck: str) -> SyncResult: ...


class MockAnkiBackend:
    """In-memory Anki. Notes are stored in a dict keyed by deck name."""

    name = "mock"

    def __init__(self) -> None:
        self.decks: dict[str, list[SyncNote]] = {}
        self._next_id = 1

    def is_available(self) -> bool:
        return True

    def sync(self, notes: list[SyncNote], deck: str) -> SyncResult:
        stored = self.decks.setdefault(deck, [])
        # Duplicate detection keyed on note content: a re-sync with the same
        # front/back skips notes that are already present, so syncing is
        # idempotent.
        seen = {(n.front, n.back) for n in stored}
        ids: list[int] = []
        accepted: list[bool] = []
        for note in notes:
            if (note.front, note.back) in seen:
                accepted.append(False)
                continue
            seen.add((note.front, note.back))
            stored.append(note)
            ids.append(self._next_id)
            self._next_id += 1
            accepted.append(True)
        return SyncResult(
            backend=self.name,
            reachable=True,
            deck=deck,
            notes_added=len(ids),
            note_ids=ids,
            accepted=accepted,
        )


class AnkiConnectBackend:
    """Real AnkiConnect client over HTTP."""

    name = "ankiconnect"

    def __init__(self, url: str = ANKICONNECT_URL, timeout: float = REQUEST_TIMEOUT) -> None:
        self.url = url
        self.timeout = timeout

    def _request(self, action: str, **params: object) -> Any:
        payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode())
        if body.get("error"):
            raise RuntimeError(f"AnkiConnect error for {action}: {body['error']}")
        return body.get("result")

    def is_available(self) -> bool:
        try:
            result = self._request("version")
            return isinstance(result, int)
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError, RuntimeError):
            return False

    def sync(self, notes: list[SyncNote], deck: str) -> SyncResult:
        if not self.is_available():
            return SyncResult(
                backend=self.name,
                reachable=False,
                deck=deck,
                notes_added=0,
                note_ids=[],
                error=f"AnkiConnect not reachable at {self.url}",
            )
        try:
            self._request("createDeck", deck=deck)
            # Ask AnkiConnect which notes would be duplicates of what is
            # already in the deck, and only submit the rest. This makes a
            # re-sync idempotent: notes already present are skipped.
            can_add = self._request(
                "canAddNotes",
                notes=[
                    {
                        "deckName": deck,
                        "modelName": ANKI_MODEL,
                        "fields": {"Front": n.front, "Back": n.back},
                    }
                    for n in notes
                ],
            )
            preflight = [bool(ok) for ok in (can_add or [])][: len(notes)]
            # (index into `notes`, note) for everything the pre-flight cleared.
            fresh: list[tuple[int, SyncNote]] = [
                (i, n) for i, n in enumerate(notes) if i < len(preflight) and preflight[i]
            ]
            payload = [
                {
                    "deckName": deck,
                    "modelName": ANKI_MODEL,
                    "fields": {"Front": n.front, "Back": n.back},
                    "tags": n.tags,
                }
                for _, n in fresh
            ]
            raw = self._request("addNotes", notes=payload) if payload else []
        except RuntimeError as exc:
            return SyncResult(
                backend=self.name,
                reachable=True,
                deck=deck,
                notes_added=0,
                note_ids=[],
                error=str(exc),
            )
        # addNotes answers per submitted note with an id, or null when Anki
        # refused that note (bad model, duplicate across decks, read-only
        # collection, ...). `accepted` must reflect that outcome, not the
        # canAddNotes prediction: a note Anki refused was NOT synced, and
        # recording it as synced would lose it forever, silently.
        written = list(raw) if isinstance(raw, list) else []
        accepted = [False] * len(notes)
        refused = 0
        for position, (index, _note) in enumerate(fresh):
            note_id = written[position] if position < len(written) else None
            if note_id is None:
                refused += 1
                continue
            accepted[index] = True
        ids = [int(x) for x in written if x is not None]
        error = None
        if refused:
            error = f"Anki refused {refused} of {len(fresh)} submitted notes"
        return SyncResult(
            backend=self.name,
            reachable=True,
            deck=deck,
            notes_added=len(ids),
            note_ids=ids,
            accepted=accepted,
            error=error,
            notes_refused=refused,
        )
