#!/usr/bin/env python3
"""End-to-end acceptance run for Lesan Pipe (goal criterion 6).

Fresh-installs ``lesan_pipe`` from this checkout into an empty virtualenv,
drives all seven MCP tools through the real stdio server against a temporary
database, then performs a real AnkiConnect HTTP sync (not ``--mock``) against
a local AnkiConnect test double and proves the re-sync is idempotent. Every
step is recorded into a Markdown transcript; any failure aborts loudly with a
non-zero exit so CI reads it as red.

Stdlib only, so the CI job needs nothing beyond Python itself:

    python3 scripts/e2e_acceptance.py --transcript /tmp/e2e-transcript.md

The committed ``docs/e2e-transcript.md`` is a sample from one passing run, not
a living document: re-run this script for fresh evidence.

WHY a script and not another pytest file: pytest runs against the checkout's
code in place, but the acceptance criterion demands a *fresh install from a
clean state* — an isolated venv built from the packaged distribution — plus a
live server round-trip. That is an operations harness, not a unit test.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = REPO_ROOT / "hermes-plugin" / "server" / "lesan_pipe_mcp.py"

EXPECTED_TOOLS = (
    "lesan_pipe_init",
    "lesan_pipe_plan",
    "lesan_pipe_generate",
    "lesan_pipe_cards",
    "lesan_pipe_review",
    "lesan_pipe_stats",
    "lesan_pipe_sync",
)

REAL_SYNC_DECK = "lesan_pipe_e2e"
MAX_OUTPUT_LINES = 40


class AcceptanceFailure(Exception):
    """A step failed: the run is red and the transcript says where."""


# ── Transcript ───────────────────────────────────────────────────────────────


class Transcript:
    def __init__(self) -> None:
        self._sections: list[str] = []
        self.steps_run = 0
        self.steps_passed = 0

    def header(self, text: str) -> None:
        self._sections.append(f"# {text}\n")

    def note(self, text: str) -> None:
        self._sections.append(f"{text}\n")

    def step(self, title: str, body: str) -> None:
        self.steps_run += 1
        self.steps_passed += 1
        self._sections.append(f"## PASS: {title}\n\n{body}\n")

    def failure(self, title: str, body: str) -> None:
        self.steps_run += 1
        self._sections.append(f"## FAIL: {title}\n\n{body}\n")

    def render(self) -> str:
        total = f"_Steps: {self.steps_passed}/{self.steps_run} passed._\n"
        return "\n".join(self._sections) + "\n" + total

    @staticmethod
    def excerpt(output: str) -> str:
        lines = output.strip().splitlines()
        if len(lines) > MAX_OUTPUT_LINES:
            head = "\n".join(lines[:MAX_OUTPUT_LINES])
            return f"{head}\n... ({len(lines) - MAX_OUTPUT_LINES} more lines)"
        return "\n".join(lines)


# ── Fake AnkiConnect ─────────────────────────────────────────────────────────
#
# A local HTTP server speaking the AnkiConnect JSON-RPC shape the real client
# uses (version / createDeck / canAddNotes / addNotes) with content-keyed
# duplicate detection. It stands in for Anki itself, which CI does not have;
# the HTTP path, the client handshake, and the CLI ledger are all real.


class FakeAnkiConnect:
    def __init__(self) -> None:
        self.decks: set[str] = set()
        self.notes: list[dict] = []

    def handle(self, action: str, params: dict) -> dict:
        if action == "version":
            return {"error": None, "result": 6}
        if action == "createDeck":
            self.decks.add(params["deck"])
            return {"error": None, "result": None}
        if action == "canAddNotes":
            # Content-keyed duplicate detection, mirroring the collection and
            # the mock backend: a note is a duplicate of what is stored, or of
            # an earlier note in the same batch (real Anki refuses those too).
            seen = {(n["fields"]["Front"], n["fields"]["Back"]) for n in self.notes}
            can = []
            for rq in params["notes"]:
                key = (rq["fields"]["Front"], rq["fields"]["Back"])
                if key in seen:
                    can.append(False)
                else:
                    can.append(True)
                    seen.add(key)
            return {"error": None, "result": can}
        if action == "addNotes":
            ids = []
            for note in params["notes"]:
                ids.append(100 + len(self.notes))
                self.notes.append(note)
            return {"error": None, "result": ids}
        raise AssertionError(f"unexpected action: {action}")


def start_fake_ankiconnect(fake: FakeAnkiConnect) -> tuple[HTTPServer, threading.Thread, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads(self.rfile.read(length).decode())
                body = json.dumps(fake.handle(req["action"], req.get("params", {}))).encode()
            except Exception as exc:  # malformed -> 500, like a broken add-on
                body = f"not-json: {exc}".encode()
                self.send_response(500)
            else:
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # silence
            pass

    # Bind explicitly to IPv4 loopback: the client URL is 127.0.0.1 by contract.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()
    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{port}"


# ── MCP stdio client ─────────────────────────────────────────────────────────


class McpClient:
    """Minimal JSON-RPC 2.0 client over the server's stdin/stdout pipes."""

    def __init__(self, env: dict[str, str]) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, str(SERVER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self._stderr_lines: list[str] = []
        self._next_id = 0
        thread = threading.Thread(target=self._drain_stderr, daemon=True)
        thread.start()

    def _drain_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self._stderr_lines.append(line.rstrip())

    def _request(self, method: str, params: dict) -> dict:
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._next_id += 1
        self._proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": self._next_id, "method": method,
                        "params": params}) + "\n"
        )
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise AcceptanceFailure(
                f"MCP server closed stdout during '{method}'. "
                f"stderr was: {' | '.join(self._stderr_lines) or '(empty)'}"
            )
        return json.loads(line)

    def tools_list(self) -> list[dict]:
        response = self._request("tools/list", {})
        if "error" in response:
            raise AcceptanceFailure(f"tools/list failed: {response['error']}")
        return response["result"]["tools"]

    def call(self, name: str, arguments: dict) -> tuple[str, bool]:
        response = self._request("tools/call", {"name": name, "arguments": arguments})
        if "error" in response:
            raise AcceptanceFailure(f"tools/call {name} got JSON-RPC error: {response['error']}")
        result = response["result"]
        content = result.get("content", [])
        if len(content) != 1 or content[0].get("type") != "text":
            raise AcceptanceFailure(f"tools/call {name} returned non-text content: {result}")
        return content[0]["text"], bool(result.get("isError", False))

    def close(self) -> None:
        if self._proc.stdin is not None:
            self._proc.stdin.close()
        self._proc.wait(timeout=30)


