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


def test_full_check_ready_when_effective_rules_are_present(tmp_path: Path) -> None:
    def runner(command, cwd):
        key = tuple(command)
        if key == ("git", "rev-parse", "--show-toplevel"):
            return _completed(command, f"{tmp_path}\n")
        if key == ("git", "remote", "get-url", "origin"):
            return _completed(command, "https://github.com/acme/widget.git\n")
        if key == ("gh", "api", "repos/acme/widget"):
            return _completed(command, json.dumps({"default_branch": "main"}))
        if key == ("gh", "api", "repos/acme/widget/rules/branches/main"):
            return _completed(command, json.dumps([
                {"type": "pull_request"},
                {"type": "non_fast_forward"},
                {"type": "required_status_checks"},
            ]))
        raise AssertionError(f"unexpected command: {command}")

    report = check_repository_posture(tmp_path, runner)
    assert report.state == "READY"
    assert report.repository == "acme/widget"
    assert report.default_branch == "main"


def test_full_check_restricted_when_rules_cannot_be_verified(tmp_path: Path) -> None:
    def runner(command, cwd):
        key = tuple(command)
        if key == ("git", "rev-parse", "--show-toplevel"):
            return _completed(command, f"{tmp_path}\n")
        if key == ("git", "remote", "get-url", "origin"):
            return _completed(command, "https://github.com/acme/widget.git\n")
        if key == ("gh", "api", "repos/acme/widget"):
            return _completed(command, json.dumps({"default_branch": "main"}))
        if key == ("gh", "api", "repos/acme/widget/rules/branches/main"):
            return _completed(command, stderr="HTTP 403", code=1)
        raise AssertionError(f"unexpected command: {command}")

    report = check_repository_posture(tmp_path, runner)
    assert report.state == "RESTRICTED"
    assert report.checks["require_pull_request"].status == "unknown"
