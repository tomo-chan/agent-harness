"""Shared vendor-neutral hook evaluation and SCM semantic validation.

The functions in this module mediate agent-issued actions visible at the hook
boundary. They do not claim complete mediation of arbitrary child-process side
effects. Repository authority state, canonical SCM publication, and control-plane
publication approval are kept explicit so the security contract can be reviewed
independently from vendor adapters.
"""

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
from urllib.parse import quote

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
    r"(?i)(?:\bgit\b[^\n;&|<>]*\bpush\b|\bgh\b[^\n;&|<>]*\bpr\s+(?:create|merge)\b|\bgh\b[^\n;&|<>]*\brelease\s+(?:create|edit|upload|delete)\b)"
)
READ_ONLY_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:pwd|ls|find|rg|grep|cat|head|tail|wc|stat|file|tree|git\s+(?:status|diff|log|show|branch|rev-parse|worktree\s+list)\b|gh\s+pr\s+(?:view|status|checks)\b)"
)
MUTATING_TOOLS = {"write", "edit", "multi_edit", "apply_patch"}
CONTROL_PLANE_PREFIXES = (
    ".agent-harness/",
    ".claude/",
    ".codex/",
    ".devin/",
    ".github/workflows/",
    "reference/claude/",
    "reference/codex/",
    "reference/harness/",
    "reference/hooks/",
    "reference/posture/",
    "reference/policies/",
    "reference/launcher/",
    "reference/scripts/",
    "reference/kubernetes/",
)
CONTROL_PLANE_FILES = {
    "AGENTS.md",
    ".github/pull_request_template.md",
}


def read_stdin() -> dict[str, Any]:
    """Read and validate one vendor hook payload from standard input."""
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    return value


def normalize(raw: dict[str, Any], vendor: str) -> dict[str, Any]:
    """Normalize a vendor hook payload into the central policy action model."""
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
    """Return the shell command represented by a normalized action."""
    value = action.get("input", {}).get("command", "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _shell_tokens(command: str) -> list[str] | None:
    """Tokenize a shell command while preserving control operators as tokens."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return None


def _has_compound_shell(command: str) -> bool:
    """Return whether a command contains shell composition outside the allowlist."""
    if "\n" in command or "\r" in command or "`" in command or "$(" in command:
        return True
    tokens = _shell_tokens(command)
    if tokens is None:
        return True
    return any(token and set(token) <= set(";&|<>") for token in tokens)


def _is_scm_mutation(action: dict[str, Any]) -> bool:
    """Conservatively detect recognizable direct remote SCM mutation syntax.

    The search is intentionally broader than the autonomous command allowlist:
    Git global options and GitHub CLI global options may appear between the
    executable and mutation subcommand. This still does not claim complete
    mediation of aliases, dynamically constructed commands, or child processes.
    """
    return bool(SCM_MUTATION_RE.search(_command(action)))


def _is_mutation(action: dict[str, Any]) -> bool:
    """Conservatively classify whether an observed action can mutate state.

    Unknown shell commands and compound shell expressions are treated as
    mutations. This classification is intentionally conservative because
    repository posture is an authority state that must precede approval logic.
    """
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
    """Run a bounded local Git query and return ``(stdout, error)``."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=5, check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return result.stdout.strip(), None


def _github_branch_head(cwd: Path, repository: str, branch: str) -> tuple[str | None, str | None]:
    """Return a branch-head SHA directly from the checked GitHub repository.

    Local remote-tracking refs are mutable by repository code running under the
    same operating-system identity, so they cannot be independent publication
    evidence. GitHub is queried directly and malformed/unavailable results fail
    closed at the caller.
    """
    endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='')}"
    try:
        result = subprocess.run(
            ["gh", "api", endpoint], cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15, check=False,
        )
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or f"exit {result.returncode}").strip()
    try:
        value = json.loads(result.stdout)
        sha = value.get("object", {}).get("sha") if isinstance(value, dict) else None
    except Exception as exc:
        return None, f"invalid GitHub branch-ref JSON: {exc}"
    if not isinstance(sha, str) or not sha:
        return None, "GitHub branch-ref response does not contain object.sha"
    return sha, None


def _active_repo_root(cwd: Path) -> str | None:
    """Resolve the active Git repository root for posture-cache context checks."""
    value, _ = _run_git(cwd, ["rev-parse", "--show-toplevel"])
    return str(Path(value).resolve()) if value else None


def refresh_repository_posture(raw: dict[str, Any]):
    """Re-evaluate repository posture and save a non-authoritative session copy."""
    cwd = Path(str(raw.get("cwd") or os.getcwd()))
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = check_repository_posture(cwd)
    save_cached_posture(session_id, report)
    return report


