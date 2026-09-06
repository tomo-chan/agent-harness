#!/usr/bin/env python3
"""Adapt normalized harness decisions to Claude Code hook responses."""

from __future__ import annotations

from common import completion_check, emit, evaluate, read_stdin, repository_posture_context


def main() -> int:
    """Handle Claude Code SessionStart, PreToolUse, and Stop hook events."""
    try:
        raw = read_stdin()
    except Exception as exc:
        return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"invalid hook input: {exc}"}})

    event = str(raw.get("hook_event_name", "PreToolUse"))
    if event == "SessionStart":
        return emit({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": repository_posture_context(raw),
            }
        })
    if event == "Stop":
        ok, reason = completion_check(raw)
        return emit({} if ok else {"decision": "block", "reason": reason})

    result = evaluate(raw, "claude")
    decision = result.decision
    if decision not in {"allow", "ask", "deny"}:
        decision = "deny"
    return emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"[{result.rule}] {result.reason}",
        }
    })


if __name__ == "__main__":
    raise SystemExit(main())
