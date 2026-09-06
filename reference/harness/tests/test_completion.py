from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from reference.harness import completion


def _raw(tmp_path: Path) -> dict:
    return {"cwd": str(tmp_path), "session_id": "completion-test"}


def _report(state: str = "READY", default_branch: str = "main") -> SimpleNamespace:
    return SimpleNamespace(
        state=state,
        default_branch=default_branch,
        summary=lambda: f"repository posture {state}",
    )


def test_session_start_does_not_persist_authoritative_completion_state(tmp_path: Path) -> None:
    reason = completion.capture_session_start(_raw(tmp_path))
    assert "re-evaluate authoritative repository state at Stop" in reason


def test_clean_checked_default_branch_skips_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())

    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): ("main", None),
            ("status", "--porcelain=v1", "--untracked-files=all"): ("", None),
            ("rev-parse", "HEAD"): ("abc", None),
            ("rev-parse", "origin/main"): ("abc", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: pytest.fail("gate must not run"))

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is True
    assert "read-only repository state" in reason


def test_feature_branch_runs_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())
    monkeypatch.setattr(
        completion,
        "_run_git",
        lambda _cwd, args: ("feature/x", None) if tuple(args) == ("branch", "--show-current") else pytest.fail(str(args)),
    )
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (True, "delivery gate passed"))

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is True
    assert reason == "delivery gate passed"


def test_dirty_default_branch_runs_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report())

    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): ("main", None),
            ("status", "--porcelain=v1", "--untracked-files=all"): (" M src/app.py", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (False, "dirty delivery"))

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
            ("rev-parse", "origin/main"): ("remote", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(completion, "_run_git", fake_git)
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (False, "diverged delivery"))

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "diverged delivery"


def test_unverifiable_posture_never_skips_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    def fail_posture(_cwd: Path):
        raise RuntimeError("posture unavailable")

    monkeypatch.setattr(completion, "check_repository_posture", fail_posture)
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (False, "full gate required"))

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "full gate required"


def test_blocked_posture_never_skips_delivery_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(completion, "check_repository_posture", lambda _cwd: _report("BLOCKED"))
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (False, "blocked delivery"))

    ok, reason = completion.completion_check(_raw(tmp_path))
    assert ok is False
    assert reason == "blocked delivery"
