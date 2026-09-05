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
    return SimpleNamespace(
        state=state,
        repository="tomo-chan/agent-harness",
        default_branch="main",
        summary=lambda: f"repository posture {state}",
    )


def test_restricted_blocks_remote_scm_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("RESTRICTED"))
    raw = _raw("git push")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "canonical-git-push"))
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


def test_compound_shell_cannot_hide_push(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("RESTRICTED"))
    raw = _raw("git status && git push")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "read-only-git"))
    assert result.decision == "ask"
    assert result.rule == "compound-shell"


def test_noncanonical_push_is_denied(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("READY"))
    raw = _raw("git push origin HEAD:other")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "canonical-git-push"))
    assert result.decision == "deny"
    assert result.rule == "canonical-git-push"


def test_canonical_push_requires_checked_branch_and_upstream(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("READY"))

    def fake_git(_cwd, args):
        values = {
            ("branch", "--show-current"): ("feature/review-fix", None),
            ("remote", "get-url", "origin"): ("https://github.com/tomo-chan/agent-harness.git", None),
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): ("origin/feature/review-fix", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(common, "_run_git", fake_git)
    raw = _raw("git push")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "canonical-git-push"))
    assert result.decision == "allow"


def test_canonical_push_denies_default_branch(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("READY"))

    def fake_git(_cwd, args):
        if tuple(args) == ("branch", "--show-current"):
            return "main", None
        raise AssertionError(args)

    monkeypatch.setattr(common, "_run_git", fake_git)
    raw = _raw("git push")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "canonical-git-push"))
    assert result.decision == "deny"
    assert "default branch" in result.reason


def test_pr_create_cannot_override_repo_head_or_base(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("READY"))
    raw = _raw("gh pr create --repo other/repo --fill")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "pr-publish"))
    assert result.decision == "deny"
    assert result.rule == "canonical-pr-create"
