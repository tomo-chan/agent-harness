from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "reference" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from policy_engine import Decision, PolicyEngine  # noqa: E402

DEFAULT_POLICY = ROOT / "reference" / "policies" / "policy.example.json"


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


def evaluate(raw: dict[str, Any], vendor: str) -> Decision:
    policy = Path(os.environ.get("AGENT_HARNESS_POLICY", str(DEFAULT_POLICY)))
    try:
        result = PolicyEngine.from_file(policy).evaluate(normalize(raw, vendor))
    except Exception as exc:
        return Decision("deny", f"policy evaluation failed closed: {exc}", "policy-error")

    approved = {item.strip() for item in os.environ.get("AGENT_HARNESS_APPROVED_RULES", "").split(",") if item.strip()}
    if result.decision == "ask" and (result.rule in approved or "*" in approved):
        return Decision("allow", f"externally approved rule {result.rule}: {result.reason}", result.rule)
    return result


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
