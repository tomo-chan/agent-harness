#!/usr/bin/env python3
"""Adapt normalized harness decisions to Devin CLI hook responses."""

from __future__ import annotations

from common import emit, evaluate, read_stdin, repository_posture_context
from completion import capture_session_start, completion_check


def main() -> int:
    """Handle Devin CLI SessionStart, PreToolUse, and Stop hook events."""
    try:
        raw = read_stdin()
    except Exception as exc:
        return emit({"decision": "block", "reason": f"invalid hook input: {exc}"})

    event = str(raw.get("hook_event_name", "PreToolUse"))
    if event == "SessionStart":
        context = repository_posture_context(raw) + " " + capture_session_start(raw)
        return emit({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        })
    if event == "Stop":
        ok, reason = completion_check(raw)
        return emit({} if ok else {"decision": "block", "reason": reason})

    result = evaluate(raw, "devin")
    if result.decision == "allow":
        return emit({})
    prefix = "approval required: " if result.decision == "ask" else ""
    return emit({"decision": "block", "reason": f"{prefix}[{result.rule}] {result.reason}"})


if __name__ == "__main__":
    raise SystemExit(main())
