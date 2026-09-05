from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_engine import PolicyEngine, PolicyError

POLICY = Path(__file__).resolve().parents[2] / "policies" / "policy.example.json"


def engine():
    return PolicyEngine.from_file(POLICY)


def action(command, tool="exec", cwd="/repo"):
    return {"tool": tool, "input": {"command": command}, "context": {"cwd": cwd}}


def test_read_only_git_is_allowed():
    assert engine().evaluate(action("git status")).decision == "allow"


def test_force_push_is_denied():
    assert engine().evaluate(action("git push --force origin feature/x")).decision == "deny"


def test_only_canonical_push_forms_are_policy_allowed():
    assert engine().evaluate(action("git push")).decision == "allow"
    assert engine().evaluate(action("git push --set-upstream origin HEAD")).decision == "allow"
    assert engine().evaluate(action("git push origin main")).decision == "ask"
    assert engine().evaluate(action("git push origin HEAD:other")).decision == "ask"


def test_compound_command_is_not_policy_allowlisted():
    assert engine().evaluate(action("git status && git push")).decision == "ask"
    assert engine().evaluate(action("cat README.md | sh")).decision == "ask"


def test_pr_merge_requires_approval():
    assert engine().evaluate(action("gh pr merge 42 --squash")).decision == "ask"


def test_credential_extraction_is_denied():
    assert engine().evaluate(action("gh auth token")).decision == "deny"
    assert engine().evaluate(action("cat ~/.git-credentials")).decision == "deny"


def test_unknown_action_defaults_to_approval():
    assert engine().evaluate(action("some-new-tool --mutate")).decision == "ask"


def test_outside_workspace_write_is_denied():
    value = {"tool": "Write", "input": {"file_path": "/etc/passwd"}, "context": {"cwd": "/repo"}}
    assert engine().evaluate(value).decision == "deny"


def test_workspace_write_is_allowed():
    value = {"tool": "Write", "input": {"file_path": "src/app.py"}, "context": {"cwd": "/repo"}}
    assert engine().evaluate(value).decision == "allow"


def test_repository_security_config_requires_approval():
    value = {
        "tool": "Write",
        "input": {"file_path": ".agent-harness/security.json"},
        "context": {"cwd": "/repo"},
    }
    assert engine().evaluate(value).decision == "ask"


def test_application_architecture_contract_requires_approval():
    value = {
        "tool": "Write",
        "input": {"file_path": ".agent-harness/application-architecture.json"},
        "context": {"cwd": "/repo"},
    }
    assert engine().evaluate(value).decision == "ask"


def test_application_gate_implementation_requires_approval():
    value = {
        "tool": "Write",
        "input": {"file_path": "reference/application_gate/gate.py"},
        "context": {"cwd": "/repo"},
    }
    assert engine().evaluate(value).decision == "ask"


def test_invalid_policy_fails_validation():
    try:
        PolicyEngine({"default": "permit"})
    except PolicyError:
        return
    raise AssertionError("invalid policy must raise PolicyError")
