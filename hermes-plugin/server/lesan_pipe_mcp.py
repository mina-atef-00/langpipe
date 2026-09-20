#!/usr/bin/env python3
"""MCP stdio server for lesan_pipe.

Speaks newline-delimited JSON-RPC 2.0 over stdin/stdout (the MCP stdio
transport) and forwards every tool call to the real ``lesan_pipe`` console
script as a subprocess. Standard library only: no SDK, no third-party
dependency, so the server starts even in the interpreter the plugin is
handed.

Two rules this file will not break:

* The CLI owns every number. Nothing here computes an SM-2 interval, a
  retention rate or a due forecast; the server formats output it did not
  derive.
* Failures are loud. A non-zero exit, an unreachable AnkiConnect, or a
  missing lesan_pipe executable comes back as an MCP tool error carrying the
  real stderr, so a failure can never be read as a cheerful empty result.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "lesan_pipe"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
DEFAULT_TIMEOUT_SECONDS = 120.0
SYNC_TIMEOUT_SECONDS = 300.0
INPROCESS_RUNNER = "from lesan_pipe.cli import app; app()"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


class ToolError(Exception):
    """A tool call that failed for a reason the caller has to see verbatim."""


# ── Locations ────────────────────────────────────────────────────────────────


def _plugin_root() -> Path:
    """The package root: ``${PLUGIN_ROOT}`` when the host set it, else this file's parent."""
    value = os.environ.get("PLUGIN_ROOT")
    return Path(value) if value else PACKAGE_ROOT


def _plugin_data() -> Path:
    """Writable, profile-scoped data directory: ``${PLUGIN_DATA}``, else the Hermes default."""
    value = os.environ.get("PLUGIN_DATA")
    if value:
        return Path(value).expanduser()
    home = os.environ.get("HERMES_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".hermes"
    return base / "plugin-data" / SERVER_NAME


def _default_db() -> str:
    """Database path used when a call omits ``db``: overridable, never guessed per call."""
    override = os.environ.get("LESAN_PIPE_DB")
    return override if override else str(_plugin_data() / "lesan_pipe.db")


# ── Locating the lesan_pipe CLI ────────────────────────────────────────────────


def _console_script_candidates() -> list:
    candidates = []
    override = os.environ.get("LESAN_PIPE_BIN")
    if override:
        candidates.append(Path(override).expanduser())
    on_path = shutil.which("lesan_pipe")
    if on_path:
        candidates.append(Path(on_path))
    root = _plugin_root()
    candidates.append(root.parent / ".venv" / "bin" / "lesan_pipe")
    candidates.append(root / ".venv" / "bin" / "lesan_pipe")
    return candidates


def _python_candidates() -> list:
    candidates = []
    root = _plugin_root()
    for python in (root.parent / ".venv" / "bin" / "python3",
                   root.parent / ".venv" / "bin" / "python",
                   Path(sys.executable) if sys.executable else None):
        if python is not None and str(python) not in candidates:
            candidates.append(str(python))
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)
    return candidates


