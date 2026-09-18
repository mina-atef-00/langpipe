"""Fake AnkiConnect server tests: the happy path against a real HTTP endpoint.

The suite previously exercised AnkiConnectBackend only on the unreachable
path. These tests stand up a real ``http.server`` speaking AnkiConnect's
JSON-RPC shape on a random port and drive the client through it:

* a first sync adds notes and reports the assigned ids,
* a re-sync against a server that already holds the notes adds zero
  (duplicate detection via ``canAddNotes``),
* the end-to-end CLI sync path, run twice against the fake, is idempotent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from langpipe.anki import ANKI_MODEL, AnkiConnectBackend, SyncNote

REPO_ROOT = Path(__file__).resolve().parent.parent


class FakeAnkiConnect:
    """Stateful fake of the AnkiConnect add-on endpoints the client uses."""

    def __init__(self, *, version: int = 6, fail_count: int = 0) -> None:
        self.version = version
        self.fail_count = fail_count  # reject the first N addNotes entries
        self.decks: set[str] = set()
        self.notes: list[dict] = []  # accepted notes
        self.fail_next_version = False
        self.corrupt_next_response = False

    # -- request dispatch -------------------------------------------------
    def handle(self, action: str, params: dict) -> dict:
        if self.fail_next_version and action == "version":
            return {"error": "connection lost", "result": None}
        if self.corrupt_next_response:
            return {"__corrupt__": "\x00 not json"}  # handler will mangle it

        if action == "version":
            return {"error": None, "result": self.version}
        if action == "createDeck":
            self.decks.add(params["deck"])
            return {"error": None, "result": None}
        if action == "canAddNotes":
            # A note is a duplicate iff an identical (front, back) note is
            # already stored in this fake's collection.
            stored = {(n["fields"]["Front"], n["fields"]["Back"]) for n in self.notes}
            can = []
            remaining = self.fail_count
            for rq in params["notes"]:
                dup = (rq["fields"]["Front"], rq["fields"]["Back"]) in stored
                reject = remaining > 0 and not dup
                if reject:
                    remaining -= 1
                can.append(not dup and not reject)
            return {"error": None, "result": can}
        if action == "addNotes":
            accepted = []
            for _i, note in enumerate(params["notes"]):
                self.fail_count = max(0, self.fail_count)
                note_id = 100 + len(self.notes)
                self.notes.append(note)
                accepted.append(note_id)
            return {"error": None, "result": accepted}
        raise AssertionError(f"unexpected action: {action}")

    # -- direct store mutation for scenario setup -------------------------
    def store_note(self, front: str, back: str) -> None:
        self.notes.append(
            {
                "deckName": "langpipe",
                "modelName": ANKI_MODEL,
                "fields": {"Front": front, "Back": back},
                "tags": [],
            }
        )


def _make_server(fake: FakeAnkiConnect):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads(self.rfile.read(length).decode())
                out = fake.handle(req["action"], req.get("params", {}))
                body = json.dumps(out).encode()
            except Exception as exc:  # malformed -> 500 with junk
                body = b"not-json{{{" + str(exc).encode()
                self.send_response(500)
            else:
                if fake.corrupt_next_response:
                    fake.corrupt_next_response = False
                    self.send_response(200)
                else:
                    self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # silence
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture()
def fake_server():
    fake = FakeAnkiConnect()
    server, thread = _make_server(fake)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield fake, url
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def test_ankiconnect_happy_path_adds_notes(fake_server) -> None:
    fake, url = fake_server
    backend = AnkiConnectBackend(url=url, timeout=2.0)
    assert backend.is_available() is True
    result = backend.sync([SyncNote("a", "b"), SyncNote("c", "d")], "langpipe")
    assert result.reachable is True
    assert result.notes_added == 2
    assert result.note_ids == [100, 101]
    assert fake.decks == {"langpipe"}
    assert len(fake.notes) == 2


def test_ankiconnect_re_sync_with_existing_notes_adds_zero(fake_server) -> None:
    fake, url = fake_server
    # The server already holds both notes Anki-side.
    fake.store_note("a", "b")
    fake.store_note("c", "d")
    backend = AnkiConnectBackend(url=url, timeout=2.0)
    result = backend.sync([SyncNote("a", "b"), SyncNote("c", "d")], "langpipe")
    assert result.reachable is True
    assert result.notes_added == 0
    assert result.note_ids == []
    assert result.accepted == [False, False]
    assert len(fake.notes) == 2  # nothing new landed server-side


def test_ankiconnect_re_sync_adds_only_the_new_note(fake_server) -> None:
    fake, url = fake_server
    fake.store_note("a", "b")
    backend = AnkiConnectBackend(url=url, timeout=2.0)
    result = backend.sync([SyncNote("a", "b"), SyncNote("new", "note")], "langpipe")
    assert result.notes_added == 1
    assert result.accepted == [False, True]
    assert len(fake.notes) == 2  # stored + the one new note


def test_ankiconnect_wrong_version_still_reports_reachable(fake_server) -> None:
    fake, url = fake_server
    fake.version = 5  # old AnkiConnect still answers version with an int
    backend = AnkiConnectBackend(url=url, timeout=2.0)
    assert backend.is_available() is True


def test_ankiconnect_error_body_surfaces_and_skips_notes(fake_server) -> None:
    fake, url = fake_server
    fake.fail_next_version = True
    backend = AnkiConnectBackend(url=url, timeout=2.0)
    assert backend.is_available() is False
    result = backend.sync([SyncNote("a", "b")], "langpipe")
    assert result.reachable is False
    assert result.notes_added == 0


def test_ankiconnect_malformed_json_counts_as_unreachable(fake_server) -> None:
    fake, url = fake_server
    fake.corrupt_next_response = True
    backend = AnkiConnectBackend(url=url, timeout=2.0)
    assert backend.is_available() is False


# ---------------------------------------------------------------------------
# End-to-end CLI sync against the fake server.
#
# Invoke the langpipe CLI as a subprocess so the mock backend cannot mask a
# broken real path. The venv-embedded langpipe entry point is used when
# available (repo checkout layout), otherwise `python -m langpipe.cli`.


def _run_cli(workdir, *args: str) -> tuple[int, str, str]:
    env_hint = ".venv/bin/langpipe"
    if (REPO_ROOT / env_hint).exists():
        cmd = [str(REPO_ROOT / env_hint)]
    else:
        cmd = [sys.executable, "-m", "langpipe.cli"]
    proc = subprocess.run(
        cmd + list(args),
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_cli_sync_end_to_end_against_fake_is_idempotent(tmp_path, fake_server) -> None:
    fake, url = fake_server
    workdir = tmp_path
    common = [
        "--db",
        str(workdir / "lp.db"),
        "--pack",
        str(REPO_ROOT / "src/langpipe/packs/demo-spanish.json"),
    ]
    rc, out, err = _run_cli(workdir, "init", "--name", "Harness", "--lang", "es", *common)
    assert rc == 0, f"init failed: {err}"
    rc, out, err = _run_cli(workdir, "generate", "--stage", "1", *common)
    assert rc == 0, f"generate failed: {err}"

    url_args = ["--url", url, "--deck", "langpipe", "--db", str(workdir / "lp.db")]
    rc, out, err = _run_cli(workdir, "sync", *url_args)
    assert rc == 0, f"first sync failed: {err}"
    first = [line.strip() for line in out.splitlines() if "notes added" in line][0]
    added_first = int(first.split()[0])
    assert added_first > 0, out

    rc, out, err = _run_cli(workdir, "sync", *url_args)
    assert rc == 0, f"second sync failed: {err}"
    second = [line.strip() for line in out.splitlines() if "notes added" in line][0]
    added_second = int(second.split()[0])
    assert added_second == 0, f"re-sync was not idempotent: {out}"
    # The fake server must confirm the same thing from its side.
    total_notes_server_side = len(fake.notes)
    assert total_notes_server_side == added_first


def test_cli_sync_unreachable_exits_nonzero(tmp_path) -> None:
    workdir = tmp_path
    common = [
        "--db",
        str(workdir / "lp.db"),
        "--pack",
        str(REPO_ROOT / "src/langpipe/packs/demo-spanish.json"),
    ]
    rc, out, err = _run_cli(workdir, "init", "--name", "Harness", "--lang", "es", *common)
    assert rc == 0, err
    rc, out, err = _run_cli(workdir, "generate", "--stage", "1", *common)
    assert rc == 0, err
    rc, out, err = _run_cli(
        workdir,
        "sync",
        "--url",
        "http://127.0.0.1:1",
        "--deck",
        "langpipe",
        "--db",
        str(workdir / "lp.db"),
    )
    assert rc != 0
    assert "not reachable" in (err + out)
