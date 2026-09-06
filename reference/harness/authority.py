"""Repository authority evaluation independent of SCM publication semantics.

S2 owns repository identity, protection posture, cache non-authority, and the
ordering rule that repository authority precedes ordinary approval. Callers from
later slices classify whether an observed operation is a mutation and whether a
RESTRICTED state forbids that operation; S2 deliberately does not encode SCM
command semantics.
"""

from __future__ import annotations

import os
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
    """Re-evaluate repository posture and save a non-authoritative session copy."""
    cwd = Path(str(raw.get("cwd") or os.getcwd()))
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = check_repository_posture(cwd)
    save_cached_posture(session_id, report)
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
        raw: Normalized hook context containing at least ``cwd`` and optionally
            ``session_id``.
        result: Lower-level policy decision before authority enforcement.
        mutation: Whether the observed operation can mutate state. Classification
            belongs to the caller because S2 does not own command semantics.
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
