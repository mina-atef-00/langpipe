#!/usr/bin/env python3
"""CI gate: pyproject and plugin.json must agree on one release version.

Stdlib only — runs before (and without) the project's dev dependencies.

Checks:
  1. pyproject.toml [project] version equals hermes-plugin/plugin.json
     version. A drifted plugin manifest would publish a wheel whose
     version disagrees with the advertised plugin version.
  2. When running on a tag (GITHUB_REF_TYPE=tag, e.g. a GitHub Release),
     the tag name — with an optional leading 'v' stripped — must equal
     that same version, so a release can never publish the wrong number.

Usage:
  python3 .github/scripts/check_release_version.py [repo-root]
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([+-][0-9A-Za-z.-]+)?$")

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"ok: {msg}")


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()

    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    except FileNotFoundError:
        fail("pyproject.toml missing")
        pyproject = {}
    except tomllib.TOMLDecodeError as exc:
        fail(f"pyproject.toml is not valid TOML ({exc})")
        pyproject = {}
    dist_version = pyproject.get("project", {}).get("version")

    plugin_path = root / "hermes-plugin" / "plugin.json"
    try:
        plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"plugin manifest missing: {plugin_path}")
        plugin = {}
    except json.JSONDecodeError as exc:
        fail(f"plugin.json is not valid JSON ({exc})")
        plugin = {}
    plugin_version = plugin.get("version") if isinstance(plugin, dict) else None

    if not isinstance(dist_version, str) or not SEMVER_RE.match(dist_version):
        fail(f"pyproject [project] version must be semver, got {dist_version!r}")
    if not isinstance(plugin_version, str) or not SEMVER_RE.match(plugin_version):
        fail(f"plugin.json 'version' must be semver, got {plugin_version!r}")
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1

    if dist_version != plugin_version:
        fail(
            "version drift: pyproject.toml "
            f"({dist_version!r}) != hermes-plugin/plugin.json ({plugin_version!r})"
        )
    else:
        ok(f"versions agree ({dist_version!r})")

    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME", "").lstrip("v")
        if tag and SEMVER_RE.match(tag) and tag != dist_version:
            fail(f"tag v{tag} does not match release version {dist_version!r}")
        elif tag == dist_version:
            ok(f"tag matches version ({dist_version!r})")

    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("release version: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
