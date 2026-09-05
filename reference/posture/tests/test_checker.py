from __future__ import annotations

import json
import subprocess
from pathlib import Path

from reference.posture.checker import (
    Check,
    RepositorySecurityPolicy,
    _state_for,
    check_repository_posture,
    parse_github_repository,
)


def test_parse_github_repository_https_and_ssh() -> None:
    assert parse_github_repository("https://github.com/acme/widget.git") == "acme/widget"
    assert parse_github_repository("git@github.com:acme/widget.git") == "acme/widget"
    assert parse_github_repository("https://example.com/acme/widget.git") is None


def test_policy_defaults_to_restricted() -> None:
    policy = RepositorySecurityPolicy.from_mapping({})
    assert policy.mode == "restricted"
    assert policy.requirements["require_pull_request"] is True


def test_state_modes() -> None:
    checks = {"x": Check("unknown", "cannot verify")}
    assert _state_for("strict", checks) == "BLOCKED"
    assert _state_for("restricted", checks) == "RESTRICTED"
    assert _state_for("warn", checks) == "READY"


def _completed(args, stdout="", stderr="", code=0):
    return subprocess.CompletedProcess(args, code, stdout=stdout, stderr=stderr)


def _runner(tmp_path: Path, *, rules_ok: bool = True):
    def runner(command, cwd):
        key = tuple(command)
        if key == ("git", "rev-parse", "--show-toplevel"):
            return _completed(command, f"{tmp_path}\n")
        if key == ("git", "remote", "get-url", "origin"):
            return _completed(command, "https://github.com/acme/widget.git\n")
        if key == ("gh", "api", "repos/acme/widget"):
            return _completed(command, json.dumps({"default_branch": "main"}))
        if key == ("gh", "api", "repos/acme/widget/rules/branches/main"):
            if not rules_ok:
                return _completed(command, stderr="HTTP 403", code=1)
            return _completed(command, json.dumps([
                {"type": "pull_request"},
                {"type": "non_fast_forward"},
                {"type": "required_status_checks"},
            ]))
        raise AssertionError(f"unexpected command: {command}")
    return runner


def test_full_check_ready_when_trusted_identity_and_rules_are_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    report = check_repository_posture(tmp_path, _runner(tmp_path))
    assert report.state == "READY"
    assert report.repository == "acme/widget"
    assert report.default_branch == "main"
    assert report.checks["trusted_repository_identity"].status == "pass"


def test_missing_trusted_repository_keeps_default_profile_restricted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGENT_HARNESS_EXPECTED_REPOSITORY", raising=False)
    report = check_repository_posture(tmp_path, _runner(tmp_path))
    assert report.state == "RESTRICTED"
    assert report.checks["trusted_repository_identity"].status == "unknown"


def test_trusted_repository_mismatch_is_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/other")
    report = check_repository_posture(tmp_path, _runner(tmp_path))
    assert report.state == "BLOCKED"
    assert report.checks["trusted_repository_identity"].status == "fail"


def test_full_check_restricted_when_rules_cannot_be_verified(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    report = check_repository_posture(tmp_path, _runner(tmp_path, rules_ok=False))
    assert report.state == "RESTRICTED"
    assert report.checks["require_pull_request"].status == "unknown"


def test_repository_warn_cannot_weaken_default_minimum_restricted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    policy_dir = tmp_path / ".agent-harness"
    policy_dir.mkdir()
    (policy_dir / "security.json").write_text(
        json.dumps({"mode": "warn"}), encoding="utf-8"
    )
    report = check_repository_posture(tmp_path, _runner(tmp_path, rules_ok=False))
    assert report.mode == "restricted"
    assert report.state == "RESTRICTED"


def test_trusted_launcher_can_explicitly_lower_minimum_for_interactive_use(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    monkeypatch.setenv("AGENT_HARNESS_MINIMUM_POSTURE_MODE", "warn")
    policy_dir = tmp_path / ".agent-harness"
    policy_dir.mkdir()
    (policy_dir / "security.json").write_text(
        json.dumps({"mode": "warn"}), encoding="utf-8"
    )
    report = check_repository_posture(tmp_path, _runner(tmp_path, rules_ok=False))
    assert report.mode == "warn"
    assert report.state == "READY"
