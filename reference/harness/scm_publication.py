"""Validate autonomous SCM publication semantics for S3.

S3 owns the classification and semantic validation of directly observable SCM
publication commands. Repository identity and authority are supplied by S2;
control-plane publication review belongs to S4 and is intentionally absent here.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.harness import authority  # noqa: E402
from reference.hooks.policy_engine import Decision  # noqa: E402
from reference.posture.checker import parse_github_repository  # noqa: E402

_SCM_PUBLICATION_RE = re.compile(
    r"(?i)(?:\bgit\b[^\n;&|<>]*\bpush\b|\bgh\b[^\n;&|<>]*\bpr\s+create\b)"
)


def _command(action: dict[str, Any]) -> str:
    """Extract one shell command from a normalized action."""
    payload = action.get("input", {})
    if not isinstance(payload, dict):
        return ""
    value = payload.get("command", "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _shell_tokens(command: str) -> list[str] | None:
    """Tokenize shell input while exposing control operators."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return None


def has_compound_shell(command: str) -> bool:
    """Return whether shell composition makes the command non-canonical."""
    if "\n" in command or "\r" in command or "`" in command or "$(" in command:
        return True
    tokens = _shell_tokens(command)
    if tokens is None:
        return True
    return any(token and set(token) <= set(";&|<>") for token in tokens)


