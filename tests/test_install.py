"""Regression: install.sh must install the global CLI from the PRIMARY checkout.

WHY: an editable install from <repo>/.worktrees/<task-id> points the global
`lesan_pipe` CLI at a throwaway dir. The moment that worktree is pruned the
CLI dies with ModuleNotFoundError. The resolver must therefore map any
worktree path back to the primary checkout so the CLI survives cleanup.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)


def test_install_script_resolves_via_common_git_dir() -> None:
    content = INSTALL_SH.read_text()
    # The fix must derive the primary checkout from the common git dir...
    assert "git-common-dir" in content
    # ...and document why a worktree source is forbidden.
    assert ".worktrees" in content


def test_print_repo_from_this_checkout_is_not_a_worktree() -> None:
    result = _run(["sh", str(INSTALL_SH), "--print-repo"])
    assert result.returncode == 0, result.stderr
    resolved = Path(result.stdout.strip())
    assert (resolved / "pyproject.toml").is_file()
    assert "/.worktrees/" not in str(resolved)


def test_print_repo_from_worktree_resolves_to_primary(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git is not None, "git is required for this regression test"
    primary = tmp_path / "primary"
    (primary / "scripts").mkdir(parents=True)
    (primary / "pyproject.toml").write_text('[project]\nname = "lesan_pipe"\n')
    shutil.copyfile(INSTALL_SH, primary / "scripts" / "install.sh")

    assert _run([git, "init"], cwd=primary).returncode == 0
    assert _run([git, "add", "-A"], cwd=primary).returncode == 0
    commit = _run(
        [git, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=primary,
    )
    assert commit.returncode == 0, commit.stderr

    wt = tmp_path / "wt"
    assert _run([git, "worktree", "add", str(wt)], cwd=primary).returncode == 0
    wt_install = wt / "scripts" / "install.sh"
    assert wt_install.is_file(), "worktree must contain the install script"

    result = _run(["sh", str(wt_install), "--print-repo"], cwd=wt)
    assert result.returncode == 0, result.stderr
    resolved = result.stdout.strip()
    assert Path(resolved) == primary
    assert "/.worktrees/" not in resolved
