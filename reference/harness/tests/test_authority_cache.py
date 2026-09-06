from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from reference.harness import common


def _raw(tmp_path: Path) -> dict:
    return {"cwd": str(tmp_path), "session_id": "authority-cache-test"}


def test_enforcement_refresh_does_not_trust_cached_ready_report(tmp_path: Path, monkeypatch) -> None:
    cached = SimpleNamespace(
        state="READY",
        repo_root=str(tmp_path),
        checked_at=10**12,
        ttl_seconds=3600,
    )
    refreshed = SimpleNamespace(state="BLOCKED")

    monkeypatch.setattr(common, "load_cached_posture", lambda _session_id: cached)
    monkeypatch.setattr(common, "refresh_repository_posture", lambda _raw: refreshed)

    result = common.current_repository_posture(_raw(tmp_path), refresh_if_stale=True)
    assert result is refreshed
    assert result.state == "BLOCKED"


def test_read_only_cache_lookup_remains_non_authoritative_context(tmp_path: Path, monkeypatch) -> None:
    cached = SimpleNamespace(
        state="READY",
        repo_root=str(tmp_path.resolve()),
        checked_at=0.0,
        ttl_seconds=0,
    )
    monkeypatch.setattr(common, "load_cached_posture", lambda _session_id: cached)
    monkeypatch.setattr(common, "_active_repo_root", lambda _cwd: str(tmp_path.resolve()))

    result = common.current_repository_posture(_raw(tmp_path), refresh_if_stale=False)
    assert result is None