def is_scm_publication(action: dict[str, Any]) -> bool:
    """Detect recognizable direct SCM publication anywhere in observed shell text.

    Detection is intentionally broader than the autonomous canonical forms so a
    compound shell such as ``git status && git push ...`` is still classified as
    a restricted publication before approval. Aliases, arbitrary child processes,
    and credential misuse remain outside S3's observation boundary.
    """
    return bool(_SCM_PUBLICATION_RE.search(_command(action)))


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    """Run one bounded Git observation and return ``(stdout, error)``."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout.strip(), None


def _current_branch(cwd: Path, rule: str) -> tuple[str | None, Decision | None]:
    """Resolve a named current branch or return a denial for detached state."""
    branch, error = _run_git(cwd, ["branch", "--show-current"])
    if error or not branch:
        return None, Decision(
            "deny",
            f"cannot determine current branch: {error or 'detached HEAD'}",
            rule,
        )
    return branch, None


def _checked_origin(cwd: Path, repository: str, rule: str) -> Decision | None:
    """Require the current origin fetch URL to match the checked repository."""
    remote, error = _run_git(cwd, ["remote", "get-url", "origin"])
    remote_repo = parse_github_repository(remote or "") if remote else None
    if error or remote_repo != repository:
        return Decision("deny", "origin no longer matches the checked repository", rule)
    return None


def _checked_push_destination(cwd: Path, repository: str, rule: str) -> Decision | None:
    """Require exactly one effective push URL for the checked repository."""
    urls, error = _run_git(cwd, ["remote", "get-url", "--push", "--all", "origin"])
    if error or not urls:
        return Decision(
            "deny",
            f"cannot determine effective origin push URL: {error or 'missing URL'}",
            rule,
        )
    push_urls = [line.strip() for line in urls.splitlines() if line.strip()]
    if len(push_urls) != 1:
        return Decision(
            "deny",
            "canonical push requires exactly one effective origin push URL",
            rule,
        )
    if parse_github_repository(push_urls[0]) != repository:
        return Decision(
            "deny",
            "effective origin push URL does not match the checked repository",
            rule,
        )
    mirror, _ = _run_git(cwd, ["config", "--bool", "--get", "remote.origin.mirror"])
    if mirror and mirror.lower() == "true":
        return Decision(
            "deny",
            "remote.origin.mirror is incompatible with canonical publication",
            rule,
        )
    return None


def _ready_report(raw: dict[str, Any]) -> tuple[Any | None, Decision | None]:
    """Obtain fresh S2 authority evidence required for publication semantics."""
    report = authority.current_repository_posture(raw, refresh_for_authority=True)
    if report is None:
        return None, Decision(
            "deny",
            "repository authority is unavailable for SCM publication",
            "repository-authority",
        )
    if report.state != "READY":
        return report, Decision("deny", report.summary(), "repository-authority")
    if not report.repository or not report.default_branch:
        return report, Decision(
            "deny",
            "checked repository/default branch is unavailable",
            "repository-authority",
        )
    return report, None


def _validate_push(
    raw: dict[str, Any], action: dict[str, Any], report: Any
) -> Decision | None:
    """Validate the canonical autonomous Git push contract."""
    command = _command(action)
    tokens = _shell_tokens(command)
    if not tokens or tokens[:2] != ["git", "push"]:
        return Decision("deny", "invalid canonical push command", "canonical-git-push")

    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    branch, denied = _current_branch(cwd, "canonical-git-push")
    if denied:
        return denied
    assert branch is not None
    if branch == report.default_branch:
        return Decision(
            "deny",
            f"direct push to default branch {branch} is prohibited",
            "canonical-git-push",
        )

    refspec = f"HEAD:refs/heads/{branch}"
    normal_form = ("git", "push", "origin", refspec)
    first_form = ("git", "push", "--set-upstream", "origin", refspec)
    form = tuple(tokens)
    if form not in {normal_form, first_form}:
        return Decision(
            "deny",
            f"autonomous push must target exactly origin {refspec}, with --set-upstream only for first publication",
            "canonical-git-push",
        )

    denied = _checked_origin(cwd, report.repository, "canonical-git-push")
    if denied:
        return denied
    denied = _checked_push_destination(cwd, report.repository, "canonical-git-push")
    if denied:
        return denied

    upstream, upstream_error = _run_git(
        cwd,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
    )
    expected_upstream = f"origin/{branch}"
    if form == normal_form:
        if upstream_error or upstream != expected_upstream:
            return Decision(
                "deny",
                f"canonical push requires upstream {expected_upstream}; use the canonical --set-upstream form for first publish",
                "canonical-git-push",
            )
    elif upstream is not None and upstream_error is None:
        return Decision(
            "deny",
            "canonical --set-upstream push is only for first publication; an upstream already exists",
            "canonical-git-push",
        )
    return None


def _validate_pr_create(
    raw: dict[str, Any], action: dict[str, Any], report: Any
) -> Decision | None:
    """Validate autonomous PR creation against the checked current branch."""
    command = _command(action)
    tokens = _shell_tokens(command)
    if not tokens or tokens[:3] != ["gh", "pr", "create"]:
        return Decision("deny", "invalid PR creation command", "canonical-pr-create")
    forbidden = {"--repo", "-R", "--head", "-H", "--base", "-B"}
    if any(token in forbidden for token in tokens[3:]):
        return Decision(
            "deny",
            "autonomous `gh pr create` may not override repository, head branch, or base branch",
            "canonical-pr-create",
        )

    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    branch, denied = _current_branch(cwd, "canonical-pr-create")
    if denied:
        return denied
    assert branch is not None
    if branch == report.default_branch:
        return Decision(
            "deny",
            f"cannot create an autonomous PR from the default branch {branch}",
            "canonical-pr-create",
        )
    denied = _checked_origin(cwd, report.repository, "canonical-pr-create")
    if denied:
        return denied

    upstream, upstream_error = _run_git(
        cwd,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
    )
    expected = f"origin/{branch}"
    if upstream_error or upstream != expected:
        return Decision(
            "deny",
            f"autonomous PR creation requires published branch upstream {expected}",
            "canonical-pr-create",
        )
    return None


def validate_autonomous_publication(
    raw: dict[str, Any], action: dict[str, Any], result: Decision
) -> Decision:
    """Apply S2 authority and S3 publication semantics to one policy decision."""
    command = _command(action)
    publication = is_scm_publication(action)
    result = authority.enforce_repository_authority(
        raw,
        result,
        mutation=authority.is_mutation(action),
        restricted_operation=publication,
    )
    if result.decision == "deny":
        return result

    if has_compound_shell(command):
        if publication or result.decision == "allow":
            return Decision(
                "ask",
                "compound shell syntax is outside the autonomous allowlist",
                "compound-shell",
            )
        return result

    if not publication or result.decision != "allow":
        return result

    report, denied = _ready_report(raw)
    if denied:
        return denied
    assert report is not None

    tokens = _shell_tokens(command) or []
    if tokens[:2] == ["git", "push"]:
        return _validate_push(raw, action, report) or result
    if tokens[:3] == ["gh", "pr", "create"]:
        return _validate_pr_create(raw, action, report) or result
    return Decision(
        "ask",
        "SCM publication syntax is outside the autonomous canonical forms",
        "noncanonical-publication",
    )
