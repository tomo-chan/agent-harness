import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_engine import PolicyEngine


POLICY = Path(__file__).resolve().parents[2] / "policies" / "policy.example.json"


def engine():
    return PolicyEngine.from_file(POLICY)


def action(command):
    return {"tool": "exec", "input": {"command": command}}


def test_read_only_git_is_allowed():
    assert engine().evaluate(action("git status")).decision == "allow"


def test_force_push_is_denied():
    assert engine().evaluate(action("git push --force origin feature/x")).decision == "deny"


def test_main_push_is_denied():
    assert engine().evaluate(action("git push origin main")).decision == "deny"


def test_pr_merge_requires_approval():
    assert engine().evaluate(action("gh pr merge 42 --squash")).decision == "ask"


def test_unknown_action_defaults_to_approval():
    assert engine().evaluate(action("some-new-tool --mutate")).decision == "ask"
