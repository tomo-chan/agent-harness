#!/usr/bin/env python3
"""Adapt Codex lifecycle events to the shared S1-S5 guarantees."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.harness.vendor_runtime import (  # noqa: E402
    completion,
    emit,
    evaluate_pre_tool_use,
    read_stdin,
    session_start_context,
)


def main() -> int:
    """Handle Codex SessionStart, PreToolUse, and Stop events fail-closed."""
    try:
        raw = read_stdin()
    except Exception as exc:
        return emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"invalid hook input: {exc}",
                }
            }
        )

    event = str(raw.get("hook_event_name", "PreToolUse"))
    if event == "SessionStart":
        return emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": session_start_context(raw),
                }
            }
        )
    if event == "Stop":
        ok, reason = completion(raw)
        return emit({} if ok else {"decision": "block", "reason": reason})

    result = evaluate_pre_tool_use(raw)
    decision = "allow" if result.decision == "allow" else "deny"
    reason = f"[{result.rule}] {result.reason}"
    if result.decision == "ask":
        reason = f"approval required; Codex ask is mapped to deny: {reason}"
    return emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
