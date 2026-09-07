"""Repository authority evaluation independent of SCM publication semantics.

S2 owns repository identity, protection posture, cache non-authority, generic
mutation classification, and the ordering rule that repository authority
precedes ordinary approval. Later slices classify whether a mutation is a
RESTRICTED operation; S2 deliberately does not encode SCM publication semantics.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "reference" / "hooks"
POSTURE_DIR = ROOT / "reference" / "posture"
for path in (HOOKS_DIR, POSTURE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from checker import check_repository_posture, load_cached_posture, save_cached_posture  # noqa: E402
from policy_engine import Decision  # noqa: E402

_MUTATING_TOOLS = {"write", "edit", "multi_edit", "apply_patch"}
_READ_ONLY_TOOLS = {"read", "glob", "grep"}
_READ_ONLY_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:pwd|ls(?:\s+[^;&|<>\n]*)?|rg(?:\s+[^;&|<>\n]*)?|grep(?:\s+[^;&|<>\n]*)?|"
    r"cat(?:\s+[^;&|<>\n]*)?|head(?:\s+[^;&|<>\n]*)?|tail(?:\s+[^;&|<>\n]*)?|"
    r"wc(?:\s+[^;&|<>\n]*)?|stat(?:\s+[^;&|<>\n]*)?|file(?:\s+[^;&|<>\n]*)?|tree(?:\s+[^;&|<>\n]*)?|"
    r"git\s+(?:status|diff|log|show|rev-parse)(?:\s+[^;&|<>\n]*)?|"
    r"git\s+branch(?:\s+(?:--show-current|--list)(?:\s+[^;&|<>\n]*)?)?|"
    r"git\s+worktree\s+list(?:\s+[^;&|<>\n]*)?|"
    r"gh\s+pr\s+(?:view|status|checks)(?:\s+[^;&|<>\n]*)?)\s*$"
)


def is_mutation(action: dict[str, Any]) -> bool:
    """Conservatively classify whether an observed generic action can mutate state.

    Only positively identified read-only tools and command forms return false.
    Unknown tools, missing command schemas, empty commands, and command variants
    with mutating modes default to mutation so ``BLOCKED`` cannot be bypassed by
    an unrecognized adapter schema.
    """
    tool = str(action.get("tool", "")).lower()
    if tool in _MUTATING_TOOLS:
        return True
    if tool in _READ_ONLY_TOOLS:
        return False

    payload = action.get("input", {})
    if not isinstance(payload, dict):
        return True
    command = payload.get("command")
    if command is None:
        return True
    if isinstance(command, list):
        command = " ".join(str(item) for item in command)
    command = str(command)
    if not command.strip():
        return True
    return not bool(_READ_ONLY_COMMAND_RE.fullmatch(command))


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Run one bounded local Git query and return ``(stdout, error)``."""
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


def _active_repo_root(cwd: Path) -> str | None:
    """Resolve the active Git repository root for cache-context checks."""
    value, _ = _run_git(cwd, ["rev-parse", "--show-toplevel"])
    return str(Path(value).resolve()) if value else None


def refresh_repository_posture(raw: dict[str, Any]):
    """Re-evaluate repository posture and best-effort save a contextual cache copy.

    The freshly computed report is authoritative for this call. Cache persistence
    is deliberately non-authoritative and therefore cannot invalidate or replace
    the report when the state directory is unavailable or concurrent writers race.
    """
    cwd = Path(str(raw.get("cwd") or os.getcwd()))
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = check_repository_posture(cwd)
    try:
        save_cached_posture(session_id, report)
    except Exception:
        pass
    return report


def current_repository_posture(raw: dict[str, Any], *, refresh_for_authority: bool = True):
    """Return posture while refusing to treat writable cache as authority.

    Authority-sensitive callers use the default ``refresh_for_authority=True``
    and always re-evaluate Git/GitHub evidence. ``False`` is only for contextual
    read-only display and applies repository-root and TTL checks to cached data.
    """
    if refresh_for_authority:
        try:
            return refresh_repository_posture(raw)
        except Exception:
            return None

    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = load_cached_posture(session_id)
    current_root = _active_repo_root(cwd)
    if report is None or current_root is None or report.repo_root != current_root:
        return None
    if time.time() - report.checked_at > report.ttl_seconds:
        return None
    return report


def repository_posture_context(raw: dict[str, Any]) -> str:
    """Build non-authoritative SessionStart context for the current posture."""
    try:
        report = refresh_repository_posture(raw)
    except Exception as exc:
        return (
            "Repository security posture UNKNOWN: checker failed: "
            f"{exc}. Authority-sensitive operations will be re-evaluated."
        )
    return report.summary() + f" policy={report.policy_source}."


def enforce_repository_authority(
    raw: dict[str, Any],
    result: Decision,
    *,
    mutation: bool,
    restricted_operation: bool = False,
) -> Decision:
    """Apply fresh repository authority before ordinary approval decisions.

    Args:
        raw: Raw hook context containing at least ``cwd`` and optionally
            ``session_id``.
        result: Lower-level policy decision before authority enforcement.
        mutation: Whether the observed operation can mutate state.
        restricted_operation: Whether the operation is forbidden while posture is
            ``RESTRICTED``. Later slices, notably S3, define this classification.

    Returns:
        The authority-adjusted decision. ``BLOCKED`` denies every mutation;
        ``RESTRICTED`` denies only caller-classified restricted operations. A
        missing fresh posture denies restricted operations but does not invent a
        broader BLOCKED state.
    """
    if not mutation:
        return result

    report = current_repository_posture(raw, refresh_for_authority=True)
    if report is None:
        if restricted_operation:
            return Decision(
                "deny",
                "repository authority is unavailable; restricted operation is prohibited",
                "repository-authority",
            )
        return result

    if report.state == "BLOCKED":
        return Decision("deny", report.summary(), "repository-authority")
    if report.state == "RESTRICTED" and restricted_operation:
        return Decision("deny", report.summary(), "repository-authority")
    return result
