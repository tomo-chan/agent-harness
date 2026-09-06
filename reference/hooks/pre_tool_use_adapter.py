#!/usr/bin/env python3
"""Example adapter from common PreToolUse-style hook input to the policy engine.

The exact vendor response schema should be kept in a vendor-specific adapter. This
example intentionally emits a simple portable allow/ask/deny object.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from policy_engine import PolicyEngine


def normalize(raw: dict) -> dict:
    """Normalize a generic PreToolUse-style payload for the central policy engine."""
    return {
        "event": "pre_tool_use",
        "tool": raw.get("tool_name", raw.get("tool", "")),
        "input": raw.get("tool_input", raw.get("input", {})),
        "context": {
            "session_id": raw.get("session_id"),
            "turn_id": raw.get("turn_id", raw.get("prompt_id")),
            "cwd": raw.get("cwd", os.getcwd()),
        },
    }


def main() -> int:
    """Evaluate one normalized hook action and emit a portable policy decision."""
    policy_path = Path(os.environ.get("AGENT_POLICY", "reference/policies/policy.example.json"))
    raw = json.load(sys.stdin)
    action = normalize(raw)
    result = PolicyEngine.from_file(policy_path).evaluate(action)
    json.dump(result.as_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
