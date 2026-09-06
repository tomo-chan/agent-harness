from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_engine import Decision, PolicyEngine, PolicyError
from reference.hooks import pre_tool_use_adapter

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


def test_canonical_push_is_policy_allow_candidate() -> None:
    result = engine().evaluate(action("git push origin HEAD:refs/heads/feature/x"))
    assert result.decision == "allow"
    assert result.rule == "canonical-git-push"


def test_noncanonical_push_requires_approval() -> None:
    result = engine().evaluate(action("git push origin feature/x"))
    assert result.decision == "ask"


def test_pr_create_is_policy_allow_candidate() -> None:
    result = engine().evaluate(action("gh pr create --title test --body body"))
    assert result.decision == "allow"
    assert result.rule == "canonical-pr-create"


def test_pr_merge_requires_approval() -> None:
    assert engine().evaluate(action("gh pr merge 42 --squash")).decision == "ask"


def test_unknown_action_defaults_to_approval() -> None:
    assert engine().evaluate(action("some-new-tool --mutate")).decision == "ask"


def test_invalid_policy_fails_validation() -> None:
    try:
        PolicyEngine({"default": "permit"})
    except PolicyError:
        return
    raise AssertionError("invalid policy must raise PolicyError")


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


def test_adapter_routes_policy_result_through_s3_publication_gate(monkeypatch) -> None:
    """The trusted hook must invoke the composed S2/S3 publication path."""
    monkeypatch.setenv("AGENT_HARNESS_POLICY", str(POLICY))
    observed: dict[str, object] = {}

    def fake_publication(raw, normalized, result):
        observed["raw"] = raw
        observed["command"] = normalized["input"]["command"]
        observed["policy_decision"] = result.decision
        return Decision("deny", "blocked by composed authority", "repository-authority")

    monkeypatch.setattr(
        pre_tool_use_adapter,
        "validate_autonomous_publication",
        fake_publication,
    )
    raw = {
        "tool": "exec",
        "input": {"command": "git push origin HEAD:refs/heads/feature/x"},
        "cwd": str(ROOT),
        "session_id": "adapter-s3-test",
    }

    result = pre_tool_use_adapter.evaluate(raw)

    assert result.decision == "deny"
    assert result.rule == "repository-authority"
    assert observed["policy_decision"] == "allow"
    assert observed["command"] == "git push origin HEAD:refs/heads/feature/x"
