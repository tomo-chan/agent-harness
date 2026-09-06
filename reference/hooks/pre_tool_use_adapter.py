#!/usr/bin/env python3
"""Normalize generic PreToolUse input and apply S1-S3 guarantee logic.

S1 supplies the trusted policy path. S2 applies repository authority before
ordinary approval. S3 classifies direct SCM publication and validates the narrow
autonomous publication forms without taking on S4 control-plane review.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = ROOT / "reference" / "harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from policy_engine import Decision, PolicyEngine  # noqa: E402
from scm_publication import validate_autonomous_publication  # noqa: E402


def normalize(raw: dict) -> dict:
    """Normalize a generic PreToolUse-style payload for deterministic evaluation."""
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


def evaluate(raw: dict) -> Decision:
    """Evaluate trusted policy, S2 authority, and S3 publication semantics."""
    policy_value = os.environ.get("AGENT_HARNESS_POLICY")
    if not policy_value:
        return Decision(
            "deny",
            "policy evaluation failed: AGENT_HARNESS_POLICY is required",
            "policy-error",
        )
    try:
        action = normalize(raw)
        result = PolicyEngine.from_file(Path(policy_value)).evaluate(action)
        return validate_autonomous_publication(raw, action, result)
    except Exception as exc:  # The hook boundary must never fail open.
        return Decision("deny", f"policy evaluation failed: {exc}", "policy-error")


def main() -> int:
    """Read one hook action, evaluate it, and emit a portable policy decision."""
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("hook input must be an object")
        result = evaluate(raw)
    except Exception as exc:
        result = Decision("deny", f"policy evaluation failed: {exc}", "policy-error")
    json.dump(result.as_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
