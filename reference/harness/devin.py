#!/usr/bin/env python3
from __future__ import annotations

from common import completion_check, emit, evaluate, read_stdin, repository_posture_context


def main() -> int:
    try:
        raw = read_stdin()
    except Exception as exc:
        return emit({"decision": "block", "reason": f"invalid hook input: {exc}"})

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

    result = evaluate(raw, "devin")
    if result.decision == "allow":
        return emit({})
    prefix = "approval required: " if result.decision == "ask" else ""
    return emit({"decision": "block", "reason": f"{prefix}[{result.rule}] {result.reason}"})


if __name__ == "__main__":
    raise SystemExit(main())
