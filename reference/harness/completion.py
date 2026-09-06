"""Deterministic completion assurance without mutable session authority.

Completion assurance must not trust state that repository code running under the
same operating-system identity can rewrite. SessionStart therefore records no
authoritative completion snapshot. At Stop, the harness re-evaluates repository
posture and current Git state. A clean default branch exactly equal to the
checked remote default branch is accepted as a read-only repository state;
otherwise the normal delivery completion gate runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
POSTURE_DIR = ROOT / "reference" / "posture"
if str(POSTURE_DIR) not in sys.path:
    sys.path.insert(0, str(POSTURE_DIR))

from checker import check_repository_posture  # noqa: E402


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Run a bounded Git query used by completion assurance."""
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


def capture_session_start(raw: dict[str, Any]) -> str:
    """Return completion context without persisting authoritative session state.

    The function intentionally does not write a baseline file. Repository code
    may execute under the same operating-system identity as hooks, so a writable
    local snapshot cannot serve as independent assurance evidence.
    """
    del raw
    return "Completion assurance will re-evaluate authoritative repository state at Stop."


def _clean_checked_default_branch(cwd: Path) -> tuple[bool, str]:
    """Determine whether current Git state is a clean checked default branch.

    The decision uses a fresh repository-posture evaluation to obtain the
    authoritative default branch and compares local HEAD with
    ``origin/<default-branch>``. Failure to establish any evidence returns false
    so the normal completion gate remains in force.
    """
    try:
        report = check_repository_posture(cwd)
    except Exception as exc:
        return False, f"posture evaluation failed: {exc}"
    if report.state == "BLOCKED" or not report.default_branch:
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
    remote_head, error = _run_git(cwd, ["rev-parse", f"origin/{report.default_branch}"])
    if error or not remote_head:
        return False, error or "remote default branch is unavailable"
    if head != remote_head:
        return False, "local default branch differs from checked remote default branch"
    return True, f"clean default branch {report.default_branch} matches origin/{report.default_branch}"


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
    """Accept only clean checked default state or a passing delivery gate.

    A clean local default branch that exactly matches the checked remote default
    branch is sufficient evidence that no local repository delivery is pending.
    Every other state, including unverifiable state, runs the full deterministic
    completion gate. This claim concerns repository state only and does not imply
    absence of external side effects during the session.
    """
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    read_only, reason = _clean_checked_default_branch(cwd)
    if read_only:
        return True, f"completion assurance: read-only repository state; {reason}"
    ok, gate_reason = _run_completion_gate(cwd)
    return ok, gate_reason
