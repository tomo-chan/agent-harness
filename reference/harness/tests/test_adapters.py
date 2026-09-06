import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run(adapter: str, payload: dict, extra_env=None):
    env = os.environ.copy()
    env.update(extra_env or {})
    completed = subprocess.run(
        [sys.executable, str(ROOT / "reference" / "harness" / f"{adapter}.py")],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=True,
    )
    return json.loads(completed.stdout)


def payload(command):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(ROOT),
        "session_id": "s1",
        "turn_id": "t1",
        "tool_use_id": "u1",
    }


def test_claude_ask_is_native_ask():
    value = run("claude", payload("terraform plan"))
    assert value["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_codex_ask_fails_closed_to_deny():
    value = run("codex", payload("terraform plan"))
    assert value["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_codex_external_approval_promotes_ask_to_allow():
    value = run(
        "codex",
        payload("terraform plan"),
        {"AGENT_HARNESS_APPROVED_RULES": "cloud-mutation"},
    )
    assert value["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_devin_denial_uses_block_shape():
    value = run("devin", payload("git push --force origin feature/x"))
    assert value["decision"] == "block"


def test_safe_git_status_allowed_by_all_adapters():
    assert run("claude", payload("git status"))["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert run("codex", payload("git status"))["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert run("devin", payload("git status")) == {}
