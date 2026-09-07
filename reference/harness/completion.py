"""Deterministic completion assurance without mutable local authority.

S5 does not trust a SessionStart snapshot or local remote-tracking references as
completion authority. At Stop it re-evaluates repository posture, reads the
checked default-branch head directly from GitHub, and treats a clean READY default
branch whose local HEAD equals that authoritative GitHub head as a verified
no-change repository state. That state is not, by itself, proof that the task may
finish without repository changes; callers must obtain requirement-side agreement
before accepting the no-change path. Every other or unverifiable state runs the
normal deterministic completion gate.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

from reference.posture.checker import check_repository_posture

ROOT = Path(__file__).resolve().parents[2]


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Run one bounded local Git query used by completion assurance."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout.strip(), None


def _github_branch_head(
    cwd: Path, repository: str, branch: str
) -> tuple[str | None, str | None]:
    """Return the checked repository's authoritative GitHub branch-head SHA."""
    endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='')}"
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
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
    """Return context without persisting authoritative completion state."""
    del raw
    return "Completion assurance will re-evaluate authoritative repository state at Stop."


def _clean_checked_default_branch(cwd: Path) -> tuple[bool, str]:
    """Return whether current state is a verified no-change repository state.

    The state check requires a freshly evaluated ``READY`` posture, the checked
    default branch, a completely clean worktree including untracked files, and an
    exact local-HEAD match with the branch head read directly from GitHub. It does
    not establish that the task requirement permits completion without repository
    changes. Any missing or weaker evidence returns false and leaves the normal
    completion gate in force.
    """
    try:
        report = check_repository_posture(cwd)
    except Exception as exc:
        return False, f"posture evaluation failed: {exc}"
    if report.state != "READY" or not report.repository or not report.default_branch:
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
    return True, f"clean READY default branch {report.default_branch} matches GitHub branch head {remote_head}"


def _run_completion_gate(cwd: Path) -> tuple[bool, str]:
    """Run the deterministic repository delivery gate and fail closed on errors."""
    gate = ROOT / "reference" / "scripts" / "completion_gate.sh"
    try:
        completed = subprocess.run(
            ["bash", str(gate)],
            cwd=cwd,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(os.environ.get("AGENT_HARNESS_COMPLETION_TIMEOUT", "120")),
            check=False,
        )
    except Exception as exc:
        return False, f"completion gate failed closed: {exc}"
    output = completed.stdout.strip()
    return completed.returncode == 0, output or f"completion gate exited {completed.returncode}"


def completion_check(raw: dict[str, Any]) -> tuple[bool, str]:
    """Require agreement for no-change completion or a passing full delivery gate.

    A verified clean default-branch state proves only that no repository change
    remains. It does not prove that completing without a change satisfies the task
    requirement. Until a caller supplies requirement-side agreement, S5 rejects
    that shortcut with an actionable reason so the vendor adapter can ask the
    request source rather than silently accepting an ambiguous completion.

    This guarantee is limited to repository-delivery state. It does not establish
    that the session produced no external side effects.
    """
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    no_change_state, reason = _clean_checked_default_branch(cwd)
    if no_change_state:
        return False, (
            "completion assurance requires request-source agreement before "
            f"accepting a no-change repository completion; {reason}"
        )
    ok, gate_reason = _run_completion_gate(cwd)
    return ok, gate_reason
