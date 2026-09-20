"""MCP stdio server tests: every tool call goes through the real CLI.

WHY this file exists: ``hermes-plugin/server/lesan_pipe_mcp.py`` promises two
things — the CLI owns every number (the server only formats subprocess
output) and failures are loud (a missing executable or a refused overwrite
comes back as a readable tool error, never a traceback or a cheerful empty
result). These tests pin both promises: the seven tools are driven in
dependency order against a temporary database, and the failure paths assert
on the documented message text.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = REPO_ROOT / "hermes-plugin" / "server" / "lesan_pipe_mcp.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("lesan_pipe_mcp_under_test", SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


srv = _load_server()


@pytest.fixture()
def hermetic_cli(monkeypatch: pytest.MonkeyPatch):
    """Hide PATH console scripts so resolution uses this checkout's package.

    WHY: ``_resolve_cli`` prefers a ``lesan_pipe`` binary on PATH, which may be
    a stale install from another checkout. Returning None from ``which``
    forces the documented fallback — the interpreter running these tests,
    which imports the worktree's ``lesan_pipe`` — so the tools exercise the
    code under test, not whatever happens to be installed.
    """
    monkeypatch.setattr(srv.shutil, "which", lambda _name: None)
    srv._CLI_COMMAND = None
    srv._CLI_FAILURE = None
    yield srv
    srv._CLI_COMMAND = None
    srv._CLI_FAILURE = None


def _call(server, name: str, arguments: dict, request_id: int = 1) -> dict:
    return server._handle(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


def _result_text(response: dict) -> tuple[str, bool]:
    assert "result" in response, f"expected a tool result, got: {response}"
    content = response["result"]["content"]
    assert len(content) == 1 and content[0]["type"] == "text"
    return content[0]["text"], response["result"].get("isError", False)


def test_all_seven_tools_end_to_end(hermetic_cli, tmp_path: Path) -> None:
    """Drive init -> plan -> generate -> cards -> review -> stats -> sync.

    WHY: this is the contract that the server forwards every tool to the
    real CLI and reports what the CLI printed. If a tool name, flag, or
    argument order drifts from ``src/lesan_pipe/cli.py``, this chain breaks.
    """
    server = hermetic_cli
    db = str(tmp_path / "mcp.db")

    text, failed = _result_text(_call(server, "lesan_pipe_init", {"db": db, "seed": 42}))
    assert not failed, text
    assert "Initialised learner" in text

    text, failed = _result_text(_call(server, "lesan_pipe_plan", {"db": db}))
    assert not failed, text
    assert "stage 1" in text

    text, failed = _result_text(
        _call(server, "lesan_pipe_generate", {"db": db, "stage": 1, "seed": 42})
    )
    assert not failed, text
    assert "Generated" in text and "stage 1" in text

    text, failed = _result_text(_call(server, "lesan_pipe_cards", {"db": db}))
    assert not failed, text
    assert "[1]" in text  # the generate step stored cards starting at id 1

    text, failed = _result_text(
        _call(server, "lesan_pipe_review", {"db": db, "card_id": 1, "grade": 4})
    )
    assert not failed, text
    assert "graded 4" in text

    text, failed = _result_text(_call(server, "lesan_pipe_stats", {"db": db}))
    assert not failed, text
    assert "retention rate" in text  # one grade-4 review is on the record now

    text, failed = _result_text(
        _call(server, "lesan_pipe_sync", {"db": db, "mock": True})
    )
    assert not failed, text
    assert "notes added" in text


def test_init_refuses_overwrite_without_confirm(hermetic_cli, tmp_path: Path) -> None:
    """An existing database must survive an init call without explicit consent.

    WHY: ``lesan_pipe init`` deletes the database first, so the server gate
    (``confirm_overwrite``) is the only thing standing between a misclick
    and a lost learner. The refusal must arrive before any subprocess runs.
    """
    server = hermetic_cli
    db = tmp_path / "precious.db"
    db.write_text("do not delete me")

    text, failed = _result_text(_call(server, "lesan_pipe_init", {"db": str(db)}))
    assert failed
    assert "already exists" in text
    assert "confirm_overwrite" in text
    assert db.read_text() == "do not delete me"  # nothing ran

    text, failed = _result_text(
        _call(server, "lesan_pipe_init", {"db": str(db), "confirm_overwrite": True})
    )
    assert not failed, text
    assert "Initialised learner" in text


def test_plugin_data_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The writable data dir honours PLUGIN_DATA and falls back per host.

    WHY: the plugin host sandbox-writes to ``${PLUGIN_DATA}``; a server that
    ignored it would scatter databases across machines instead of the
    profile-scoped directory the host prepared.
    """
    monkeypatch.setenv("PLUGIN_DATA", "/tmp/profile-9")
    monkeypatch.delenv("HERMES_HOME", raising=False)
    assert srv._plugin_data() == Path("/tmp/profile-9")

    monkeypatch.delenv("PLUGIN_DATA")
    monkeypatch.setenv("HERMES_HOME", "/tmp/hermes-home")
    assert srv._plugin_data() == Path("/tmp/hermes-home/plugin-data/lesan_pipe")

    monkeypatch.delenv("HERMES_HOME")
    assert srv._plugin_data() == Path.home() / ".hermes" / "plugin-data" / "lesan_pipe"