def current_repository_posture(raw: dict[str, Any], *, refresh_if_stale: bool = True):
    """Return repository posture without trusting mutable cache for enforcement.

    When ``refresh_if_stale`` is true, which is the enforcement path used for
    mutations, posture is always re-evaluated from Git and GitHub evidence. The
    session cache is only a context/performance artifact and is never an
    authoritative source for mutation permission. Read-only callers may request
    the cached report by setting ``refresh_if_stale`` false.
    """
    if refresh_if_stale:
        try:
            return refresh_repository_posture(raw)
        except Exception:
            return None

    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    session_id = str(raw.get("session_id") or f"pid-{os.getpid()}")
    report = load_cached_posture(session_id)
    current_root = _active_repo_root(cwd)
    if report is None or current_root is None or report.repo_root != current_root:
        return None
    if time.time() - report.checked_at > report.ttl_seconds:
        return None
    return report


def repository_posture_context(raw: dict[str, Any]) -> str:
    """Build SessionStart context describing the current repository posture."""
    try:
        report = refresh_repository_posture(raw)
    except Exception as exc:
        return f"Repository security posture UNKNOWN: checker failed: {exc}. Remote SCM mutations will be restricted."
    return report.summary() + f" policy={report.policy_source}."


def _current_branch(cwd: Path, rule: str) -> tuple[str | None, Decision | None]:
    """Resolve a named current branch or return a deny decision for detached state."""
    branch, error = _run_git(cwd, ["branch", "--show-current"])
    if error or not branch:
        return None, Decision("deny", f"cannot determine current branch: {error or 'detached HEAD'}", rule)
    return branch, None


def _checked_origin(cwd: Path, report, rule: str) -> Decision | None:
    """Ensure the fetch URL for ``origin`` still names the checked repository."""
    remote, error = _run_git(cwd, ["remote", "get-url", "origin"])
    remote_repo = parse_github_repository(remote or "") if remote else None
    if error or not remote_repo or remote_repo != report.repository:
        return Decision("deny", "origin no longer matches the checked repository", rule)
    return None


def _checked_push_destination(cwd: Path, report, rule: str) -> Decision | None:
    """Ensure the effective ``origin`` push URL names only the checked repository.

    Explicitly naming ``origin`` in the command is insufficient because
    ``remote.origin.pushurl`` and Git URL rewrite rules can redirect a push. The
    validator therefore resolves the effective push URL through Git itself and
    requires exactly one destination that parses to the checked GitHub
    repository. Mirror mode is also rejected because it changes ref semantics.
    """
    urls, error = _run_git(cwd, ["remote", "get-url", "--push", "--all", "origin"])
    if error or not urls:
        return Decision("deny", f"cannot determine effective origin push URL: {error or 'missing URL'}", rule)
    push_urls = [line.strip() for line in urls.splitlines() if line.strip()]
    if len(push_urls) != 1:
        return Decision("deny", "canonical push requires exactly one effective origin push URL", rule)
    push_repo = parse_github_repository(push_urls[0])
    if push_repo != report.repository:
        return Decision("deny", "effective origin push URL does not match the checked repository", rule)
    mirror, _ = _run_git(cwd, ["config", "--bool", "--get", "remote.origin.mirror"])
    if mirror and mirror.lower() == "true":
        return Decision("deny", "remote.origin.mirror is incompatible with canonical publication", rule)
    return None


