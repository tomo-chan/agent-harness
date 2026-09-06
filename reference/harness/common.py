from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "reference" / "hooks"
POSTURE_DIR = ROOT / "reference" / "posture"
for path in (HOOKS_DIR, POSTURE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from checker import check_repository_posture, load_cached_posture, parse_github_repository, save_cached_posture  # noqa: E402
from policy_engine import Decision, PolicyEngine  # noqa: E402

DEFAULT_POLICY = ROOT / "reference" / "policies" / "policy.example.json"
SCM_MUTATION_RE = re.compile(
    r"(?i)^\s*(?:git\s+push\b|gh\s+pr\s+(?:create|merge)\b|gh\s+release\s+(?:create|edit|upload|delete)\b)"
)
READ_ONLY_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:pwd|ls|find|rg|grep|cat|head|tail|wc|stat|file|tree|git\s+(?:status|diff|log|show|branch|rev-parse|worktree\s+list)\b|gh\s+pr\s+(?:view|status|checks)\b)"
)
MUTATING_TOOLS = {"write", "edit", "multi_edit", "apply_patch"}
CANONICAL_PUSH_FORMS = {
    ("git", "push"),
    ("git", "push", "--set-upstream", "origin", "HEAD"),
}


def read_stdin() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    return value


def normalize(raw: dict[str, Any], vendor: str) -> dict[str, Any]:
    tool_input = raw.get("tool_input", raw.get("input", {}))
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    return {
        "event": str(raw.get("hook_event_name", raw.get("event", "PreToolUse"))),
        "tool": str(raw.get("tool_name", raw.get("tool", ""))),
        "input": tool_input,
        "context": {
            "vendor": vendor,
            "session_id": raw.get("session_id"),
            "turn_id": raw.get("turn_id", raw.get("prompt_id")),
            "tool_use_id": raw.get("tool_use_id"),
            "cwd": str(raw.get("cwd") or os.getcwd()),
            "permission_mode": raw.get("permission_mode"),
        },
    }


