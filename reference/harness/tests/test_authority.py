from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from reference.harness import authority
from reference.hooks.policy_engine import Decision


def _raw(tmp_path: Path) -> dict:
    return {"cwd": str(tmp_path), "session_id": "authority-test"}


def _report(state: str, tmp_path: Path):
    return SimpleNamespace(
        state=state,
        repo_root=str(tmp_path.resolve()),
        checked_at=10**12,
        ttl_seconds=3600,
        summary=lambda: f"repository posture {state}",
    )


def test_authority_refresh_does_not_trust_cached_ready_report(
    tmp_path: Path, monkeypatch
) -> None:
    cached = _report("READY", tmp_path)
    refreshed = _report("BLOCKED", tmp_path)
    monkeypatch.setattr(authority, "load_cached_posture", lambda _session_id: cached)
    monkeypatch.setattr(authority, "refresh_repository_posture", lambda _raw: refreshed)

    result = authority.current_repository_posture(
        _raw(tmp_path), refresh_for_authority=True
    )
    assert result is refreshed
    assert result.state == "BLOCKED"


def test_context_cache_is_not_used_when_expired(tmp_path: Path, monkeypatch) -> None:
    cached = SimpleNamespace(
        state="READY",
        repo_root=str(tmp_path.resolve()),
        checked_at=0.0,
        ttl_seconds=0,
    )
    monkeypatch.setattr(authority, "load_cached_posture", lambda _session_id: cached)
    monkeypatch.setattr(
        authority, "_active_repo_root", lambda _cwd: str(tmp_path.resolve())
    )

    assert (
        authority.current_repository_posture(
            _raw(tmp_path), refresh_for_authority=False
        )
        is None
    )


def test_blocked_authority_denies_mutation_before_approval(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        authority,
        "current_repository_posture",
        lambda *args, **kwargs: _report("BLOCKED", tmp_path),
    )
    result = authority.enforce_repository_authority(
        _raw(tmp_path),
        Decision("ask", "ordinary approval", "approval"),
        mutation=True,
    )
    assert result.decision == "deny"
    assert result.rule == "repository-authority"


def test_blocked_authority_does_not_change_read_only_decision(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        authority,
        "current_repository_posture",
        lambda *args, **kwargs: _report("BLOCKED", tmp_path),
    )
    result = authority.enforce_repository_authority(
        _raw(tmp_path),
        Decision("allow", "read only", "read-only"),
        mutation=False,
    )
    assert result.decision == "allow"


def test_restricted_authority_allows_nonrestricted_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        authority,
        "current_repository_posture",
        lambda *args, **kwargs: _report("RESTRICTED", tmp_path),
    )
    result = authority.enforce_repository_authority(
        _raw(tmp_path),
        Decision("allow", "local mutation", "local"),
        mutation=True,
        restricted_operation=False,
    )
    assert result.decision == "allow"


def test_restricted_authority_denies_caller_classified_restricted_operation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        authority,
        "current_repository_posture",
        lambda *args, **kwargs: _report("RESTRICTED", tmp_path),
    )
    result = authority.enforce_repository_authority(
        _raw(tmp_path),
        Decision("allow", "candidate", "candidate"),
        mutation=True,
        restricted_operation=True,
    )
    assert result.decision == "deny"
    assert result.rule == "repository-authority"


def test_missing_authority_fails_closed_only_for_restricted_operation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        authority,
        "current_repository_posture",
        lambda *args, **kwargs: None,
    )
    ordinary = authority.enforce_repository_authority(
        _raw(tmp_path),
        Decision("allow", "local mutation", "local"),
        mutation=True,
        restricted_operation=False,
    )
    restricted = authority.enforce_repository_authority(
        _raw(tmp_path),
        Decision("allow", "remote mutation", "remote"),
        mutation=True,
        restricted_operation=True,
    )
    assert ordinary.decision == "allow"
    assert restricted.decision == "deny"
