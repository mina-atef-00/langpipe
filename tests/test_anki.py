"""Anki bridge tests: mock backend and unreachable detection."""

from __future__ import annotations

from langpipe.anki import AnkiConnectBackend, MockAnkiBackend, SyncNote


def test_mock_backend_sync() -> None:
    backend = MockAnkiBackend()
    assert backend.is_available() is True
    notes = [SyncNote("a", "b"), SyncNote("c", "d")]
    result = backend.sync(notes, "deck1")
    assert result.reachable is True
    assert result.notes_added == 2
    assert result.note_ids == [1, 2]
    assert len(backend.decks["deck1"]) == 2


def test_mock_backend_accumulates() -> None:
    backend = MockAnkiBackend()
    backend.sync([SyncNote("a", "b")], "d")
    result = backend.sync([SyncNote("c", "d")], "d")
    assert result.note_ids == [2]
    assert len(backend.decks["d"]) == 2


def test_mock_backend_separate_decks() -> None:
    backend = MockAnkiBackend()
    backend.sync([SyncNote("a", "b")], "one")
    backend.sync([SyncNote("c", "d")], "two")
    assert len(backend.decks["one"]) == 1
    assert len(backend.decks["two"]) == 1


def test_mock_backend_re_sync_adds_zero_notes() -> None:
    backend = MockAnkiBackend()
    notes = [SyncNote("a", "b"), SyncNote("c", "d")]
    first = backend.sync(notes, "deck1")
    second = backend.sync(notes, "deck1")
    assert first.notes_added == 2
    assert second.notes_added == 0
    assert second.note_ids == []
    assert len(backend.decks["deck1"]) == 2


def test_mock_backend_re_sync_adds_only_new_notes() -> None:
    backend = MockAnkiBackend()
    backend.sync([SyncNote("a", "b")], "d")
    result = backend.sync([SyncNote("a", "b"), SyncNote("e", "f")], "d")
    assert result.notes_added == 1
    assert len(backend.decks["d"]) == 2


def test_mocks_duplicate_only_within_same_deck() -> None:
    backend = MockAnkiBackend()
    notes = [SyncNote("a", "b")]
    backend.sync(notes, "one")
    result = backend.sync(notes, "two")
    assert result.notes_added == 1
    assert len(backend.decks["two"]) == 1


def test_ankiconnect_unreachable_reports_failure() -> None:
    backend = AnkiConnectBackend(url="http://127.0.0.1:1", timeout=0.5)
    assert backend.is_available() is False
    result = backend.sync([SyncNote("a", "b")], "d")
    assert result.reachable is False
    assert result.notes_added == 0
    assert "not reachable" in (result.error or "")
