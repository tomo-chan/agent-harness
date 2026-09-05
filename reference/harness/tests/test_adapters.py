import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from reference.posture.checker import Check, PostureReport, save_cached_posture  # noqa: E402


def _cache_ready_posture(state_dir: str, session_id: str) -> None:
    report = PostureReport(
        state="READY",
        repository="tomo-chan/agent-harness",
        repo_root=str(ROOT),
        default_branch="main",
        mode="restricted",
        ttl_seconds=3600,
        policy_source="test",
        checked_at=time.time(),
        checks={"test": Check("pass", "fixture")},
    )
    with patch.dict(os.environ, {"AGENT_HARNESS_STATE_DIR": state_dir}):
        save_cached_posture(session_id, report)


def run(adapter: str, payload: dict, extra_env=None):
    env = os.environ.copy()
    env.update(extra_env or {})
    with tempfile.TemporaryDirectory() as state_dir:
        env["AGENT_HARNESS_STATE_DIR"] = state_dir
        _cache_ready_posture(state_dir, str(payload.get("session_id", "s1")))
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
    value = run("claude", payload("gh pr merge 1 --squash"))
    assert value["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_codex_ask_fails_closed_to_deny():
    value = run("codex", payload("gh pr merge 1 --squash"))
    assert value["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_codex_external_approval_promotes_ask_to_allow():
    value = run(
        "codex",
        payload("gh pr merge 1 --squash"),
        {"AGENT_HARNESS_APPROVED_RULES": "scm-merge-release"},
    )
    assert value["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_devin_denial_uses_block_shape():
    value = run("devin", payload("git push --force origin feature/x"))
    assert value["decision"] == "block"


def test_safe_git_status_allowed_by_all_adapters():
    assert run("claude", payload("git status"))["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert run("codex", payload("git status"))["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert run("devin", payload("git status")) == {}