def _imports_lesan_pipe(python: str) -> bool:
    try:
        completed = subprocess.run(
            [python, "-c", "import lesan_pipe.cli"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


_CLI_COMMAND = None
_CLI_FAILURE = None


def _resolve_cli() -> list:
    """Return the argv prefix that runs lesan_pipe, resolved once and cached.

    Order: ``LESAN_PIPE_BIN``, ``lesan_pipe`` on PATH, the repository virtualenv
    beside this package, then any interpreter that can import the package
    (the CLI module is invoked directly in that case). Failure is cached too,
    so a missing CLI costs one probe, not one per tool call.
    """
    global _CLI_COMMAND, _CLI_FAILURE
    if _CLI_COMMAND is not None:
        return list(_CLI_COMMAND)
    if _CLI_FAILURE is not None:
        raise ToolError(_CLI_FAILURE)
    for candidate in _console_script_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            _CLI_COMMAND = [str(candidate)]
            return list(_CLI_COMMAND)
    for python in _python_candidates():
        if _imports_lesan_pipe(python):
            _CLI_COMMAND = [python, "-c", INPROCESS_RUNNER]
            return list(_CLI_COMMAND)
    tried = ", ".join(str(path) for path in _console_script_candidates())
    _CLI_FAILURE = (
        "lesan_pipe executable not found, so no lesan_pipe command can run. Tried: "
        f"{tried}; then the interpreters {', '.join(_python_candidates())} for an importable "
        "lesan_pipe package. Install the CLI (for example `pipx install lesan_pipe`), activate the "
        "repository virtualenv, or set LESAN_PIPE_BIN to the lesan_pipe console script."
    )
    raise ToolError(_CLI_FAILURE)


# ── Running the CLI ──────────────────────────────────────────────────────────


def _timeout(seconds: float | None = None) -> float:
    if seconds is not None:
        return seconds
    configured = os.environ.get("LESAN_PIPE_TIMEOUT")
    if configured:
        try:
            return max(1.0, float(configured))
        except ValueError:
            return DEFAULT_TIMEOUT_SECONDS
    return DEFAULT_TIMEOUT_SECONDS


def _run(argv: list, timeout: float | None = None) -> tuple:
    """Run lesan_pipe with *argv*; return ``(stdout, stderr)``. Any failure raises ToolError."""
    command = _resolve_cli() + [str(part) for part in argv]
    limit = _timeout(timeout)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        raise ToolError(
            f"lesan_pipe {' '.join(str(p) for p in argv)} timed out after {limit:.0f}s and was "
            "killed. Raise LESAN_PIPE_TIMEOUT if the operation legitimately needs longer."
        ) from None
    except OSError as exc:
        raise ToolError(
            f"could not start lesan_pipe ({command[0]}): {exc}. Set LESAN_PIPE_BIN to a working "
            "lesan_pipe console script."
        ) from exc
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        details = "\n".join(part for part in (stdout, stderr) if part)
        raise ToolError(
            f"lesan_pipe {' '.join(str(p) for p in argv)} exited {completed.returncode}."
            + (f"\n{details}" if details else "\n(no output on stdout or stderr)")
        )
    if stdout:
        return stdout, stderr
    empty = f"(lesan_pipe exited 0 with no output: {' '.join(str(p) for p in argv)})"
    return empty, stderr


def _flag(argv: list, name: str, value) -> None:
    if value is not None:
        argv.extend([name, str(value)])


def _db_for(args: dict) -> str:
    requested = args.get("db")
    return str(requested) if requested else _default_db()


def _require(args: dict, key: str) -> object:
    if key not in args or args[key] is None:
        raise ToolError(f"missing required argument '{key}'")
    return args[key]


# ── Tool implementations (thin argv builders over the real CLI) ──────────────


def _tool_init(args: dict) -> tuple:
    db = _db_for(args)
    confirm = bool(args.get("confirm_overwrite"))
    if Path(db).exists() and not confirm:
        raise ToolError(
            f"a lesan_pipe database already exists at {db}, and `lesan_pipe init` deletes it. "
            "Nothing was run. Call lesan_pipe_init again with "
            "confirm_overwrite=true to accept the loss, or pass a different db path."
        )
    argv = ["init", "--db", db]
    if confirm:
        argv.append("--force")
    for option in ("name", "lang", "pack", "seed", "daily"):
        _flag(argv, f"--{option}", args.get(option))
    return _run(argv)


def _tool_plan(args: dict) -> tuple:
    return _run(["plan", "--db", _db_for(args)])


def _tool_generate(args: dict) -> tuple:
    argv = ["generate", "--db", _db_for(args)]
    for option in ("stage", "seed", "count", "pack"):
        _flag(argv, f"--{option}", args.get(option))
    return _run(argv)


def _tool_cards(args: dict) -> tuple:
    argv = ["cards", "--db", _db_for(args)]
    _flag(argv, "--stage", args.get("stage"))
    return _run(argv)


def _tool_review(args: dict) -> tuple:
    card_id = _require(args, "card_id")
    grade = _require(args, "grade")
    argv = ["review", str(card_id), "--grade", str(grade), "--db", _db_for(args)]
    return _run(argv)


def _tool_stats(args: dict) -> tuple:
    return _run(["stats", "--db", _db_for(args)])


def _tool_sync(args: dict) -> tuple:
    argv = ["sync", "--db", _db_for(args)]
    for option in ("deck", "stage", "url"):
        _flag(argv, f"--{option}", args.get(option))
    if args.get("mock"):
        argv.append("--mock")
    return _run(argv, timeout=SYNC_TIMEOUT_SECONDS)


def _db_property() -> dict:
    return {
        "type": "string",
        "description": (
            "SQLite database path. Defaults to lesan_pipe.db inside the plugin data directory "
            f"({_plugin_data()}); override it per call for another learner or profile."
        ),
    }


TOOLS = (
    {
        "name": "lesan_pipe_init",
        "description": (
            "Create a fresh learner, curriculum and database from a language pack. "
            "Destructive: an existing database at the same path is deleted first, "
            "so pass confirm_overwrite=true only after the learner agreed to lose it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Learner name."},
                "lang": {
                    "type": "string",
                    "description": "Target language code (ISO 639-1), e.g. 'es'.",
                },
                "pack": {
                    "type": "string",
                    "description": (
                        "Path to a language pack JSON file. "
                        "Omit to use the bundled demo pack."
                    ),
                },
                "seed": {"type": "integer", "description": "Seed for deterministic generation."},
                "daily": {"type": "integer", "description": "New cards per day target."},
                "confirm_overwrite": {
                    "type": "boolean",
                    "description": "Must be true to replace an existing database at db.",
                },
                "db": _db_property(),
            },
        },
        "handler": _tool_init,
    },
    {
        "name": "lesan_pipe_plan",
        "description": "Print the phased curriculum with per-stage vocabulary and grammar targets.",
        "inputSchema": {"type": "object", "properties": {"db": _db_property()}},
        "handler": _tool_plan,
    },
    {
        "name": "lesan_pipe_generate",
        "description": "Generate practice cards for one curriculum stage from the language pack.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stage": {"type": "integer", "description": "Curriculum stage (1-based)."},
                "seed": {"type": "integer", "description": "Seed for deterministic generation."},
                "count": {"type": "integer", "description": "Cap on cards (0 = all)."},
                "pack": {"type": "string", "description": "Override the language pack path."},
                "db": _db_property(),
            },
        },
        "handler": _tool_generate,
    },
    {
        "name": "lesan_pipe_cards",
        "description": "List cards stored in the database, optionally filtered by stage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stage": {"type": "integer", "description": "Filter by stage (0 = all)."},
                "db": _db_property(),
            },
        },
        "handler": _tool_cards,
    },
    {
        "name": "lesan_pipe_review",
        "description": (
            "Record one review of a card and reschedule it with SM-2. The CLI owns the interval "
            "and ease arithmetic; the tool only reports what it printed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer", "description": "Card ID to review."},
                "grade": {
                    "type": "integer",
                    "description": "Recall grade 0-5 (0 blackout, 5 perfect).",
                },
                "db": _db_property(),
            },
            "required": ["card_id", "grade"],
        },
        "handler": _tool_review,
    },
    {
        "name": "lesan_pipe_stats",
        "description": (
            "Print the analytics report (retention, lapses, due forecast), all derived from the "
            "review-event log by the CLI."
        ),
        "inputSchema": {"type": "object", "properties": {"db": _db_property()}},
        "handler": _tool_stats,
    },
    {
        "name": "lesan_pipe_sync",
        "description": (
            "Export cards to Anki through AnkiConnect. Requires Anki running with the AnkiConnect "
            "add-on; an unreachable endpoint is reported as a tool error, never as a silent "
            "success. Re-running is safe: sync is content-key idempotent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string", "description": "Anki deck name (default 'lesan_pipe')."},
                "stage": {"type": "integer", "description": "Only export this stage (0 = all)."},
                "url": {"type": "string", "description": "AnkiConnect base URL (default http://127.0.0.1:8765)."},
                "mock": {
                    "type": "boolean",
                    "description": "Use the in-memory mock backend instead of Anki.",
                },
                "db": _db_property(),
            },
        },
        "handler": _tool_sync,
    },
)

_TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


# ── JSON-RPC plumbing ────────────────────────────────────────────────────────


def _write(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def _ok(request_id, result: dict) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id, code: int, message: str) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _tool_text(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _negotiate(params: dict) -> str:
    requested = params.get("protocolVersion")
    return requested if requested in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION


def _handle(message: dict):
    """Return the response payload, or None for a notification."""
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": INVALID_REQUEST, "message": "message must be a JSON object"}}
    method = message.get("method")
    if not isinstance(method, str) or not method:
        return {"jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": INVALID_REQUEST, "message": "missing 'method'"}}
    if "id" not in message:
        _log(f"{SERVER_NAME}: notification '{method}' ignored")
        return None
    request_id = message.get("id")
    params = message.get("params")
    params = params if isinstance(params, dict) else {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": _negotiate(params),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        keys = ("name", "description", "inputSchema")
        listed = [{key: tool[key] for key in keys} for tool in TOOLS]
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": listed}}
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in _TOOLS_BY_NAME:
            known = ", ".join(tool["name"] for tool in TOOLS)
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": INVALID_PARAMS,
                              "message": f"unknown tool {name!r}; known tools: {known}"}}
        arguments = params.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        try:
            stdout, stderr = _TOOLS_BY_NAME[name]["handler"](arguments)
        except ToolError as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": _tool_text(str(exc), True)}
        except Exception as exc:  # surfaced, never swallowed: an unknown failure is still a failure
            detail = f"lesan_pipe tool {name} raised {type(exc).__name__}: {exc}"
            return {"jsonrpc": "2.0", "id": request_id,
                    "result": _tool_text(detail, True)}
        text = stdout if not stderr else f"{stdout}\n\n{stderr}"
        return {"jsonrpc": "2.0", "id": request_id, "result": _tool_text(text)}

    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": METHOD_NOT_FOUND, "message": f"unsupported method {method!r}"}}


def main() -> int:
    _log(f"{SERVER_NAME} MCP server {SERVER_VERSION} ready (data dir: {_plugin_data()})")
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _write({"jsonrpc": "2.0", "id": None,
                    "error": {"code": PARSE_ERROR, "message": f"invalid JSON: {exc}"}})
            continue
        if isinstance(message, list):
            _write({"jsonrpc": "2.0", "id": None,
                    "error": {"code": INVALID_REQUEST,
                              "message": "batch requests are not supported"}})
            continue
        response = _handle(message)
        if response is not None:
            _write(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
