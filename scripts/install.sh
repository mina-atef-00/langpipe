#!/usr/bin/env sh
# One-command dev install for lesan_pipe.
#
# Installs the `lesan_pipe` CLI editable from this repo and links the Hermes
# plugin at this repo, so editing the checkout changes BOTH surfaces without
# reinstalling:
#
#   ./scripts/install.sh
#
# Do NOT `pip install lesan_pipe` / `pipx install lesan_pipe`: that name belongs
# to an unrelated project on PyPI and would install the wrong tool.
#
# The global CLI must ALWAYS install from the PRIMARY checkout, never from a
# git worktree: install.sh may itself live inside <repo>/.worktrees/<task-id>,
# and an editable install from there dies with ModuleNotFoundError the moment
# that worktree is pruned. Resolution below maps any worktree path back to the
# primary checkout via the common git dir.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_FALLBACK="$(cd "$SCRIPT_DIR/.." && pwd)"

# Print the primary checkout for a given path inside a repo/worktree.
# Falls back to the input dir when git is missing or this is not a git
# checkout (e.g. an sdist tarball).
primary_checkout() {
    _dir="$1"
    if command -v git >/dev/null 2>&1; then
        _common="$(git -C "$_dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
        if [ -n "${_common:-}" ]; then
            _primary="$(dirname "$_common")"
            if [ -f "$_primary/pyproject.toml" ]; then
                printf '%s\n' "$_primary"
                return 0
            fi
        fi
    fi
    printf '%s\n' "$_dir"
}

REPO="$(primary_checkout "$REPO_FALLBACK")"

if [ "${1:-}" = "--print-repo" ]; then
    # Dry run for tests: print the resolved install source without installing.
    printf '%s\n' "$REPO"
    exit 0
fi

if [ "$REPO" != "$REPO_FALLBACK" ]; then
    echo "note: resolved primary checkout $REPO (invoked from worktree $REPO_FALLBACK)" >&2
fi
# The link's directory name MUST equal plugin.json's `name` ("lesan-pipe"):
# Hermes Agent Plugins v1 rejects a plugin dir whose basename mismatches the
# manifest, so a wrong name leaves the plugin (and its MCP tools) silently
# unloaded. Drop any stale pre-fix link under the old underscore name first.
PLUGIN_LINK="${HOME}/.hermes/plugins/lesan-pipe"
rm -f "${HOME}/.hermes/plugins/lesan_pipe"

if command -v uv >/dev/null 2>&1; then
    (cd "$REPO" && uv tool install --editable . --force)
elif command -v pipx >/dev/null 2>&1; then
    pipx install --editable "$REPO" --force
else
    python3 -m pip install --user -e "$REPO"
fi

mkdir -p "$(dirname "$PLUGIN_LINK")"
ln -sfn "$REPO/hermes-plugin" "$PLUGIN_LINK"

if ! command -v lesan_pipe >/dev/null 2>&1; then
    echo "install finished but lesan_pipe is not on PATH" >&2
    exit 1
fi
lesan_pipe --help >/dev/null

echo "cli:    $(command -v lesan_pipe) (editable from $REPO)"
echo "plugin: $PLUGIN_LINK -> $(readlink "$PLUGIN_LINK")"
