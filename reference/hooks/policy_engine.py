#!/usr/bin/env python3
"""Vendor-neutral, deny-first policy engine for agent tool calls.

The engine is intentionally deterministic. Policy schema errors and evaluation
errors are not converted into permission; the CLI boundary emits ``deny`` when
it cannot establish a valid decision.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VALID_DECISIONS = {"allow", "ask", "deny"}
VALID_RULE_KEYS = {"id", "reason", "tool_regex", "command_regex", "action_regex"}


@dataclass(frozen=True)
class Decision:
    """One deterministic policy decision and the rule that produced it."""

    decision: str
    reason: str
    rule: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize the decision for hook adapters and CLI output."""
        return {"decision": self.decision, "reason": self.reason, "rule": self.rule}


class PolicyError(ValueError):
    """Raised when policy configuration violates the supported policy schema."""


class PolicyEngine:
    """Evaluate normalized actions with explicit deny > ask > allow precedence."""

    def __init__(self, policy: dict[str, Any]):
        """Validate and retain one policy mapping for deterministic evaluation."""
        self.policy = self._validate(policy)

    @classmethod
    def from_file(cls, path: str | Path) -> "PolicyEngine":
        """Load a UTF-8 JSON policy file and construct a validated engine."""
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    @staticmethod
    def _validate(policy: Any) -> dict[str, Any]:
        """Validate policy structure and all configured regular expressions."""
        if not isinstance(policy, dict):
            raise PolicyError("policy must be an object")
        default = policy.get("default", "ask")
        if default not in VALID_DECISIONS:
            raise PolicyError(f"invalid default decision: {default!r}")
        for outcome in VALID_DECISIONS:
            rules = policy.get(outcome, [])
            if not isinstance(rules, list):
                raise PolicyError(f"{outcome} must be a list")
            for index, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    raise PolicyError(f"{outcome}[{index}] must be an object")
                unknown = set(rule) - VALID_RULE_KEYS
                if unknown:
                    raise PolicyError(
                        f"unsupported keys in {outcome}[{index}]: {sorted(unknown)}"
                    )
                for key in ("tool_regex", "command_regex", "action_regex"):
                    if key in rule:
                        try:
                            re.compile(str(rule[key]))
                        except re.error as exc:
                            raise PolicyError(
                                f"invalid regex in {outcome}[{index}].{key}: {exc}"
                            ) from exc
        return policy

    @staticmethod
    def _command(action: dict[str, Any]) -> str:
        """Extract a command string from a normalized action payload."""
        payload = action.get("input", {})
        if not isinstance(payload, dict):
            return ""
        value = payload.get("command", "")
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
        return str(value)

    @classmethod
    def _text(cls, action: dict[str, Any]) -> str:
        """Build the combined tool-and-command text used by action regex rules."""
        return f"{action.get('tool', '')}\n{cls._command(action)}"

    @classmethod
    def _matches(cls, rule: dict[str, Any], action: dict[str, Any]) -> bool:
        """Return whether every predicate configured on one rule matches the action."""
        tool = str(action.get("tool", ""))
        command = cls._command(action)
        if pattern := rule.get("tool_regex"):
            if not re.search(str(pattern), tool):
                return False
        if pattern := rule.get("command_regex"):
            if not re.search(str(pattern), command):
                return False
        if pattern := rule.get("action_regex"):
            if not re.search(str(pattern), cls._text(action)):
                return False
        return True

    def evaluate(self, action: dict[str, Any]) -> Decision:
        """Evaluate one normalized action using deny-first deterministic precedence."""
        if not isinstance(action, dict):
            raise PolicyError("action must be an object")
        for outcome in ("deny", "ask", "allow"):
            for rule in self.policy.get(outcome, []):
                if self._matches(rule, action):
                    return Decision(
                        outcome,
                        rule.get("reason", f"matched {outcome} rule"),
                        rule.get("id"),
                    )
        default = self.policy.get("default", "ask")
        return Decision(default, "no explicit policy rule matched", "default")


def main() -> int:
    """Evaluate one JSON action from stdin and fail closed at the CLI boundary."""
    if len(sys.argv) != 2:
        print("usage: policy_engine.py POLICY.json", file=sys.stderr)
        return 64
    try:
        action = json.load(sys.stdin)
        result = PolicyEngine.from_file(sys.argv[1]).evaluate(action)
    except Exception as exc:  # The process boundary must never fail open.
        result = Decision("deny", f"policy evaluation failed: {exc}", "policy-error")
    json.dump(result.as_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