# ── Steps ────────────────────────────────────────────────────────────────────


def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=600, **kwargs)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lesan Pipe end-to-end acceptance run.")
    parser.add_argument("--repo", default=str(REPO_ROOT), help="Checkout to install from.")
    parser.add_argument(
        "--transcript", default=None, help="Where to write the Markdown transcript."
    )
    parser.add_argument("--keep", action="store_true", help="Keep the temp workdir for inspection.")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    transcript_path = Path(args.transcript) if args.transcript else None
    for required in ("pyproject.toml", "hermes-plugin/server/lesan_pipe_mcp.py"):
        if not (repo / required).is_file():
            print(f"E2E FAILED: --repo {repo} has no {required}; not a lesan_pipe checkout.")
            return 2

    transcript = Transcript()
    workdir = Path(tempfile.mkdtemp(prefix="lesan_e2e_"))
    if transcript_path is None:
        transcript_path = workdir / "e2e-transcript.md"
    failed: str | None = None
    try:
        _run_all(repo, workdir, transcript)
    except AcceptanceFailure as exc:
        failed = str(exc)
        transcript.failure("acceptance step", failed)
    except Exception as exc:  # never die without writing the transcript
        failed = f"unexpected {type(exc).__name__}: {exc}"
        transcript.failure("harness error", failed)
    transcript_path.write_text(transcript.render(), encoding="utf-8")

    print(f"workdir: {workdir}")
    print(f"transcript: {transcript_path}")
    if failed is not None:
        print(f"E2E FAILED: {failed}")
        print(f"workdir kept for inspection: {workdir}")
        return 1
    print(f"E2E PASSED ({transcript.steps_passed}/{transcript.steps_run} steps)")
    if not args.keep:
        shutil.rmtree(workdir, ignore_errors=True)
    else:
        print(f"workdir kept for inspection: {workdir}")
    return 0


