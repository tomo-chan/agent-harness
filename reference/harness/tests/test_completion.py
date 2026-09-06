from __future__ import annotations

import json
from pathlib import Path

import pytest

from reference.harness import completion


def _raw(tmp_path: Path) -> dict:
    return {"cwd": str(tmp_path), "session_id": "completion-test"}


def test_unchanged_repository_state_is_read_only_and_skips_gate(tmp_path: Path, monkeypatch) -> None:
    snapshots = [
        ({"repo_root": str(tmp_path), "head": "abc", "status": ""}, None),
        ({"repo_root": str(tmp_path), "head": "abc", "status": ""}, None),
    ]
    monkeypatch.setattr(completion, "_snapshot", lambda _cwd: snapshots.pop(0))
    monkeypatch.setenv("AGENT_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: pytest.fail("gate must not run"))

    completion.capture_session_start(_raw(tmp_path))
    ok, reason = completion.completion_check(_raw(tmp_path))

    assert ok is True
    assert "read-only session" in reason


def test_changed_head_runs_full_completion_gate(tmp_path: Path, monkeypatch) -> None:
    snapshots = [
        ({"repo_root": str(tmp_path), "head": "abc", "status": ""}, None),
        ({"repo_root": str(tmp_path), "head": "def", "status": ""}, None),
    ]
    monkeypatch.setattr(completion, "_snapshot", lambda _cwd: snapshots.pop(0))
    monkeypatch.setenv("AGENT_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (False, "delivery gate failed"))

    completion.capture_session_start(_raw(tmp_path))
    ok, reason = completion.completion_check(_raw(tmp_path))

    assert ok is False
    assert reason == "delivery gate failed"


def test_changed_worktree_runs_full_completion_gate(tmp_path: Path, monkeypatch) -> None:
    snapshots = [
        ({"repo_root": str(tmp_path), "head": "abc", "status": ""}, None),
        ({"repo_root": str(tmp_path), "head": "abc", "status": " M src/app.py\n"}, None),
    ]
    monkeypatch.setattr(completion, "_snapshot", lambda _cwd: snapshots.pop(0))
    monkeypatch.setenv("AGENT_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (True, "delivery gate passed"))

    completion.capture_session_start(_raw(tmp_path))
    ok, reason = completion.completion_check(_raw(tmp_path))

    assert ok is True
    assert reason == "delivery gate passed"


def test_missing_baseline_never_assumes_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(
        completion,
        "_snapshot",
        lambda _cwd: ({"repo_root": str(tmp_path), "head": "abc", "status": ""}, None),
    )
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (False, "full gate required"))

    ok, reason = completion.completion_check(_raw(tmp_path))

    assert ok is False
    assert reason == "full gate required"


def test_invalid_baseline_never_assumes_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_STATE_DIR", str(tmp_path / "state"))
    path = completion._state_path("completion-test")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"repo_root": str(tmp_path)}), encoding="utf-8")
    monkeypatch.setattr(
        completion,
        "_snapshot",
        lambda _cwd: ({"repo_root": str(tmp_path), "head": "abc", "status": ""}, None),
    )
    monkeypatch.setattr(completion, "_run_completion_gate", lambda _cwd: (False, "full gate required"))

    ok, reason = completion.completion_check(_raw(tmp_path))

    assert ok is False
    assert reason == "full gate required"
