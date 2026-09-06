"""Session-aware deterministic completion assurance.

A Stop hook should enforce delivery invariants only when the session actually
changed repository state. SessionStart therefore records a compact Git snapshot.
At Stop, an unchanged snapshot is treated as a read-only session and completes
without requiring a feature branch or upstream. Changed or unverifiable state is
subject to the normal deterministic completion gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Run a bounded Git query used to construct a session snapshot."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=5, check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout, None


def _session_id(raw: dict[str, Any]) -> str:
    """Return the stable hook session identifier used for completion state."""
    return str(raw.get("session_id") or f"pid-{os.getpid()}")


def _state_path(session_id: str) -> Path:
    """Derive a private filesystem path for one session snapshot."""
    base = Path(os.environ.get(
        "AGENT_HARNESS_STATE_DIR",
        str(Path(tempfile.gettempdir()) / "agent-harness"),
    )) / "completion"
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return base / f"{digest}.json"


def _snapshot(cwd: Path) -> tuple[dict[str, str] | None, str | None]:
    """Capture repository root, HEAD, and exact porcelain worktree state."""
    root, error = _run_git(cwd, ["rev-parse", "--show-toplevel"])
    if error or root is None:
        return None, error or "repository root unavailable"
    repo_root = Path(root.strip()).resolve()
    head, error = _run_git(repo_root, ["rev-parse", "HEAD"])
    if error or head is None:
        return None, error or "HEAD unavailable"
    status, error = _run_git(repo_root, ["status", "--porcelain=v1", "--untracked-files=all"])
    if error or status is None:
        return None, error or "worktree status unavailable"
    return {
        "repo_root": str(repo_root),
        "head": head.strip(),
        "status": status,
    }, None


def capture_session_start(raw: dict[str, Any]) -> str:
    """Persist the SessionStart Git snapshot and return a context summary.

    Snapshot failure does not weaken Stop enforcement: no valid snapshot means
    Stop falls back to the full completion gate instead of assuming read-only.
    """
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    snapshot, error = _snapshot(cwd)
    if snapshot is None:
        return f"Completion baseline UNKNOWN: {error}. Stop will require full completion assurance."

    path = _state_path(_session_id(raw))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    return "Completion baseline captured; unchanged repository state is treated as read-only."


def _load_session_start(raw: dict[str, Any]) -> dict[str, str] | None:
    """Load a previously captured SessionStart snapshot if it is valid."""
    try:
        value = json.loads(_state_path(_session_id(raw)).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if not all(isinstance(value.get(key), str) for key in ("repo_root", "head", "status")):
        return None
    return {key: value[key] for key in ("repo_root", "head", "status")}


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
    """Skip delivery gates only when repository state is unchanged since SessionStart.

    Equality of repository root, HEAD, and exact porcelain status is evidence for
    a read-only session. Any changed or unverifiable state runs the full gate.
    """
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    baseline = _load_session_start(raw)
    current, error = _snapshot(cwd)
    if baseline is not None and current is not None and baseline == current:
        return True, "completion assurance: read-only session; repository state unchanged"
    if current is None:
        reason = error or "current repository state unavailable"
        ok, gate_reason = _run_completion_gate(cwd)
        return ok, f"completion baseline comparison unavailable ({reason}); {gate_reason}"
    return _run_completion_gate(cwd)