def _run_all(repo: Path, workdir: Path, transcript: Transcript) -> None:
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    commit = run(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo))
    transcript.header("Lesan Pipe end-to-end acceptance transcript")
    transcript.note(
        f"Run at {stamp}; checkout `{repo}` at commit "
        f"`{(commit.stdout or '?').strip()}`; harness Python "
        f"{sys.version.split()[0]}. Every step below ran for real in order; "
        "a step that failed would abort the run and this transcript would end "
        "there. (`mock` sync exercises the tool plumbing hermetically; the "
        "Anki sync in step 9 speaks real AnkiConnect HTTP to a local test "
        "double, because CI has no Anki installed.)\n"
    )

    # — 1. Fresh install from a clean state ————————————————————————————
    venv = workdir / "install-venv"
    proc = run([sys.executable, "-m", "venv", str(venv)])
    check(proc.returncode == 0, f"venv creation failed: {proc.stderr[-2000:]}")
    pip = venv / "bin" / "pip"
    if not pip.is_file():
        # Some base images ship venv without pip: bootstrap from stdlib.
        proc = run([str(venv / "bin" / "python"), "-m", "ensurepip"])
        check(proc.returncode == 0, f"ensurepip failed: {proc.stderr[-2000:]}")
    proc = run([str(pip), "install", str(repo)])
    check(proc.returncode == 0, f"fresh pip install of {repo} failed: {proc.stderr[-3000:]}")
    console = venv / "bin" / "lesan_pipe"
    check(console.is_file(), f"fresh install produced no console script at {console}")
    proc = run([str(console), "--help"])
    check(proc.returncode == 0, f"fresh lesan_pipe --help failed: {proc.stderr[-2000:]}")
    check("lesan_pipe" in proc.stdout, "fresh lesan_pipe --help printed no lesan_pipe text")
    transcript.step(
        "fresh install from a clean state",
        f"Created an empty venv, ran `pip install {repo}` (non-editable: this "
        f"builds the wheel, so broken packaging fails here), and the fresh "
        f"`lesan_pipe --help` exits 0. Console script: `{console}`.",
    )

    # — 2. MCP server speaks: initialize + seven tools listed ———————————
    db = workdir / "e2e.db"
    plugin_data = workdir / "plugin-data"
    plugin_data.mkdir()
    env = dict(os.environ)
    env["LESAN_PIPE_BIN"] = str(console)  # the server must drive the fresh install
    env["PLUGIN_DATA"] = str(plugin_data)
    env.pop("LESAN_PIPE_DB", None)
    client = McpClient(env)
    try:
        hello = client._request("initialize", {"protocolVersion": "2025-06-18"})
        check("result" in hello, f"MCP initialize failed: {hello}")
        server_info = hello["result"].get("serverInfo", {})
        check(server_info.get("name") == "lesan_pipe", f"unexpected serverInfo: {server_info}")
        tools = client.tools_list()
        names = [t["name"] for t in tools]
        check(
            tuple(names) == EXPECTED_TOOLS,
            f"expected tools {list(EXPECTED_TOOLS)}, server listed {names}",
        )
        transcript.step(
            "MCP server handshake and tool catalogue",
            f"`initialize` reports `{server_info}`; `tools/list` returns exactly "
            f"the seven tools: {', '.join(names)}.",
        )

        # — 3-8. Six tools against the temporary database ——————————————
        def tool(name: str, arguments: dict, anchor: str, title: str) -> str:
            text, is_error = client.call(name, arguments)
            check(not is_error, f"{name} returned a tool error: {text[:2000]}")
            check(anchor in text, f"{name} output missing {anchor!r}: {text[:2000]}")
            transcript.step(title, f"`{name}` ok.\n\n```\n{Transcript.excerpt(text)}\n```")
            return text

        tool(
            "lesan_pipe_init",
            {"name": "E2E", "lang": "es", "seed": 42, "db": str(db)},
            "Initialised learner",
            "tool 1/7: init creates the learner in a temporary database",
        )
        tool(
            "lesan_pipe_plan", {"db": str(db)}, "stage 1", "tool 2/7: plan prints the curriculum"
        )
        tool(
            "lesan_pipe_generate",
            {"db": str(db), "stage": 1, "seed": 42},
            "stage 1",
            "tool 3/7: generate builds the stage-1 cards",
        )
        text = tool(
            "lesan_pipe_cards", {"db": str(db)}, "[1]", "tool 4/7: cards lists stored cards"
        )
        check("[2]" in text, f"expected several cards, cards output was: {text[:2000]}")
        tool(
            "lesan_pipe_review",
            {"db": str(db), "card_id": 1, "grade": 4},
            "graded 4",
            "tool 5/7: review records a grade-4 SM-2 review",
        )
        tool(
            "lesan_pipe_stats",
            {"db": str(db)},
            "retention rate",
            "tool 6/7: stats reports retention from the review log",
        )
        tool(
            "lesan_pipe_sync",
            {"db": str(db), "mock": True},
            "notes added",
            "tool 7/7: sync pushes cards through the mock backend",
        )

        # — 9. A real AnkiConnect HTTP sync, then idempotent re-sync ————
        fake = FakeAnkiConnect()
        server, _thread, url = start_fake_ankiconnect(fake)
        try:
            text, is_error = client.call(
                "lesan_pipe_sync", {"db": str(db), "url": url, "deck": REAL_SYNC_DECK}
            )
            check(not is_error, f"real sync returned a tool error: {text[:2000]}")
            first = _notes_added(text)
            check(first > 0, f"real sync added no notes: {text[:2000]}")
            check(
                len(fake.notes) == first,
                f"server holds {len(fake.notes)} notes but CLI reported {first}",
            )
            check(
                REAL_SYNC_DECK in fake.decks,
                f"server never saw createDeck for {REAL_SYNC_DECK!r}",
            )
            transcript.step(
                "real AnkiConnect sync (HTTP, not --mock)",
                f"`lesan_pipe_sync` against a live AnkiConnect-shaped HTTP endpoint "
                f"at `{url}` added {first} notes to deck `{REAL_SYNC_DECK}`; the "
                f"server confirms {len(fake.notes)} notes stored.\n\n```\n"
                f"{Transcript.excerpt(text)}\n```",
            )

            text, is_error = client.call(
                "lesan_pipe_sync", {"db": str(db), "url": url, "deck": REAL_SYNC_DECK}
            )
            check(not is_error, f"re-sync returned a tool error: {text[:2000]}")
            second = _notes_added(text)
            check(second == 0, f"re-sync was not idempotent (added {second}): {text[:2000]}")
            check(
                len(fake.notes) == first,
                f"re-sync grew the server collection to {len(fake.notes)} notes",
            )
            transcript.step(
                "idempotent re-sync adds zero",
                f"Re-running the identical sync added {second} notes and the server "
                f"collection is unchanged at {len(fake.notes)}: content-keyed "
                f"duplicate detection holds end to end.\n\n```\n"
                f"{Transcript.excerpt(text)}\n```",
            )
        finally:
            server.shutdown()
            server.server_close()
    finally:
        client.close()


def _notes_added(text: str) -> int:
    for line in text.splitlines():
        if "notes added" in line:
            return int(line.strip().split()[0])
    raise AcceptanceFailure(f"sync output has no 'N notes added' line: {text[:2000]}")


if __name__ == "__main__":
    sys.exit(main())