def _is_control_plane_path(path: str) -> bool:
    """Return whether a repository path belongs to the harness control plane."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized in CONTROL_PLANE_FILES or normalized.startswith(CONTROL_PLANE_PREFIXES)


def _control_plane_publication_decision(cwd: Path, report) -> Decision | None:
    """Require approval for control-plane changes using authoritative base SHA.

    The default-branch head is fetched directly from the checked GitHub
    repository, then the committed branch diff is evaluated against that exact
    SHA. Local ``origin/<default>`` refs are deliberately ignored because the
    evaluated repository can rewrite them. If the authoritative commit object is
    not available locally or the diff cannot be established, validation fails
    closed rather than falling back to a mutable ref.
    """
    if not report.repository or not report.default_branch:
        return Decision("deny", "checked repository/default branch is unavailable for control-plane diff validation", "control-plane-publication")
    base_sha, error = _github_branch_head(cwd, report.repository, report.default_branch)
    if error or not base_sha:
        return Decision(
            "deny",
            f"cannot obtain authoritative GitHub default-branch head: {error or 'unknown error'}",
            "control-plane-publication",
        )
    _, object_error = _run_git(cwd, ["cat-file", "-e", f"{base_sha}^{{commit}}"])
    if object_error:
        return Decision(
            "deny",
            f"authoritative GitHub base commit {base_sha} is not available locally for diff validation",
            "control-plane-publication",
        )
    changed, diff_error = _run_git(cwd, ["diff", "--name-only", f"{base_sha}...HEAD"])
    if diff_error or changed is None:
        return Decision(
            "deny",
            f"cannot establish control-plane publication diff against GitHub base {base_sha}: {diff_error or 'unknown error'}",
            "control-plane-publication",
        )
    protected = sorted(path for path in changed.splitlines() if path and _is_control_plane_path(path))
    if protected:
        sample = ", ".join(protected[:5])
        suffix = "" if len(protected) <= 5 else f" (+{len(protected) - 5} more)"
        return Decision(
            "ask",
            f"publishing control-plane changes requires explicit approval: {sample}{suffix}",
            "control-plane-publication",
        )
    return None


def _validate_canonical_push(raw: dict[str, Any], action: dict[str, Any], report) -> Decision | None:
    """Validate explicit autonomous Git publication semantics.

    A permitted push explicitly names ``origin`` and the exact destination ref,
    then validates the checked fetch identity, effective push URL, branch,
    upstream lifecycle, and control-plane publication evidence. This removes
    dependence on ``push.default``, ``pushRemote``, implicit refspecs, or a
    redirecting ``pushurl`` from the autonomous contract.
    """
    command = _command(action)
    tokens = _shell_tokens(command)
    if not tokens or tokens[:2] != ["git", "push"]:
        return Decision("deny", "invalid canonical push command", "canonical-git-push")
    if report is None or report.state != "READY":
        reason = report.summary() if report is not None else "repository security posture is unavailable"
        return Decision("deny", reason, "repository-posture")

    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    branch, denied = _current_branch(cwd, "canonical-git-push")
    if denied:
        return denied
    assert branch is not None
    if branch == report.default_branch:
        return Decision("deny", f"direct push to default branch {branch} is prohibited", "canonical-git-push")

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

    denied = _checked_origin(cwd, report, "canonical-git-push")
    if denied:
        return denied
    denied = _checked_push_destination(cwd, report, "canonical-git-push")
    if denied:
        return denied

    upstream, upstream_error = _run_git(cwd, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
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

    return _control_plane_publication_decision(cwd, report)


def _validate_pr_create(raw: dict[str, Any], action: dict[str, Any], report) -> Decision | None:
    """Validate autonomous PR creation against the current checked Git state.

    Repository, head, and base overrides are prohibited. The current branch must
    be a published non-default branch whose ``origin`` and upstream still match
    the repository verified by posture checking. Control-plane changes require
    explicit publication approval regardless of how those files were edited.
    """
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

    cwd = Path(str(raw.get("cwd") or os.getcwd())).resolve()
    branch, denied = _current_branch(cwd, "canonical-pr-create")
    if denied:
        return denied
    assert branch is not None
    if branch == report.default_branch:
        return Decision("deny", f"cannot create an autonomous PR from the default branch {branch}", "canonical-pr-create")

    denied = _checked_origin(cwd, report, "canonical-pr-create")
    if denied:
        return denied

    upstream, upstream_error = _run_git(cwd, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    expected = f"origin/{branch}"
    if upstream_error or upstream != expected:
        return Decision(
            "deny",
            f"autonomous PR creation requires published branch upstream {expected}; publish the current branch canonically first",
            "canonical-pr-create",
        )
    return _control_plane_publication_decision(cwd, report)


def _enforce_repository_posture(raw: dict[str, Any], action: dict[str, Any], result: Decision) -> Decision:
    """Apply freshly evaluated authority-state and semantic SCM constraints.

    ``BLOCKED`` and ``RESTRICTED`` are repository authority states, not ordinary
    approval-class decisions. Mutation enforcement always re-evaluates posture
    instead of trusting the writable session cache, then applies authority before
    ordinary approval so lower-level approval cannot weaken the restriction.
    """
    if action.get("event") != "PreToolUse":
        return result

    command = _command(action)
    mutation = _is_mutation(action)
    if not mutation:
        return result

    report = current_repository_posture(raw, refresh_if_stale=True)
    if report is None:
        if _is_scm_mutation(action):
            return Decision(
                "deny",
                "repository security posture is unavailable; recognizable direct remote SCM mutation is restricted",
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
        return _validate_canonical_push(raw, action, report) or result
    if tokens[:3] == ["gh", "pr", "create"]:
        return _validate_pr_create(raw, action, report) or result
    return result


def _approved_rules() -> set[str]:
    """Return trusted rule identifiers explicitly approved for this execution."""
    return {
        item.strip()
        for item in os.environ.get("AGENT_HARNESS_APPROVED_RULES", "").split(",")
        if item.strip()
    }


def evaluate(raw: dict[str, Any], vendor: str) -> Decision:
    """Evaluate one hook action through policy, posture, semantics, and approval.

    Authority-state enforcement precedes approval. Approval is applied only to
    the final ``ask`` result, including semantic publication review decisions,
    so it cannot convert a recognized ``BLOCKED``/``RESTRICTED`` authority denial
    into an allow.
    """
    policy = Path(os.environ.get("AGENT_HARNESS_POLICY", str(DEFAULT_POLICY)))
    action = normalize(raw, vendor)
    try:
        result = PolicyEngine.from_file(policy).evaluate(action)
    except Exception as exc:
        return Decision("deny", f"policy evaluation failed closed: {exc}", "policy-error")

    result = _enforce_repository_posture(raw, action, result)
    approved = _approved_rules()
    if result.decision == "ask" and (result.rule in approved or "*" in approved):
        return Decision("allow", f"externally approved rule {result.rule}: {result.reason}", result.rule)
    return result


def emit(value: dict[str, Any]) -> int:
    """Emit a compact JSON hook response to standard output."""
    json.dump(value, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0
