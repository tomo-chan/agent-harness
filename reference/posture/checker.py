"""Evaluate and cache repository security posture for autonomous agent sessions.

Repository posture is an authority state derived from trusted launcher identity,
a trusted minimum policy, repository-local strengthening requirements, local Git
state, and effective GitHub rules. The checker preserves pass/fail/unknown
evidence instead of silently treating unavailable external state as success.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import quote, urlparse

CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]

DEFAULT_POLICY: dict[str, Any] = {
    "mode": "restricted",
    "ttl_seconds": 300,
    "requirements": {
        "github_remote": True,
        "require_pull_request": True,
        "block_force_push": True,
        "required_status_checks": True,
    },
}
MODE_RANK = {"warn": 0, "restricted": 1, "strict": 2}


@dataclass(frozen=True)
class Check:
    """One posture evidence item with pass, fail, or unknown status."""

    status: str
    detail: str


@dataclass(frozen=True)
class RepositorySecurityPolicy:
    """Normalized repository posture requirements and cache behavior."""

    mode: str
    ttl_seconds: int
    requirements: dict[str, bool]
    expected_repository: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "RepositorySecurityPolicy":
        """Validate a complete policy mapping and apply built-in defaults."""
        mode = str(value.get("mode", "restricted"))
        if mode not in MODE_RANK:
            raise ValueError("mode must be strict, restricted, or warn")
        ttl = int(value.get("ttl_seconds", 300))
        if ttl < 0:
            raise ValueError("ttl_seconds must be >= 0")
        requirements = dict(DEFAULT_POLICY["requirements"])
        supplied = value.get("requirements", {})
        if not isinstance(supplied, dict):
            raise ValueError("requirements must be an object")
        for key, item in supplied.items():
            if key not in requirements:
                raise ValueError(f"unknown repository security requirement: {key}")
            requirements[key] = bool(item)
        expected = value.get("expected_repository")
        return cls(mode, ttl, requirements, str(expected) if expected else None)

    @classmethod
    def from_overlay(cls, value: dict[str, Any]) -> "RepositorySecurityPolicy":
        """Validate a repository overlay without inventing weakening defaults.

        Missing requirements are represented as ``False`` because the overlay is
        combined monotonically with the trusted baseline. ``warn`` is the neutral
        mode and a large default TTL is neutral when the effective TTL is the
        minimum of both inputs.
        """
        mode = str(value.get("mode", "warn"))
        if mode not in MODE_RANK:
            raise ValueError("mode must be strict, restricted, or warn")
        ttl = int(value.get("ttl_seconds", 2**31 - 1))
        if ttl < 0:
            raise ValueError("ttl_seconds must be >= 0")
        requirements = {key: False for key in DEFAULT_POLICY["requirements"]}
        supplied = value.get("requirements", {})
        if not isinstance(supplied, dict):
            raise ValueError("requirements must be an object")
        for key, item in supplied.items():
            if key not in requirements:
                raise ValueError(f"unknown repository security requirement: {key}")
            requirements[key] = bool(item)
        expected = value.get("expected_repository")
        return cls(mode, ttl, requirements, str(expected) if expected else None)

    @staticmethod
    def _read_mapping(path: Path) -> dict[str, Any]:
        """Read one JSON policy file and require an object at its root."""
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("repository security policy must be a JSON object")
        return value

    @classmethod
    def load_effective(cls, repo_root: Path) -> tuple["RepositorySecurityPolicy", str]:
        """Combine trusted launcher policy and repository overlay monotonically.

        ``AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY`` supplies the trusted
        baseline file. A trusted launcher may explicitly override only the
        baseline mode through ``AGENT_HARNESS_MINIMUM_POSTURE_MODE``; this keeps
        the established interactive ``warn`` use case while requirements and TTL
        remain anchored in the trusted baseline file. The repository overlay at
        ``.agent-harness/security.json`` may then strengthen mode or requirements,
        shorten TTL, and add an expected-repository consistency claim, but cannot
        weaken the resulting trusted baseline.
        """
        trusted_path_value = os.environ.get("AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY")
        if trusted_path_value:
            trusted_path = Path(trusted_path_value)
            if not trusted_path.is_file():
                raise ValueError(f"trusted repository security policy does not exist: {trusted_path}")
            baseline = cls.from_mapping(cls._read_mapping(trusted_path))
            trusted_source = str(trusted_path)
        else:
            baseline = cls.from_mapping(DEFAULT_POLICY)
            trusted_source = "built-in restricted defaults"

        launcher_mode = os.environ.get("AGENT_HARNESS_MINIMUM_POSTURE_MODE")
        if launcher_mode is not None:
            if launcher_mode not in MODE_RANK:
                raise ValueError("AGENT_HARNESS_MINIMUM_POSTURE_MODE must be strict, restricted, or warn")
            baseline = cls(
                launcher_mode,
                baseline.ttl_seconds,
                dict(baseline.requirements),
                baseline.expected_repository,
            )
            trusted_source = f"{trusted_source}; launcher_mode={launcher_mode}"

        overlay_path = repo_root / ".agent-harness" / "security.json"
        if not overlay_path.exists():
            return baseline, f"trusted={trusted_source}; repository=missing"

        overlay = cls.from_overlay(cls._read_mapping(overlay_path))
        mode = baseline.mode if MODE_RANK[baseline.mode] >= MODE_RANK[overlay.mode] else overlay.mode
        requirements = {
            key: baseline.requirements[key] or overlay.requirements[key]
            for key in baseline.requirements
        }
        ttl_seconds = min(baseline.ttl_seconds, overlay.ttl_seconds)
        effective = cls(mode, ttl_seconds, requirements, overlay.expected_repository)
        return effective, f"trusted={trusted_source}; repository={overlay_path}"


@dataclass(frozen=True)
class PostureReport:
    """Repository authority state together with the evidence used to derive it."""

    state: str
    repository: str | None
    repo_root: str
    default_branch: str | None
    mode: str
    ttl_seconds: int
    policy_source: str
    checked_at: float
    checks: dict[str, Check]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report for the session posture cache."""
        value = asdict(self)
        value["checks"] = {name: asdict(check) for name, check in self.checks.items()}
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PostureReport":
        """Reconstruct a posture report from cached serialized data."""
        checks = {name: Check(**check) for name, check in value.get("checks", {}).items()}
        return cls(
            state=value["state"], repository=value.get("repository"), repo_root=value["repo_root"],
            default_branch=value.get("default_branch"), mode=value["mode"],
            ttl_seconds=int(value.get("ttl_seconds", 300)),
            policy_source=value.get("policy_source", "unknown"), checked_at=float(value["checked_at"]),
            checks=checks,
        )

    def summary(self) -> str:
        """Return a concise human- and agent-readable posture explanation."""
        problems = [f"{name}={check.status} ({check.detail})" for name, check in self.checks.items() if check.status != "pass"]
        suffix = "; ".join(problems) if problems else "all required checks passed"
        return f"repository posture {self.state}: {suffix}"


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one bounded local command used to collect posture evidence."""
    return subprocess.run(list(command), cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=15)


def _stdout(runner: CommandRunner, command: Sequence[str], cwd: Path) -> tuple[str | None, str | None]:
    """Run a command and normalize its result into ``(stdout, error)``."""
    try:
        result = runner(command, cwd)
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout.strip(), None


def _repo_root(cwd: Path, runner: CommandRunner) -> Path:
    """Resolve the active Git repository root or fail when outside a repository."""
    output, error = _stdout(runner, ["git", "rev-parse", "--show-toplevel"], cwd)
    if error or not output:
        raise RuntimeError(f"not inside a Git repository: {error or 'unknown error'}")
    return Path(output).resolve()


def parse_github_repository(remote: str) -> str | None:
    """Parse a github.com SSH or URL remote into canonical ``owner/repository`` form."""
    remote = remote.strip()
    ssh = re.fullmatch(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?", remote)
    if ssh:
        return f"{ssh.group(1)}/{ssh.group(2)}".removesuffix(".git")
    parsed = urlparse(remote)
    if parsed.hostname != "github.com":
        return None
    path = parsed.path.strip("/").removesuffix(".git")
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else None


def _state_for(mode: str, checks: dict[str, Check]) -> str:
    """Derive READY, RESTRICTED, or BLOCKED from mode and three-valued evidence."""
    problem = any(check.status in {"fail", "unknown"} for check in checks.values())
    if not problem:
        return "READY"
    if mode == "strict":
        return "BLOCKED"
    if mode == "restricted":
        return "RESTRICTED"
    return "READY"


def _effective_rule_types(repository: str, default_branch: str, root: Path, runner: CommandRunner) -> tuple[set[str] | None, str | None]:
    """Read active GitHub rule types that currently apply to the default branch."""
    endpoint = f"repos/{repository}/rules/branches/{quote(default_branch, safe='')}"
    raw, error = _stdout(runner, ["gh", "api", endpoint], root)
    if raw is None:
        return None, error
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return None, f"invalid branch-rules JSON: {exc}"
    if not isinstance(parsed, list):
        return None, "branch-rules response is not an array"
    return {str(rule["type"]) for rule in parsed if isinstance(rule, dict) and rule.get("type")}, None


def check_repository_posture(cwd: Path | str, runner: CommandRunner = _run) -> PostureReport:
    """Evaluate trusted repository identity and required GitHub protections.

    Invalid trusted or repository policy fails closed to BLOCKED. Missing or
    unavailable external evidence remains ``unknown`` and is interpreted by the
    effective mode. Repository-local policy can strengthen but never weaken the
    trusted baseline. A trusted repository identity mismatch is always BLOCKED.
    """
    cwd = Path(cwd).resolve()
    root = _repo_root(cwd, runner)
    try:
        policy, source = RepositorySecurityPolicy.load_effective(root)
    except Exception as exc:
        return PostureReport(
            state="BLOCKED", repository=None, repo_root=str(root), default_branch=None,
            mode="strict", ttl_seconds=0, policy_source="invalid", checked_at=time.time(),
            checks={"policy": Check("fail", f"invalid security policy: {exc}")},
        )

    checks: dict[str, Check] = {}
    remote, remote_error = _stdout(runner, ["git", "remote", "get-url", "origin"], root)
    repository = parse_github_repository(remote or "") if remote else None
    if policy.requirements["github_remote"]:
        if repository:
            checks["github_remote"] = Check("pass", repository)
        elif remote_error:
            checks["github_remote"] = Check("unknown", remote_error)
        else:
            checks["github_remote"] = Check("fail", f"origin is not a github.com repository: {remote}")

    trusted_expected = os.environ.get("AGENT_HARNESS_EXPECTED_REPOSITORY")
    if trusted_expected:
        status = "pass" if repository == trusted_expected else "fail"
        checks["trusted_repository_identity"] = Check(status, f"expected {trusted_expected}; found {repository}")
    else:
        checks["trusted_repository_identity"] = Check("unknown", "trusted launcher did not provide AGENT_HARNESS_EXPECTED_REPOSITORY")

    if policy.expected_repository:
        status = "pass" if repository == policy.expected_repository else "fail"
        checks["repository_declared_identity"] = Check(status, f"repository policy expected {policy.expected_repository}; found {repository}")
        if trusted_expected and policy.expected_repository != trusted_expected:
            checks["repository_policy_conflict"] = Check("fail", f"repository policy expects {policy.expected_repository} but trusted launcher expects {trusted_expected}")

    default_branch: str | None = None
    metadata_error: str | None = None
    if repository:
        raw, metadata_error = _stdout(runner, ["gh", "api", f"repos/{repository}"], root)
        if raw:
            try:
                metadata = json.loads(raw)
                default_branch = str(metadata.get("default_branch") or "") or None
            except Exception as exc:
                metadata_error = f"invalid repository metadata JSON: {exc}"
    if default_branch:
        checks["github_metadata"] = Check("pass", f"default branch {default_branch}")
    else:
        checks["github_metadata"] = Check("unknown", metadata_error or "GitHub repository/default branch unavailable")

    rule_types: set[str] | None = None
    rules_error: str | None = None
    if repository and default_branch:
        rule_types, rules_error = _effective_rule_types(repository, default_branch, root, runner)

    requirements = {
        "require_pull_request": "pull_request",
        "block_force_push": "non_fast_forward",
        "required_status_checks": "required_status_checks",
    }
    for requirement, rule_type in requirements.items():
        if not policy.requirements[requirement]:
            continue
        if rule_types is None:
            checks[requirement] = Check("unknown", rules_error or "effective branch rules unavailable")
        elif rule_type in rule_types:
            checks[requirement] = Check("pass", f"active {rule_type} rule applies to {default_branch}")
        else:
            checks[requirement] = Check("fail", f"no active {rule_type} rule applies to {default_branch}")

    state = _state_for(policy.mode, checks)
    for key in ("trusted_repository_identity", "repository_declared_identity", "repository_policy_conflict"):
        if checks.get(key, Check("pass", "")).status == "fail":
            state = "BLOCKED"

    return PostureReport(
        state, repository, str(root), default_branch, policy.mode, policy.ttl_seconds,
        source, time.time(), checks,
    )


def _state_path(session_id: str) -> Path:
    """Derive a filesystem-safe private cache path from a session identifier."""
    base = Path(os.environ.get("AGENT_HARNESS_STATE_DIR", str(Path(tempfile.gettempdir()) / "agent-harness" / "posture")))
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return base / f"{digest}.json"


def save_cached_posture(session_id: str, report: PostureReport) -> None:
    """Atomically persist a posture report with restrictive filesystem permissions."""
    path = _state_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(report.to_dict(), separators=(",", ":")), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


def load_cached_posture(session_id: str) -> PostureReport | None:
    """Load a cached posture report, returning ``None`` for missing or invalid cache data."""
    path = _state_path(session_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return PostureReport.from_dict(value)
    except (FileNotFoundError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
