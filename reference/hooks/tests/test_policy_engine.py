from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_engine import PolicyEngine, PolicyError

POLICY = Path(__file__).resolve().parents[2] / "policies" / "policy.example.json"
ADAPTER = Path(__file__).resolve().parents[1] / "pre_tool_use_adapter.py"


def engine() -> PolicyEngine:
    return PolicyEngine.from_file(POLICY)


def action(command: str) -> dict:
    return {"tool": "exec", "input": {"command": command}}


def test_deny_precedes_ask_and_allow() -> None:
    policy = {
        "default": "ask",
        "deny": [{"id": "deny", "command_regex": "danger"}],
        "ask": [{"id": "ask", "command_regex": "danger"}],
        "allow": [{"id": "allow", "command_regex": "danger"}],
    }
    assert PolicyEngine(policy).evaluate(action("danger")).decision == "deny"


def test_read_only_git_is_allowed() -> None:
    assert engine().evaluate(action("git status")).decision == "allow"


def test_force_push_is_denied() -> None:
    assert engine().evaluate(action("git push --force origin feature/x")).decision == "deny"


def test_main_push_is_denied() -> None:
    assert engine().evaluate(action("git push origin main")).decision == "deny"


def test_pr_merge_requires_approval() -> None:
    assert engine().evaluate(action("gh pr merge 42 --squash")).decision == "ask"


def test_unknown_action_defaults_to_approval() -> None:
    assert engine().evaluate(action("some-new-tool --mutate")).decision == "ask"


def test_invalid_policy_fails_validation() -> None:
    with pytest.raises(PolicyError):
        PolicyEngine({"default": "permit"})


@pytest.mark.parametrize("value", [False, None, 42, ["safe"]])
def test_non_string_regex_fields_are_rejected(value) -> None:
    policy = {
        "default": "ask",
        "allow": [{"id": "unsafe", "command_regex": value}],
    }
    with pytest.raises(PolicyError):
        PolicyEngine(policy)


def test_empty_regex_remains_an_explicit_predicate() -> None:
    policy = {
        "default": "ask",
        "allow": [{"id": "explicit-empty", "command_regex": ""}],
    }
    assert PolicyEngine(policy).evaluate(action("anything")).decision == "allow"


def test_adapter_denies_when_trusted_policy_is_missing() -> None:
    env = os.environ.copy()
    env.pop("AGENT_HARNESS_POLICY", None)
    result = subprocess.run(
        [sys.executable, str(ADAPTER)],
        input=json.dumps({"tool": "exec", "input": {"command": "git status"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    decision = json.loads(result.stdout)
    assert decision["decision"] == "deny"
    assert decision["rule"] == "policy-error"
