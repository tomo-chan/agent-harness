#!/usr/bin/env python3
"""Vendor-neutral, deny-first policy engine for agent tool calls."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

VALID_DECISIONS = {"allow", "ask", "deny"}
VALID_RULE_KEYS = {
    "id", "reason", "tool_regex", "command_regex", "action_regex",
    "path_regex", "path_scope",
}


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str
    rule: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"decision": self.decision, "reason": self.reason, "rule": self.rule}


class PolicyError(ValueError):
    pass


class PolicyEngine:
    """Deny > ask > allow policy evaluation with path-aware matching."""

    def __init__(self, policy: dict[str, Any]):
        self.policy = self._validate(policy)

    @classmethod
    def from_file(cls, path: str | Path) -> "PolicyEngine":
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    @staticmethod
    def _validate(policy: Any) -> dict[str, Any]:
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
                    raise PolicyError(f"unsupported keys in {outcome}[{index}]: {sorted(unknown)}")
                for key in ("tool_regex", "command_regex", "action_regex", "path_regex"):
                    if key in rule:
                        re.compile(str(rule[key]))
                if rule.get("path_scope") not in (None, "workspace", "outside_workspace"):
                    raise PolicyError(f"invalid path_scope in {outcome}[{index}]")
        return policy

    @staticmethod
    def _command(action: dict[str, Any]) -> str:
        payload = action.get("input", {})
        if not isinstance(payload, dict):
            return ""
        value = payload.get("command", "")
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
        return str(value)

    @classmethod
    def _text(cls, action: dict[str, Any]) -> str:
        return f"{action.get('tool', '')}\n{cls._command(action)}"

    @staticmethod
    def _paths(action: dict[str, Any]) -> list[str]:
        payload = action.get("input", {})
        if not isinstance(payload, dict):
            return []
        result: list[str] = []
        for key in ("file_path", "path", "target_path", "directory", "cwd"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                result.append(value)
        for key in ("paths", "files"):
            value = payload.get(key)
            if isinstance(value, list):
                result.extend(str(v) for v in value if isinstance(v, (str, Path)))
        return result

    @staticmethod
    def _resolved(path: str, cwd: str) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(cwd) / candidate
        return candidate.resolve(strict=False)

    @classmethod
    def _path_scope_matches(cls, scope: str, paths: Iterable[str], cwd: str) -> bool:
        paths = list(paths)
        if not paths:
            return False
        workspace = Path(cwd).resolve(strict=False)
        inside = []
        for raw in paths:
            resolved = cls._resolved(raw, cwd)
            try:
                resolved.relative_to(workspace)
                inside.append(True)
            except ValueError:
                inside.append(False)
        return all(inside) if scope == "workspace" else any(not item for item in inside)

    @classmethod
    def _matches(cls, rule: dict[str, Any], action: dict[str, Any]) -> bool:
        tool = str(action.get("tool", ""))
        command = cls._command(action)
        paths = cls._paths(action)
        context = action.get("context", {})
        cwd = str(context.get("cwd", ".")) if isinstance(context, dict) else "."

        if pattern := rule.get("tool_regex"):
            if not re.search(str(pattern), tool):
                return False
        if pattern := rule.get("command_regex"):
            if not re.search(str(pattern), command):
                return False
        if pattern := rule.get("action_regex"):
            if not re.search(str(pattern), cls._text(action)):
                return False
        if pattern := rule.get("path_regex"):
            if not paths or not any(re.search(str(pattern), path) for path in paths):
                return False
        if scope := rule.get("path_scope"):
            if not cls._path_scope_matches(str(scope), paths, cwd):
                return False
        return True

    def evaluate(self, action: dict[str, Any]) -> Decision:
        if not isinstance(action, dict):
            raise PolicyError("action must be an object")
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
    try:
        action = json.load(sys.stdin)
        result = PolicyEngine.from_file(sys.argv[1]).evaluate(action)
    except Exception as exc:  # CLI boundary must fail closed.
        result = Decision("deny", f"policy evaluation failed: {exc}", "policy-error")
    json.dump(result.as_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
