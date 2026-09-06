"""Deterministic completion assurance without mutable local authority.

Completion assurance must not trust evidence that repository code running under
the same operating-system identity can rewrite. SessionStart records no
authoritative completion snapshot, and local remote-tracking refs are not used as
remote authority. At Stop, the harness re-evaluates repository posture, obtains
the checked default branch head directly from GitHub, and compares it with the
current local Git state. Otherwise the normal delivery completion gate runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
POSTURE_DIR = ROOT / "reference" / "posture"
if str(POSTURE_DIR) not in sys.path:
    sys.path.insert(0, str(POSTURE_DIR))

from checker import check_repository_posture  # noqa: E402


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Run a bounded local Git query used by completion assurance."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=5, check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout.strip(), None


def _github_branch_head(cwd: Path, repository: str, branch: str) -> tuple[str | None, str | None]:
    """Return the authoritative GitHub branch-head SHA for a checked repository.

    The query goes directly to GitHub through ``gh api`` instead of trusting the
    local ``refs/remotes/origin/*`` namespace, which repository code running as
    the same user can rewrite. Malformed or unavailable responses fail closed.
    """
    endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='')}"
    try:
        result = subprocess.run(
            ["gh", "api", endpoint], cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15, check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    try:
        value = json.loads(result.stdout)
        sha = value.get("object", {}).get("sha") if isinstance(value, dict) else None
    except Exception as exc:
        return None, f"invalid GitHub branch-ref JSON: {exc}"
    if not isinstance(sha, str) or not sha:
        return None, "GitHub branch-ref response does not contain object.sha"
    return sha, None


def capture_session_start(raw: dict[str, Any]) -> str:
    """Return completion context without persisting authoritative session state.

    The function intentionally does not write a baseline file. Repository code
    may execute under the same operating-system identity as hooks, so a writable
    local snapshot cannot serve as independent assurance evidence.
    """
    del raw
    return "Completion assurance will re-evaluate authoritative repository state at Stop."


def _clean_checked_default_branch(cwd: Path) -> tuple[bool, str]:
    """Determine whether current Git state equals the checked GitHub default head.

    The decision freshly evaluates repository posture, requires the current
    branch to be the checked default branch with a clean worktree, and compares
    local ``HEAD`` with the branch-head SHA returned directly by GitHub. Failure
    to establish any evidence returns false so the full completion gate remains
    in force.
    """
    try:
        report = check_repository_posture(cwd)
    except Exception as exc:
        return False, f"posture evaluation failed: {exc}"
    if report.state == "BLOCKED" or not report.repository or not report.default_branch:
        return False, report.summary()

    branch, error = _run_git(cwd, ["branch", "--show-current"])
    if error or not branch or branch != report.default_branch:
        return False, error or "current branch is not the checked default branch"

    status, error = _run_git(cwd, ["status", "--porcelain=v1", "--untracked-files=all"])
    if error or status:
        return False, error or "worktree is not clean"

    head, error = _run_git(cwd, ["rev-parse", "HEAD"])
    if error or not head:
        return False, error or "HEAD is unavailable"
    remote_head, error = _github_branch_head(cwd, report.repository, report.default_branch)
    if error or not remote_head:
        return False, error or "GitHub default branch head is unavailable"
    if head != remote_head:
        return False, "local default branch differs from the authoritative GitHub default branch"
    return True, f"clean default branch {report.default_branch} matches GitHub branch head {remote_head}"


def _run_completion_gate(cwd: Path) -> tuple[bool, str]:
    """Run the repository delivery completion gate and fail closed on errors."""
    gate = ROOT / "reference" / "scripts" / "completion_gate.sh"
    try:
        completed = subprocess.run(
            ["bash", str(gate)], cwd=cwd, env=os.environ.copy(), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=int(os.environ.get("AGENT_HARNESS_COMPLETION_TIMEOUT", "120")),
            check=False,
        )
    except Exception as exc:
        return False, f"completion gate failed closed: {exc}"
    output = completed.stdout.strip()
    return completed.returncode == 0, output or f"completion gate exited {completed.returncode}"


def completion_check(raw: dict[str, Any]) -> tuple[bool, str]:
    """Accept only authoritative clean default state or a passing delivery gate.

    A clean local checked default branch whose ``HEAD`` exactly matches the
    branch-head SHA returned directly by GitHub is sufficient evidence that no
    local repository delivery is pending. Every other or unverifiable state runs
    the full deterministic completion gate. This claim concerns repository state
    only and does not imply absence of external side effects during the session.
    """
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    read_only, reason = _clean_checked_default_branch(cwd)
    if read_only:
        return True, f"completion assurance: read-only repository state; {reason}"
    ok, gate_reason = _run_completion_gate(cwd)
    return ok, gate_reason
