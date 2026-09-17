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
    error: str | None = None


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
        ids: list[int] = []
        for note in notes:
            stored.append(note)
            ids.append(self._next_id)
            self._next_id += 1
        return SyncResult(
            backend=self.name,
            reachable=True,
            deck=deck,
            notes_added=len(notes),
            note_ids=ids,
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
            raw = self._request(
                "addNotes",
                notes=[
                    {
                        "deckName": deck,
                        "modelName": ANKI_MODEL,
                        "fields": {"Front": n.front, "Back": n.back},
                        "tags": n.tags,
                    }
                    for n in notes
                ],
            )
        except RuntimeError as exc:
            return SyncResult(
                backend=self.name,
                reachable=True,
                deck=deck,
                notes_added=0,
                note_ids=[],
                error=str(exc),
            )
        ids = [int(x) for x in raw if x is not None]
        return SyncResult(
            backend=self.name,
            reachable=True,
            deck=deck,
            notes_added=len(ids),
            note_ids=ids,
        )
