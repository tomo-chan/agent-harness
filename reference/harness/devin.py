#!/usr/bin/env python3
from __future__ import annotations

from common import completion_check, emit, evaluate, read_stdin


def main() -> int:
    try:
        raw = read_stdin()
    except Exception as exc:
        return emit({"decision": "block", "reason": f"invalid hook input: {exc}"})

    event = str(raw.get("hook_event_name", "PreToolUse"))
    if event == "Stop":
        ok, reason = completion_check(raw)
        return emit({} if ok else {"decision": "block", "reason": reason})

    result = evaluate(raw, "devin")
    # Devin's portable blocking contract is top-level decision:block.
    # Ask is held until an external approval rule promotes it to allow.
    if result.decision == "allow":
        return emit({})
    prefix = "approval required: " if result.decision == "ask" else ""
    return emit({"decision": "block", "reason": f"{prefix}[{result.rule}] {result.reason}"})


if __name__ == "__main__":
    raise SystemExit(main())
