#!/usr/bin/env python3
from __future__ import annotations

from common import completion_check, emit, evaluate, read_stdin, repository_posture_context


def main() -> int:
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

    result = evaluate(raw, "codex")
    decision = "allow" if result.decision == "allow" else "deny"
    reason = f"[{result.rule}] {result.reason}"
    if result.decision == "ask":
        reason = f"approval required; Codex ask is mapped to deny: {reason}"
    return emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    })


if __name__ == "__main__":
    raise SystemExit(main())
