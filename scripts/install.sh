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
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_LINK="${HOME}/.hermes/plugins/lesan_pipe"

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
