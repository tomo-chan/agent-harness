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


def _write_trusted_policy(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "trusted-security.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _write_repository_overlay(tmp_path: Path, value: dict) -> Path:
    directory = tmp_path / ".agent-harness"
    directory.mkdir(exist_ok=True)
    path = directory / "security.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


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


def test_trusted_launcher_can_explicitly_lower_mode_for_interactive_use(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    trusted = _write_trusted_policy(tmp_path, {"mode": "restricted"})
    monkeypatch.setenv("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY", str(trusted))
    monkeypatch.setenv("AGENT_HARNESS_MINIMUM_POSTURE_MODE", "warn")
    _write_repository_overlay(tmp_path, {"mode": "warn"})
    report = check_repository_posture(tmp_path, _runner(tmp_path, rules_ok=False))
    assert report.mode == "warn"
    assert report.state == "READY"
    assert "launcher_mode=warn" in report.policy_source


def test_repository_cannot_weaken_trusted_launcher_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    trusted = _write_trusted_policy(tmp_path, {"mode": "warn"})
    monkeypatch.setenv("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY", str(trusted))
    monkeypatch.setenv("AGENT_HARNESS_MINIMUM_POSTURE_MODE", "strict")
    _write_repository_overlay(tmp_path, {"mode": "warn"})
    report = check_repository_posture(tmp_path, _runner(tmp_path, rules_ok=False))
    assert report.mode == "strict"
    assert report.state == "BLOCKED"


def test_invalid_trusted_launcher_mode_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    monkeypatch.setenv("AGENT_HARNESS_MINIMUM_POSTURE_MODE", "invalid")
    report = check_repository_posture(tmp_path, _runner(tmp_path))
    assert report.state == "BLOCKED"
    assert report.checks["policy"].status == "fail"


def test_repository_warn_cannot_weaken_trusted_restricted_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    trusted = _write_trusted_policy(tmp_path, {"mode": "restricted"})
    monkeypatch.setenv("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY", str(trusted))
    _write_repository_overlay(tmp_path, {"mode": "warn"})
    report = check_repository_posture(tmp_path, _runner(tmp_path, rules_ok=False))
    assert report.mode == "restricted"
    assert report.state == "RESTRICTED"


def test_repository_can_strengthen_trusted_warn_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    trusted = _write_trusted_policy(tmp_path, {
        "mode": "warn",
        "requirements": {
            "github_remote": True,
            "require_pull_request": False,
            "block_force_push": False,
            "required_status_checks": False,
        },
    })
    monkeypatch.setenv("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY", str(trusted))
    _write_repository_overlay(tmp_path, {
        "mode": "strict",
        "requirements": {"require_pull_request": True},
    })
    report = check_repository_posture(tmp_path, _runner(tmp_path, rules_ok=False))
    assert report.mode == "strict"
    assert report.state == "BLOCKED"
    assert "require_pull_request" in report.checks


def test_repository_false_requirement_cannot_disable_trusted_true_requirement(tmp_path: Path, monkeypatch) -> None:
    trusted = _write_trusted_policy(tmp_path, {
        "requirements": {"required_status_checks": True},
    })
    monkeypatch.setenv("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY", str(trusted))
    _write_repository_overlay(tmp_path, {
        "requirements": {"required_status_checks": False},
    })
    policy, _ = RepositorySecurityPolicy.load_effective(tmp_path)
    assert policy.requirements["required_status_checks"] is True


def test_repository_can_add_requirement_not_required_by_trusted_baseline(tmp_path: Path, monkeypatch) -> None:
    trusted = _write_trusted_policy(tmp_path, {
        "requirements": {
            "github_remote": True,
            "require_pull_request": False,
            "block_force_push": False,
            "required_status_checks": False,
        },
    })
    monkeypatch.setenv("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY", str(trusted))
    _write_repository_overlay(tmp_path, {
        "requirements": {"required_status_checks": True},
    })
    policy, _ = RepositorySecurityPolicy.load_effective(tmp_path)
    assert policy.requirements["required_status_checks"] is True


def test_repository_can_only_shorten_posture_cache_ttl(tmp_path: Path, monkeypatch) -> None:
    trusted = _write_trusted_policy(tmp_path, {"ttl_seconds": 120})
    monkeypatch.setenv("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY", str(trusted))
    _write_repository_overlay(tmp_path, {"ttl_seconds": 600})
    policy, _ = RepositorySecurityPolicy.load_effective(tmp_path)
    assert policy.ttl_seconds == 120

    _write_repository_overlay(tmp_path, {"ttl_seconds": 30})
    policy, _ = RepositorySecurityPolicy.load_effective(tmp_path)
    assert policy.ttl_seconds == 30


def test_repository_declared_identity_is_additional_consistency_check(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    _write_repository_overlay(tmp_path, {"expected_repository": "acme/other"})
    report = check_repository_posture(tmp_path, _runner(tmp_path))
    assert report.state == "BLOCKED"
    assert report.checks["repository_policy_conflict"].status == "fail"


def test_invalid_repository_overlay_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HARNESS_EXPECTED_REPOSITORY", "acme/widget")
    _write_repository_overlay(tmp_path, {"mode": "invalid"})
    report = check_repository_posture(tmp_path, _runner(tmp_path))
    assert report.state == "BLOCKED"
    assert report.checks["policy"].status == "fail"
