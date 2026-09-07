from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from reference.harness import completion


def _raw(tmp_path: Path, *, stop_hook_active: bool = False) -> dict:
    """Build one Stop payload for completion-assurance tests."""
    return {
        "cwd": str(tmp_path),
        "session_id": "completion-test",
        "stop_hook_active": stop_hook_active,
    }


def _report(state: str = "READY", default_branch: str = "main") -> SimpleNamespace:
    """Build one repository-posture test double."""
    return SimpleNamespace(
        state=state,
        repository="acme/widget",
        default_branch=default_branch,
        summary=lambda: f"repository posture {state}",
    )


def _stub_clean_default_branch(monkeypatch) -> None:
    """Stub deterministic evidence for a clean READY default branch."""
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())

    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): ("main", None),
            ("status", "--porcelain=v1", "--untracked-files=all"): ("", None),
            ("rev-parse", "HEAD"): ("abc", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(
        completion, "_github_branch_head", lambda _cwd, repo, branch: ("abc", None)
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: pytest.fail("gate must not run")
    )


def test_session_start_does_not_persist_authoritative_completion_state(tmp_path: Path) -> None:
    reason = completion.capture_session_start(_raw(tmp_path))
    assert "re-evaluate authoritative repository state at Stop" in reason


def test_first_passing_stop_returns_evidence_for_agent_review(
    tmp_path: Path, monkeypatch
) -> None:
    """A passing deterministic state starts one non-deterministic review turn."""
    _stub_clean_default_branch(monkeypatch)

    ok, reason = completion.completion_check(_raw(tmp_path))

    assert ok is False
    assert "Deterministic completion assurance passed" in reason
    assert "repository has no delivery delta" in reason
    assert "new findings or insights" in reason
    assert "ask the requester only when" in reason


def test_follow_up_stop_passes_after_agent_review(tmp_path: Path, monkeypatch) -> None:
    """The vendor stop-hook continuation marker prevents an infinite review loop."""
    _stub_clean_default_branch(monkeypatch)

    ok, reason = completion.completion_check(_raw(tmp_path, stop_hook_active=True))

    assert ok is True
    assert "passed after agent review" in reason
    assert "repository has no delivery delta" in reason


def test_passing_delivery_gate_also_requires_agent_review(
    tmp_path: Path, monkeypatch
) -> None:
    """Changed work receives the same non-deterministic review after its gate passes."""
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())
    monkeypatch.setattr(
        completion,
        "_run_git",
        lambda _cwd, args: (
            ("feature/x", None)
            if tuple(args) == ("branch", "--show-current")
            else pytest.fail(str(args))
        ),
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (True, "delivery gate passed")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))

    assert ok is False
    assert "delivery gate passed" in reason
    assert "non-deterministic completion conditions" in reason


def test_follow_up_stop_rechecks_deterministic_gate(tmp_path: Path, monkeypatch) -> None:
    """Agent review never bypasses a deterministic guarantee that later fails."""
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())
    monkeypatch.setattr(
        completion,
        "_run_git",
        lambda _cwd, args: (
            ("feature/x", None)
            if tuple(args) == ("branch", "--show-current")
            else pytest.fail(str(args))
        ),
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "delivery gate failed")
    )

    ok, reason = completion.completion_check(_raw(tmp_path, stop_hook_active=True))

    assert ok is False
    assert reason == "delivery gate failed"


def test_restricted_default_branch_never_skips_delivery_gate(
    tmp_path: Path, monkeypatch
) -> None:
    """Only READY posture is sufficient for the no-change evidence path."""
    monkeypatch.setattr(
        completion, "check_repository_posture", lambda _cwd: _report("RESTRICTED")
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "full gate required")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "full gate required"


def test_dirty_default_branch_runs_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())

    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): ("main", None),
            ("status", "--porcelain=v1", "--untracked-files=all"): (" M src/app.py", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "dirty delivery")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "dirty delivery"


def test_diverged_default_branch_runs_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())

    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): ("main", None),
            ("status", "--porcelain=v1", "--untracked-files=all"): ("", None),
            ("rev-parse", "HEAD"): ("local", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(
        completion, "_github_branch_head", lambda _cwd, repo, branch: ("remote", None)
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "diverged delivery")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "diverged delivery"


def test_mutated_remote_tracking_ref_is_not_completion_authority(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())

    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): ("main", None),
            ("status", "--porcelain=v1", "--untracked-files=all"): ("", None),
            ("rev-parse", "HEAD"): ("forged", None),
        }
        if tuple(args) == ("rev-parse", "origin/main"):
            pytest.fail("local remote-tracking ref must not be used as authority")
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(
        completion,
        "_github_branch_head",
        lambda _cwd, repo, branch: ("actual-github", None),
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "full gate required")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "full gate required"


def test_unavailable_github_head_never_skips_delivery_gate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())

    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): ("main", None),
            ("status", "--porcelain=v1", "--untracked-files=all"): ("", None),
            ("rev-parse", "HEAD"): ("abc", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(
        completion,
        "_github_branch_head",
        lambda _cwd, repo, branch: (None, "GitHub unavailable"),
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "full gate required")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "full gate required"


def test_unverifiable_posture_never_skips_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    def fail_posture(_cwd: Path):
        raise RuntimeError("posture unavailable")

    monkeypatch.setattr(completion, "check_repository_posture", fail_posture)
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "full gate required")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "full gate required"


def test_blocked_posture_never_skips_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        completion, "check_repository_posture", lambda _cwd: _report("BLOCKED")
    )
    monkeypatch.setattr(
        completion, "_run_completion_gate", lambda _cwd: (False, "blocked delivery")
    )

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "blocked delivery"
