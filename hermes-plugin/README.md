# langpipe — Agent Plugins v1 package

Portable plugin package for [langpipe](https://github.com/mina-atef-00/langpipe), a
language-learning pipeline: a guided learner interview, a deterministic curriculum and
SM-2 scheduler, graded card generation, idempotent Anki sync, and retention analytics.

This directory is the catalog-ready package. It is self-contained: everything the
plugin loads lives inside `hermes-plugin/`, and the host installs it from
`repo#hermes-plugin`.

```
hermes-plugin/
├── plugin.json                 # Agent Plugins v1 manifest
├── mcp.json                    # stdio MCP server entry
├── skills/langpipe/SKILL.md    # the learner-interview skill
├── server/langpipe_mcp.py      # stdio MCP server (stdlib only)
└── README.md
```

## What it gives the agent

| Surface | Contents |
|---|---|
| Skill `langpipe` | The learner interview, preset selection, grounding rules, and the CLI workflow. |
| MCP server `langpipe` | Seven tools that drive the real CLI: `langpipe_init`, `langpipe_plan`, `langpipe_generate`, `langpipe_cards`, `langpipe_review`, `langpipe_stats`, `langpipe_sync`. |

The server is a thin bridge. It builds CLI arguments, runs the console script, and
returns what the script printed. It never reimplements SM-2, the analytics, or the
idempotency ledger — langpipe's doctrine is that the code owns every number that
appears in a report, and this package keeps that boundary.

Failures stay loud: a non-zero exit, an unreachable AnkiConnect, or a missing
executable comes back as an MCP tool error carrying the real stderr, so a failed sync
can never be read as an empty success. `langpipe_init` refuses to overwrite an
existing database unless the call passes `confirm_overwrite: true`.

## Prerequisites

1. **The langpipe CLI itself.** The package ships the wrapper, not the pipeline.
   Any one of these works:
   - `pipx install langpipe` (isolated console script on `PATH`);
   - the repository virtualenv next to this package (`../.venv`), used automatically;
   - a Python environment where `import langpipe.cli` succeeds — the server finds it
     and invokes the CLI module directly.
   If none is found, every tool call fails with the list of paths that were tried;
   set `LANGPIPE_BIN` to a langpipe console script to point at one explicitly.

2. **Anki + AnkiConnect, for `langpipe_sync` only.** Anki must be running with the
   [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed, because
   `sync` posts to the add-on's HTTP endpoint (default `http://127.0.0.1:8765`). Every
   other tool works without Anki. When the endpoint is unreachable the CLI exits
   non-zero and the tool call reports that failure; pass `mock: true` to exercise the
   in-memory backend instead, which touches no Anki install.

3. **Python 3.8+** — the server imports only the standard library.

## Data and database path

`${PLUGIN_DATA}` is the package's writable, profile-scoped directory, and it is also
the server's working directory. The review database defaults to
`${PLUGIN_DATA}/langpipe.db`, so two profiles never share one learner. Override per
call with the `db` argument, or for the whole server by exporting `LANGPIPE_DB`.
Nothing is written into the read-only package directory.

Two more environment variables are honoured:

| Variable | Effect |
|---|---|
| `LANGPIPE_BIN` | Explicit path to the langpipe console script. |
| `LANGPIPE_TIMEOUT` | Per-call timeout in seconds (default 120; `langpipe_sync` uses 300). |

## Running it by hand

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 server/langpipe_mcp.py
```

Responses are newline-delimited JSON-RPC on stdout; the server's own diagnostics go to
stderr, so stdout carries nothing but protocol traffic.

## License

MIT, same as langpipe.
