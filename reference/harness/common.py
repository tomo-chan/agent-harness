from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "reference" / "hooks"
POSTURE_DIR = ROOT / "reference" / "posture"
for path in (HOOKS_DIR, POSTURE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from checker import check_repository_posture, load_cached_posture, save_cached_posture  # noqa: E402
from policy_engine import Decision, PolicyEngine  # noqa: E402

DEFAULT_POLICY = ROOT / "reference" / "policies" / "policy.example.json"
SCM_MUTATION_RE = re.compile(
    r"(?i)^\s*(?:git\s+push\b|gh\s+pr\s+(?:create|merge)\b|gh\s+release\s+(?:create|edit|upload|delete)\b)"
)
READ_ONLY_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:pwd|ls|find|rg|grep|cat|head|tail|wc|stat|file|tree|git\s+(?:status|diff|log|show|branch|rev-parse|worktree\s+list)\b|gh\s+pr\s+(?:view|status|checks)\b)"
)
MUTATING_TOOLS = {"write", "edit", "multi_edit", "apply_patch"}


def read_stdin() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    return value


def normalize(raw: dict[str, Any], vendor: str) -> dict[str, Any]:
    tool_input = raw.get("tool_input", raw.get("input", {}))
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    return {
        "event": str(raw.get("hook_event_name", raw.get("event", "PreToolUse"))),
        "tool": str(raw.get("tool_name", raw.get("tool", ""))),
        "input": tool_input,
        "context": {
            "vendor": vendor,
            "session_id": raw.get("session_id"),
            "turn_id": raw.get("turn_id", raw.get("prompt_id")),
            "tool_use_id": raw.get("tool_use_id"),
            "cwd": str(raw.get("cwd") or os.getcwd()),
            "permission_mode": raw.get("permission_mode"),
        },
    }


def _command(action: dict[str, Any]) -> str:
    value = action.get("input", {}).get("command", "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _is_scm_mutation(action: dict[str, Any]) -> bool:
    return bool(SCM_MUTATION_RE.search(_command(action)))


def _is_mutation(action: dict[str, Any]) -> bool:
    tool = str(action.get("tool", "")).lower()
    if tool in MUTATING_TOOLS:
        return True
    command = _command(action)
    if not command:
        return False
    return not bool(READ_ONLY_COMMAND_RE.search(command))


def refresh_repository_posture(raw: dict[str, Any]):
    cwd = Path(str(raw.get("cwd") or os.getcwd()))
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = check_repository_posture(cwd)
    save_cached_posture(session_id, report)
    return report


def current_repository_posture(raw: dict[str, Any], *, refresh_if_stale: bool = True):
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = load_cached_posture(session_id)
    stale = report is None
    if report is not None:
        stale = stale or report.repo_root != str(cwd if (cwd / ".git").exists() else Path(report.repo_root))
        stale = stale or (time.time() - report.checked_at > report.ttl_seconds)
    if stale and refresh_if_stale:
        try:
            report = refresh_repository_posture(raw)
        except Exception:
            return None
    return report


def repository_posture_context(raw: dict[str, Any]) -> str:
    try:
        report = refresh_repository_posture(raw)
    except Exception as exc:
        return f"Repository security posture UNKNOWN: checker failed: {exc}. Remote SCM mutations will be restricted."
    source = f" policy={report.policy_source}."
    return report.summary() + source


def _enforce_repository_posture(raw: dict[str, Any], action: dict[str, Any], result: Decision) -> Decision:
    if result.decision != "allow" or action.get("event") != "PreToolUse":
        return result
    if not _is_mutation(action):
        return result

    report = current_repository_posture(raw, refresh_if_stale=True)
    if report is None:
        if _is_scm_mutation(action):
            return Decision(
                "deny",
                "repository security posture is unavailable; remote SCM mutation is restricted",
                "repository-posture",
            )
        return result

    if report.state == "BLOCKED":
        return Decision("deny", report.summary(), "repository-posture")
    if report.state == "RESTRICTED" and _is_scm_mutation(action):
        return Decision("deny", report.summary(), "repository-posture")
    return result


def evaluate(raw: dict[str, Any], vendor: str) -> Decision:
    policy = Path(os.environ.get("AGENT_HARNESS_POLICY", str(DEFAULT_POLICY)))
    action = normalize(raw, vendor)
    try:
        result = PolicyEngine.from_file(policy).evaluate(action)
    except Exception as exc:
        return Decision("deny", f"policy evaluation failed closed: {exc}", "policy-error")

    approved = {
        item.strip()
        for item in os.environ.get("AGENT_HARNESS_APPROVED_RULES", "").split(",")
        if item.strip()
    }
    if result.decision == "ask" and (result.rule in approved or "*" in approved):
        result = Decision("allow", f"externally approved rule {result.rule}: {result.reason}", result.rule)
    return _enforce_repository_posture(raw, action, result)


def completion_check(raw: dict[str, Any]) -> tuple[bool, str]:
    cwd = Path(str(raw.get("cwd") or os.getcwd()))
    gate = ROOT / "reference" / "scripts" / "completion_gate.sh"
    env = os.environ.copy()
    try:
        completed = subprocess.run(
            ["bash", str(gate)],
            cwd=cwd,
            env=env,
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


def emit(value: dict[str, Any]) -> int:
    json.dump(value, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0
