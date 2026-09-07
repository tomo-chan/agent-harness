"""Require explicit review when autonomous SCM publication changes control plane.

S4 runs only after S3 has established an otherwise autonomous publication. The
comparison base is the checked GitHub repository's current default-branch head,
not a mutable local remote-tracking reference.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

from reference.harness import authority, scm_publication
from reference.hooks.policy_engine import Decision

CONTROL_PLANE_PREFIXES = (
    ".agent-harness/",
    ".claude/",
    ".codex/",
    ".devin/",
    ".github/workflows/",
    "reference/claude/",
    "reference/codex/",
    "reference/harness/",
    "reference/hooks/",
    "reference/posture/",
    "reference/policies/",
    "reference/launcher/",
    "reference/scripts/",
    "reference/kubernetes/",
)
CONTROL_PLANE_FILES = {
    "AGENTS.md",
    ".github/pull_request_template.md",
}


def _run(command: Sequence[str], cwd: Path, timeout: int) -> tuple[str | None, str | None]:
    """Run one bounded observation command and normalize its result."""
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout.strip(), None


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Run one bounded Git observation."""
    return _run(["git", *args], cwd, 5)


def _github_branch_head(
    cwd: Path, repository: str, branch: str
) -> tuple[str | None, str | None]:
    """Return a branch head SHA directly from the checked GitHub repository."""
    endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='')}"
    raw, error = _run(["gh", "api", endpoint], cwd, 15)
    if raw is None:
        return None, error
    try:
        value = json.loads(raw)
        sha = value.get("object", {}).get("sha") if isinstance(value, dict) else None
    except Exception as exc:
        return None, f"invalid GitHub branch-ref JSON: {exc}"
    if not isinstance(sha, str) or not sha:
        return None, "GitHub branch-ref response does not contain object.sha"
    return sha, None


def is_control_plane_path(path: str) -> bool:
    """Return whether a repository path belongs to the Agent Harness control plane."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized in CONTROL_PLANE_FILES or normalized.startswith(CONTROL_PLANE_PREFIXES)


def control_plane_publication_decision(
    raw: dict[str, Any], report: Any
) -> Decision | None:
    """Return review/deny decision for the publication diff, or ``None`` when clear."""
    if not report.repository or not report.default_branch:
        return Decision(
            "deny",
            "checked repository/default branch is unavailable for control-plane review",
            "control-plane-publication",
        )
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    base_sha, error = _github_branch_head(cwd, report.repository, report.default_branch)
    if error or not base_sha:
        return Decision(
            "deny",
            f"cannot obtain authoritative GitHub default-branch head: {error or 'unknown error'}",
            "control-plane-publication",
        )
    _, object_error = _run_git(cwd, ["cat-file", "-e", f"{base_sha}^{{commit}}"])
    if object_error:
        return Decision(
            "deny",
            f"authoritative GitHub base commit {base_sha} is not available locally for diff validation",
            "control-plane-publication",
        )
    changed, diff_error = _run_git(cwd, ["diff", "--name-only", f"{base_sha}...HEAD"])
    if diff_error or changed is None:
        return Decision(
            "deny",
            f"cannot establish publication diff against GitHub base {base_sha}: {diff_error or 'unknown error'}",
            "control-plane-publication",
        )
    protected = sorted(path for path in changed.splitlines() if path and is_control_plane_path(path))
    if not protected:
        return None
    sample = ", ".join(protected[:5])
    suffix = "" if len(protected) <= 5 else f" (+{len(protected) - 5} more)"
    return Decision(
        "ask",
        f"publishing control-plane changes requires explicit review: {sample}{suffix}",
        "control-plane-publication",
    )


def validate_publication(
    raw: dict[str, Any], action: dict[str, Any], result: Decision
) -> Decision:
    """Apply S1-S3 guarantees then require S4 review for control-plane publication."""
    result = scm_publication.validate_autonomous_publication(raw, action, result)
    if result.decision != "allow" or not scm_publication.is_scm_publication(action):
        return result

    report = authority.current_repository_posture(raw, refresh_for_authority=True)
    if report is None or report.state != "READY":
        reason = report.summary() if report is not None else "repository authority is unavailable"
        return Decision("deny", reason, "repository-authority")
    return control_plane_publication_decision(raw, report) or result
