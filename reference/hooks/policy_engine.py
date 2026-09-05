#!/usr/bin/env python3
"""Small vendor-neutral policy engine for agent tool calls."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str
    rule: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"decision": self.decision, "reason": self.reason, "rule": self.rule}


class PolicyEngine:
    """First-match engine with deny/ask/allow sections and deny-first precedence."""

    def __init__(self, policy: dict[str, Any]):
        self.policy = policy

    @classmethod
    def from_file(cls, path: str | Path) -> "PolicyEngine":
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    @staticmethod
    def _text(action: dict[str, Any]) -> str:
        tool = str(action.get("tool", ""))
        payload = action.get("input", {})
        command = payload.get("command", "") if isinstance(payload, dict) else ""
        return f"{tool}\n{command}"

    @staticmethod
    def _matches(rule: dict[str, Any], action: dict[str, Any]) -> bool:
        tool = str(action.get("tool", ""))
        if pattern := rule.get("tool_regex"):
            if not re.search(pattern, tool):
                return False
        if pattern := rule.get("command_regex"):
            payload = action.get("input", {})
            command = payload.get("command", "") if isinstance(payload, dict) else ""
            if not re.search(pattern, command):
                return False
        if pattern := rule.get("action_regex"):
            if not re.search(pattern, PolicyEngine._text(action)):
                return False
        return True

    def evaluate(self, action: dict[str, Any]) -> Decision:
        # Security precedence is explicit rather than dependent on JSON ordering.
        for outcome in ("deny", "ask", "allow"):
            for rule in self.policy.get(outcome, []):
                if self._matches(rule, action):
                    return Decision(outcome, rule.get("reason", f"matched {outcome} rule"), rule.get("id"))
        default = self.policy.get("default", "ask")
        return Decision(default, "no explicit policy rule matched", "default")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: policy_engine.py POLICY.json", file=sys.stderr)
        return 64
    action = json.load(sys.stdin)
    result = PolicyEngine.from_file(sys.argv[1]).evaluate(action)
    json.dump(result.as_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
