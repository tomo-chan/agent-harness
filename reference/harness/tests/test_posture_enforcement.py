from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "reference" / "harness"))
sys.path.insert(0, str(ROOT / "reference" / "hooks"))

import common  # noqa: E402
from policy_engine import Decision  # noqa: E402


def _raw(command: str):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(ROOT),
        "session_id": "posture-test",
    }


def _report(state: str):
    return SimpleNamespace(state=state, summary=lambda: f"repository posture {state}")


def test_restricted_blocks_remote_scm_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("RESTRICTED"))
    raw = _raw("git push origin feature/x")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "feature-git-mutation"))
    assert result.decision == "deny"
    assert result.rule == "repository-posture"


def test_restricted_allows_local_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("RESTRICTED"))
    raw = _raw("git commit -m test")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "feature-git-mutation"))
    assert result.decision == "allow"


def test_blocked_denies_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("BLOCKED"))
    raw = _raw("git commit -m test")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "feature-git-mutation"))
    assert result.decision == "deny"
