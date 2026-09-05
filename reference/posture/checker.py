from __future__ import annotations

import fnmatch
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
from urllib.parse import urlparse

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


@dataclass(frozen=True)
class Check:
    status: str  # pass | fail | unknown
    detail: str


@dataclass(frozen=True)
class RepositorySecurityPolicy:
    mode: str
    ttl_seconds: int
    requirements: dict[str, bool]
    expected_repository: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "RepositorySecurityPolicy":
        mode = str(value.get("mode", "restricted"))
        if mode not in {"strict", "restricted", "warn"}:
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
    def load(cls, repo_root: Path) -> tuple["RepositorySecurityPolicy", str]:
        explicit = os.environ.get("AGENT_HARNESS_REPOSITORY_SECURITY_POLICY")
        path = Path(explicit) if explicit else repo_root / ".agent-harness" / "security.json"
        if not path.exists():
            return cls.from_mapping(DEFAULT_POLICY), "built-in restricted defaults (config missing)"
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("repository security policy must be a JSON object")
        return cls.from_mapping(value), str(path)


@dataclass(frozen=True)
class PostureReport:
    state: str  # READY | RESTRICTED | BLOCKED
    repository: str | None
    repo_root: str
    default_branch: str | None
    mode: str
    policy_source: str
    checked_at: float
    checks: dict[str, Check]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["checks"] = {name: asdict(check) for name, check in self.checks.items()}
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PostureReport":
        checks = {name: Check(**check) for name, check in value.get("checks", {}).items()}
        return cls(
            state=value["state"],
            repository=value.get("repository"),
            repo_root=value["repo_root"],
            default_branch=value.get("default_branch"),
            mode=value["mode"],
            policy_source=value.get("policy_source", "unknown"),
            checked_at=float(value["checked_at"]),
            checks=checks,
        )

    def summary(self) -> str:
        problems = [f"{name}={check.status} ({check.detail})" for name, check in self.checks.items() if check.status != "pass"]
        suffix = "; ".join(problems) if problems else "all required checks passed"
        return f"repository posture {self.state}: {suffix}"


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command), cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=15
    )


def _stdout(runner: CommandRunner, command: Sequence[str], cwd: Path) -> tuple[str | None, str | None]:
    try:
        result = runner(command, cwd)
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout.strip(), None


def _repo_root(cwd: Path, runner: CommandRunner) -> Path:
    output, error = _stdout(runner, ["git", "rev-parse", "--show-toplevel"], cwd)
    if error or not output:
        raise RuntimeError(f"not inside a Git repository: {error or 'unknown error'}")
    return Path(output).resolve()


def parse_github_repository(remote: str) -> str | None:
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


def _ref_matches(rule: dict[str, Any], default_branch: str) -> bool:
    ref = f"refs/heads/{default_branch}"
    condition = rule.get("conditions", {}).get("ref_name")
    if not isinstance(condition, dict):
        return True
    includes = condition.get("include") or []
    excludes = condition.get("exclude") or []

    def matches(pattern: str) -> bool:
        if pattern in {"~ALL", "~DEFAULT_BRANCH"}:
            return pattern == "~ALL" or bool(default_branch)
        return fnmatch.fnmatch(ref, pattern) or fnmatch.fnmatch(default_branch, pattern)

    if includes and not any(matches(str(item)) for item in includes):
        return False
    if any(matches(str(item)) for item in excludes):
        return False
    return True


def _active_rule_types(rulesets: list[dict[str, Any]], default_branch: str) -> set[str]:
    rule_types: set[str] = set()
    for ruleset in rulesets:
        if ruleset.get("enforcement") != "active" or not _ref_matches(ruleset, default_branch):
            continue
        for rule in ruleset.get("rules") or []:
            if isinstance(rule, dict) and rule.get("type"):
                rule_types.add(str(rule["type"]))
    return rule_types


def _state_for(mode: str, checks: dict[str, Check]) -> str:
    problem = any(check.status in {"fail", "unknown"} for check in checks.values())
    if not problem:
        return "READY"
    if mode == "strict":
        return "BLOCKED"
    if mode == "restricted":
        return "RESTRICTED"
    return "READY"


def check_repository_posture(cwd: Path | str, runner: CommandRunner = _run) -> PostureReport:
    cwd = Path(cwd).resolve()
    root = _repo_root(cwd, runner)
    try:
        policy, source = RepositorySecurityPolicy.load(root)
    except Exception as exc:
        return PostureReport(
            state="BLOCKED",
            repository=None,
            repo_root=str(root),
            default_branch=None,
            mode="strict",
            policy_source="invalid",
            checked_at=time.time(),
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

    if policy.expected_repository:
        status = "pass" if repository == policy.expected_repository else "fail"
        checks["repository_identity"] = Check(status, f"expected {policy.expected_repository}; found {repository}")

    default_branch: str | None = None
    metadata: dict[str, Any] | None = None
    if repository:
        raw, error = _stdout(runner, ["gh", "api", f"repos/{repository}"], root)
        if raw:
            try:
                metadata = json.loads(raw)
                default_branch = str(metadata.get("default_branch") or "") or None
            except Exception as exc:
                error = f"invalid repository metadata JSON: {exc}"
        checks["github_metadata"] = Check("pass", f"default branch {default_branch}") if default_branch else Check("unknown", error or "default branch unavailable")
    else:
        checks["github_metadata"] = Check("unknown", "GitHub repository identity unavailable")

    rulesets: list[dict[str, Any]] | None = None
    rules_error: str | None = None
    if repository and default_branch:
        raw, rules_error = _stdout(runner, ["gh", "api", f"repos/{repository}/rulesets?includes_parents=true"], root)
        if raw is not None:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    rulesets = parsed
                else:
                    rules_error = "rulesets response is not an array"
            except Exception as exc:
                rules_error = f"invalid rulesets JSON: {exc}"

    rule_types = _active_rule_types(rulesets or [], default_branch or "") if rulesets is not None else set()
    requirements = {
        "require_pull_request": "pull_request",
        "block_force_push": "non_fast_forward",
        "required_status_checks": "required_status_checks",
    }
    for requirement, rule_type in requirements.items():
        if not policy.requirements[requirement]:
            continue
        if rulesets is None:
            checks[requirement] = Check("unknown", rules_error or "rulesets unavailable")
        elif rule_type in rule_types:
            checks[requirement] = Check("pass", f"active {rule_type} rule applies to {default_branch}")
        else:
            checks[requirement] = Check("fail", f"no active {rule_type} rule applies to {default_branch}")

    state = _state_for(policy.mode, checks)
    if checks.get("repository_identity", Check("pass", "")).status == "fail":
        state = "BLOCKED"
    return PostureReport(state, repository, str(root), default_branch, policy.mode, source, time.time(), checks)


def _state_path(session_id: str) -> Path:
    base = Path(os.environ.get("AGENT_HARNESS_STATE_DIR", str(Path(tempfile.gettempdir()) / "agent-harness" / "posture")))
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return base / f"{digest}.json"


def save_cached_posture(session_id: str, report: PostureReport) -> None:
    path = _state_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(report.to_dict(), separators=(",", ":")), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


def load_cached_posture(session_id: str) -> PostureReport | None:
    path = _state_path(session_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return PostureReport.from_dict(value)
    except (FileNotFoundError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