def test_default_db_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A call without ``db`` uses LESAN_PIPE_DB, else lesan_pipe.db under PLUGIN_DATA.

    WHY: per-call ``db`` lets one host serve several learners, but the common
    single-learner case must land in a predictable file without every call
    repeating the path.
    """
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("LESAN_PIPE_DB", raising=False)
    assert srv._default_db() == str(tmp_path / "data" / "lesan_pipe.db")

    monkeypatch.setenv("LESAN_PIPE_DB", str(tmp_path / "custom.db"))
    assert srv._default_db() == str(tmp_path / "custom.db")
    assert srv._db_for({}) == str(tmp_path / "custom.db")
    assert srv._db_for({"db": "/tmp/explicit.db"}) == "/tmp/explicit.db"


def test_broken_install_is_documented_error_not_traceback(
    hermetic_cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no CLI anywhere, the tool returns the install guidance as an error.

    WHY: a plugin host with a broken install must show the learner how to
    fix it (install the CLI or set LESAN_PIPE_BIN), not a Python traceback.
    This is the evidence half of the task: the failure is a loud tool error.
    """
    server = hermetic_cli
    monkeypatch.setattr(server, "_console_script_candidates", lambda: [])
    monkeypatch.setattr(server, "_python_candidates", lambda: [])
    server._CLI_COMMAND = None
    server._CLI_FAILURE = None

    with pytest.raises(server.ToolError, match="lesan_pipe executable not found") as excinfo:
        server._resolve_cli()
    assert "LESAN_PIPE_BIN" in str(excinfo.value)

    response = _call(server, "lesan_pipe_plan", {"db": "/tmp/nowhere.db"})
    text, failed = _result_text(response)
    assert failed
    assert "lesan_pipe executable not found" in text
    assert "Traceback" not in text


def test_unknown_tool_lists_known_tools(hermetic_cli) -> None:
    """A misspelled tool name answers with the catalogue, not a KeyError page."""
    response = _call(hermetic_cli, "lesan_pipe_dance", {})
    assert response["error"]["code"] == hermetic_cli.INVALID_PARAMS
    assert "lesan_pipe_init" in response["error"]["message"]
    assert "Traceback" not in response["error"]["message"]


def test_missing_required_arg_is_error_not_traceback(hermetic_cli) -> None:
    """Review without a grade fails with a one-liner naming the argument."""
    response = _call(hermetic_cli, "lesan_pipe_review", {"card_id": 1})
    text, failed = _result_text(response)
    assert failed
    assert "missing required argument 'grade'" in text
    assert "Traceback" not in text


def test_handle_rejects_non_object_message(hermetic_cli) -> None:
    """Garbage on the wire is an INVALID_REQUEST error, never an exception."""
    response = hermetic_cli._handle("not a dict")
    assert response["error"]["code"] == hermetic_cli.INVALID_REQUEST
    assert "Traceback" not in response["error"]["message"]
