#!/usr/bin/env python3
"""Normalize generic PreToolUse input and evaluate the trusted policy.

The adapter does not fall back to a repository-local policy. S1 requires the
policy path to be supplied by a trusted launcher through
``AGENT_HARNESS_POLICY``. Missing or invalid trusted policy state therefore
produces a deterministic ``deny`` decision.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from policy_engine import Decision, PolicyEngine


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
    """Evaluate one hook action using only an explicitly trusted policy path."""
    try:
        policy_value = os.environ.get("AGENT_HARNESS_POLICY")
        if not policy_value:
            raise RuntimeError("AGENT_HARNESS_POLICY is required")
        policy_path = Path(policy_value)
        raw = json.load(sys.stdin)
        action = normalize(raw)
        result = PolicyEngine.from_file(policy_path).evaluate(action)
    except Exception as exc:  # The hook boundary must never fail open.
        result = Decision("deny", f"policy evaluation failed: {exc}", "policy-error")
    json.dump(result.as_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
