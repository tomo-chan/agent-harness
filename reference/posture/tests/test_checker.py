from __future__ import annotations

import json
import subprocess
from pathlib import Path

from reference.posture.checker import (
    RepositorySecurityPolicy,
    _active_rule_types,
    _state_for,
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
    from reference.posture.checker import Check

    checks = {"x": Check("unknown", "cannot verify")}
    assert _state_for("strict", checks) == "BLOCKED"
    assert _state_for("restricted", checks) == "RESTRICTED"
    assert _state_for("warn", checks) == "READY"


def test_active_rules_apply_to_default_branch() -> None:
    rulesets = [
        {
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
            "rules": [
                {"type": "pull_request"},
                {"type": "non_fast_forward"},
                {"type": "required_status_checks"},
            ],
        }
    ]
    assert _active_rule_types(rulesets, "main") == {
        "pull_request",
        "non_fast_forward",
        "required_status_checks",
    }


def test_disabled_rules_do_not_count() -> None:
    rulesets = [
        {
            "enforcement": "disabled",
            "conditions": {"ref_name": {"include": ["~ALL"], "exclude": []}},
            "rules": [{"type": "pull_request"}],
        }
    ]
    assert _active_rule_types(rulesets, "main") == set()