def _command(action: dict[str, Any]) -> str:
    value = action.get("input", {}).get("command", "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _shell_tokens(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return None


def _has_compound_shell(command: str) -> bool:
    if "\n" in command or "\r" in command or "`" in command or "$(" in command:
        return True
    tokens = _shell_tokens(command)
    if tokens is None:
        return True
    return any(token and set(token) <= set(";&|<>") for token in tokens)


def _is_scm_mutation(action: dict[str, Any]) -> bool:
    return bool(SCM_MUTATION_RE.search(_command(action)))


def _is_mutation(action: dict[str, Any]) -> bool:
    tool = str(action.get("tool", "")).lower()
    if tool in MUTATING_TOOLS:
        return True
    command = _command(action)
    if not command:
        return False
    if _has_compound_shell(command):
        return True
    return not bool(READ_ONLY_COMMAND_RE.fullmatch(command.strip()))


def _run_git(cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
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


def _active_repo_root(cwd: Path) -> str | None:
    value, _ = _run_git(cwd, ["rev-parse", "--show-toplevel"])
    return str(Path(value).resolve()) if value else None


def refresh_repository_posture(raw: dict[str, Any]):
    cwd = Path(str(raw.get("cwd") or os.getcwd()))
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = check_repository_posture(cwd)
    save_cached_posture(session_id, report)
    return report


def current_repository_posture(raw: dict[str, Any], *, refresh_if_stale: bool = True):
    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = load_cached_posture(session_id)
    current_root = _active_repo_root(cwd)
    stale = report is None
    if report is not None:
        stale = stale or current_root is None or report.repo_root != current_root
        stale = stale or (time.time() - report.checked_at > report.ttl_seconds)
    if stale and refresh_if_stale:
        try:
            report = refresh_repository_posture(raw)
        except Exception:
            return None
    return report


def repository_posture_context(raw: dict[str, Any]) -> str:
    try:
        report = refresh_repository_posture(raw)
    except Exception as exc:
        return f"Repository security posture UNKNOWN: checker failed: {exc}. Remote SCM mutations will be restricted."
    return report.summary() + f" policy={report.policy_source}."


def _validate_canonical_push(raw: dict[str, Any], action: dict[str, Any], report) -> Decision | None:
    command = _command(action)
    tokens = _shell_tokens(command)
    if not tokens or tuple(tokens) not in CANONICAL_PUSH_FORMS:
        return Decision(
            "deny",
            "autonomous push must use exactly `git push` or `git push --set-upstream origin HEAD`",
            "canonical-git-push",
        )
    if report is None or report.state != "READY":
        reason = report.summary() if report is not None else "repository security posture is unavailable"
        return Decision("deny", reason, "repository-posture")

    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    branch, error = _run_git(cwd, ["branch", "--show-current"])
    if error or not branch:
        return Decision("deny", f"cannot determine current branch: {error or 'detached HEAD'}", "canonical-git-push")
    if branch == report.default_branch:
        return Decision("deny", f"direct push to default branch {branch} is prohibited", "canonical-git-push")

    remote, error = _run_git(cwd, ["remote", "get-url", "origin"])
    remote_repo = parse_github_repository(remote or "") if remote else None
    if error or not remote_repo or remote_repo != report.repository:
        return Decision("deny", "origin no longer matches the checked repository", "canonical-git-push")

    if tuple(tokens) == ("git", "push"):
        upstream, error = _run_git(cwd, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        expected = f"origin/{branch}"
        if error or upstream != expected:
            return Decision(
                "deny",
                f"canonical git push requires upstream {expected}; use `git push --set-upstream origin HEAD` for first publish",
                "canonical-git-push",
            )
    return None


def _validate_pr_create(action: dict[str, Any], report) -> Decision | None:
    command = _command(action)
    tokens = _shell_tokens(command)
    if not tokens or tokens[:3] != ["gh", "pr", "create"]:
        return None
    if report is None or report.state != "READY":
        reason = report.summary() if report is not None else "repository security posture is unavailable"
        return Decision("deny", reason, "repository-posture")
    forbidden = {"--repo", "-R", "--head", "-H", "--base", "-B"}
    if any(token in forbidden for token in tokens[3:]):
        return Decision(
            "deny",
            "autonomous `gh pr create` may not override repository, head branch, or base branch",
            "canonical-pr-create",
        )
    return None


def _enforce_repository_posture(raw: dict[str, Any], action: dict[str, Any], result: Decision) -> Decision:
    if action.get("event") != "PreToolUse":
        return result

    command = _command(action)
    mutation = _is_mutation(action)
    if not mutation:
        return result

    # Repository posture is an authority state, not an approval-class policy result.
    # It must therefore be enforced before allow/ask handling so BLOCKED cannot be
    # weakened by native prompts or trusted external approval of an ordinary rule.
    report = current_repository_posture(raw, refresh_if_stale=True)
    if report is None:
        if _is_scm_mutation(action):
            return Decision(
                "deny",
                "repository security posture is unavailable; remote SCM mutation is restricted",
                "repository-posture",
            )
    else:
        if report.state == "BLOCKED":
            return Decision("deny", report.summary(), "repository-posture")
        if report.state == "RESTRICTED" and _is_scm_mutation(action):
            return Decision("deny", report.summary(), "repository-posture")

    if result.decision != "allow":
        return result

    if command and _has_compound_shell(command):
        return Decision("ask", "compound shell syntax is outside the autonomous allowlist", "compound-shell")

    tokens = _shell_tokens(command) or []
    if tokens[:2] == ["git", "push"]:
        denied = _validate_canonical_push(raw, action, report)
        return denied or result
    if tokens[:3] == ["gh", "pr", "create"]:
        denied = _validate_pr_create(action, report)
        return denied or result
    return result


def evaluate(raw: dict[str, Any], vendor: str) -> Decision:
    policy = Path(os.environ.get("AGENT_HARNESS_POLICY", str(DEFAULT_POLICY)))
    action = normalize(raw, vendor)
    try:
        result = PolicyEngine.from_file(policy).evaluate(action)
    except Exception as exc:
        return Decision("deny", f"policy evaluation failed closed: {exc}", "policy-error")

    approved = {
        item.strip()
        for item in os.environ.get("AGENT_HARNESS_APPROVED_RULES", "").split(",")
        if item.strip()
    }
    if result.decision == "ask" and (result.rule in approved or "*" in approved):
        result = Decision("allow", f"externally approved rule {result.rule}: {result.reason}", result.rule)
    return _enforce_repository_posture(raw, action, result)


def completion_check(raw: dict[str, Any]) -> tuple[bool, str]:
    cwd = Path(str(raw.get("cwd") or os.getcwd()))
    gate = ROOT / "reference" / "scripts" / "completion_gate.sh"
    env = os.environ.copy()
    try:
        completed = subprocess.run(
            ["bash", str(gate)],
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(os.environ.get("AGENT_HARNESS_COMPLETION_TIMEOUT", "120")),
            check=False,
        )
    except Exception as exc:
        return False, f"completion gate failed closed: {exc}"
    output = completed.stdout.strip()
    return completed.returncode == 0, output or f"completion gate exited {completed.returncode}"


def emit(value: dict[str, Any]) -> int:
    json.dump(value, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0
