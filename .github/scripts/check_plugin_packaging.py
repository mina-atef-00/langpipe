#!/usr/bin/env python3
"""CI gate for the Agent Plugins v1 package in hermes-plugin/.

Stdlib only — runs before (and without) the project's dev dependencies.

Checks:
  1. plugin.json carries the required Agent Plugins v1 manifest fields
     with sane types (name, semver version, description, license).
  2. mcp.json carries a non-empty mcpServers map; every server entry has a
     usable stdio/sse/streamable-http shape and every ${PLUGIN_ROOT}-relative
     file it references exists on disk.
  3. Manifests agree with each other and the skill: the mcp server key, the
     skill directory, and the SKILL.md frontmatter name all equal the plugin
     name; the server module referenced by mcp.json exists.
  4. SKILL.md single-source: every SKILL.md file tracked under the repo root
     must be byte-identical to the canonical
     hermes-plugin/skills/<name>/SKILL.md. A second copy that drifts fails
     the build; the fix is to re-sync it from the canonical source, never to
     edit a copy in place.

Usage:
  python3 .github/scripts/check_plugin_packaging.py [repo-root]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([+-][0-9A-Za-z.-]+)?$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"ok: {msg}")


def load_json(path: Path, label: str) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"{label} missing: {path}")
        return None
    except json.JSONDecodeError as exc:
        fail(f"{label} is not valid JSON ({path}: {exc})")
        return None
    if not isinstance(data, dict):
        fail(f"{label} must be a JSON object: {path}")
        return None
    return data


def check_plugin_manifest(plugin_dir: Path) -> dict | None:
    manifest = load_json(plugin_dir / "plugin.json", "plugin manifest")
    if manifest is None:
        return None
    name = manifest.get("name")
    version = manifest.get("version")
    description = manifest.get("description")
    license_ = manifest.get("license")
    if not isinstance(name, str) or not NAME_RE.match(name):
        fail("plugin.json: 'name' must be a lowercase slug ([a-z0-9_-])")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        fail("plugin.json: 'version' must be semver (X.Y.Z)")
    if not isinstance(description, str) or not description.strip():
        fail("plugin.json: 'description' must be a non-empty string")
    if not isinstance(license_, str) or not license_.strip():
        fail("plugin.json: 'license' must be a non-empty string")
    if not FAILURES:
        ok(f"plugin.json valid (name={name!r} version={version!r})")
    return manifest


def check_mcp_manifest(plugin_dir: Path) -> dict | None:
    manifest = load_json(plugin_dir / "mcp.json", "mcp manifest")
    if manifest is None:
        return None
    servers = manifest.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        fail("mcp.json: 'mcpServers' must be a non-empty object")
        return manifest
    for server_name, entry in servers.items():
        if not isinstance(entry, dict):
            fail(f"mcp.json: server {server_name!r} must be an object")
            continue
        kind = entry.get("type", "stdio")
        if kind not in ("stdio", "sse", "streamable-http"):
            fail(f"mcp.json: server {server_name!r} has unknown type {kind!r}")
        if kind == "stdio":
            command = entry.get("command")
            args = entry.get("args", [])
            if not isinstance(command, str) or not command.strip():
                fail(f"mcp.json: server {server_name!r} needs a 'command'")
            if not isinstance(args, list) or not all(
                isinstance(a, str) for a in args
            ):
                fail(f"mcp.json: server {server_name!r} 'args' must be strings")
            for arg in args if isinstance(args, list) else []:
                if not isinstance(arg, str):
                    continue
                resolved = arg.replace("${PLUGIN_ROOT}", str(plugin_dir))
                # Only file-like args (ending in .py) that resolve inside the
                # package are existence-checked; opaque flags are skipped.
                candidate = Path(resolved)
                if (
                    "${" not in resolved
                    and candidate.suffix == ".py"
                    and not candidate.is_file()
                ):
                    fail(
                        f"mcp.json: server {server_name!r} references "
                        f"missing file {arg!r}"
                    )
    if not any(f.startswith("mcp.json") for f in FAILURES):
        ok(f"mcp.json valid (servers={sorted(servers)!r})")
    return manifest


def check_consistency(
    plugin_dir: Path, plugin: dict | None, mcp: dict | None
) -> Path | None:
    if plugin is None or mcp is None:
        return None
    name = plugin.get("name")
    servers = mcp.get("mcpServers")
    if not isinstance(name, str) or not isinstance(servers, dict):
        return None
    if name not in servers:
        fail(
            f"manifest drift: plugin.json name {name!r} has no matching "
            f"mcp.json server (have {sorted(servers)!r})"
        )
    skill_dir = plugin_dir / "skills" / name
    canonical = skill_dir / "SKILL.md"
    if not canonical.is_file():
        fail(f"manifest drift: skill file missing: {canonical}")
        return None
    frontmatter = canonical.read_text(encoding="utf-8")
    match = FRONTMATTER_NAME_RE.search(frontmatter)
    skill_name = match.group(1).strip().strip("'\"") if match else None
    if skill_name != name:
        fail(
            f"manifest drift: SKILL.md frontmatter name {skill_name!r} "
            f"!= plugin name {name!r}"
        )
    else:
        ok(f"manifests agree on name {name!r} (plugin/mcp/skill)")
    return canonical


def check_skill_single_source(root: Path, canonical: Path) -> None:
    copies = sorted(
        p
        for p in root.rglob("SKILL.md")
        if ".git" not in p.parts and p.is_file()
    )
    if canonical not in copies:
        fail(f"canonical skill not found by scan: {canonical}")
        return
    digest = hashlib.sha256(canonical.read_bytes()).hexdigest()
    ok(f"canonical {canonical.relative_to(root)} sha256={digest[:12]}")
    drifted = [
        p for p in copies if hashlib.sha256(p.read_bytes()).hexdigest() != digest
    ]
    for path in drifted:
        fail(
            f"SKILL.md drift: {path.relative_to(root)} differs from "
            f"{canonical.relative_to(root)} — re-sync the copy from the "
            "canonical source"
        )
    if not drifted:
        ok(f"single-source: {len(copies)} SKILL.md copie(s) identical")


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    plugin_dir = root / "hermes-plugin"
    if not plugin_dir.is_dir():
        fail(f"plugin package missing: {plugin_dir}")
        print(f"{len(FAILURES)} failure(s)")
        return 1
    plugin = check_plugin_manifest(plugin_dir)
    mcp = check_mcp_manifest(plugin_dir)
    canonical = check_consistency(plugin_dir, plugin, mcp)
    if canonical is not None:
        check_skill_single_source(root, canonical)
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("plugin packaging: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
