from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "reference" / "harness"))
sys.path.insert(0, str(ROOT / "reference" / "hooks"))

import common  # noqa: E402
from policy_engine import Decision  # noqa: E402

BRANCH = "feature/review-fix"
REFSPEC = f"HEAD:refs/heads/{BRANCH}"
NORMAL_PUSH = f"git push origin {REFSPEC}"
FIRST_PUSH = f"git push --set-upstream origin {REFSPEC}"


def _raw(command: str):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(ROOT),
        "session_id": "posture-test",
    }


def _report(state: str):
    return SimpleNamespace(
        state=state,
        repository="tomo-chan/agent-harness",
        default_branch="main",
        summary=lambda: f"repository posture {state}",
    )


def _published_feature_git(_cwd, args):
    values = {
        ("branch", "--show-current"): (BRANCH, None),
        ("remote", "get-url", "origin"): ("https://github.com/tomo-chan/agent-harness.git", None),
        ("remote", "get-url", "--push", "--all", "origin"): ("https://github.com/tomo-chan/agent-harness.git", None),
        ("config", "--bool", "--get", "remote.origin.mirror"): ("false", None),
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): (f"origin/{BRANCH}", None),
    }
    return values[tuple(args)]


def _allow(command: str, monkeypatch, fake_git, rule="canonical-git-push"):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("READY"))
    monkeypatch.setattr(common, "_run_git", fake_git)
    monkeypatch.setattr(common, "_control_plane_publication_decision", lambda _cwd, _report: None)
    raw = _raw(command)
    action = common.normalize(raw, "codex")
    return common._enforce_repository_posture(raw, action, Decision("allow", "ok", rule))


def test_restricted_blocks_remote_scm_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("RESTRICTED"))
    raw = _raw(NORMAL_PUSH)
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "canonical-git-push"))
    assert result.decision == "deny"
    assert result.rule == "repository-posture"


def test_restricted_allows_local_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("RESTRICTED"))
    raw = _raw("git commit -m test")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "feature-git-mutation"))
    assert result.decision == "allow"


def test_blocked_denies_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("BLOCKED"))
    raw = _raw("git commit -m test")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "feature-git-mutation"))
    assert result.decision == "deny"


def test_blocked_overrides_ask_for_mutation(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("BLOCKED"))
    raw = _raw("gh pr merge 1 --squash")
    action = common.normalize(raw, "claude")
    result = common._enforce_repository_posture(raw, action, Decision("ask", "approval required", "scm-merge-release"))
    assert result.decision == "deny"


def test_blocked_does_not_change_read_only_decision(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("BLOCKED"))
    raw = _raw("git status")
    action = common.normalize(raw, "claude")
    result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "read-only-git"))
    assert result.decision == "allow"


def test_restricted_compound_shell_cannot_hide_push(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("RESTRICTED"))
    raw = _raw(f"git status && {NORMAL_PUSH}")
    action = common.normalize(raw, "codex")
    result = common._enforce_repository_posture(raw, action, Decision("ask", "approval required", "default"))
    assert result.decision == "deny"
    assert result.rule == "repository-posture"


def test_canonical_push_rejects_implicit_and_wrong_refspec_forms(monkeypatch):
    for command in ("git push", "git push origin", "git push origin HEAD:other"):
        result = _allow(command, monkeypatch, _published_feature_git)
        assert result.decision == "deny"
        assert result.rule == "canonical-git-push"


def test_canonical_push_allows_explicit_origin_current_branch(monkeypatch):
    result = _allow(NORMAL_PUSH, monkeypatch, _published_feature_git)
    assert result.decision == "allow"


def test_canonical_push_denies_detached_head(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("branch", "--show-current"):
            return "", None
        raise AssertionError(args)

    result = _allow(NORMAL_PUSH, monkeypatch, fake_git)
    assert result.decision == "deny"
    assert "detached HEAD" in result.reason


def test_canonical_push_denies_default_branch(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("branch", "--show-current"):
            return "main", None
        raise AssertionError(args)

    result = _allow("git push origin HEAD:refs/heads/main", monkeypatch, fake_git)
    assert result.decision == "deny"
    assert "default branch" in result.reason


def test_canonical_push_denies_origin_repository_mismatch(monkeypatch):
    def fake_git(_cwd, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): ("https://github.com/other/repository.git", None),
        }
        return values[tuple(args)]

    result = _allow(NORMAL_PUSH, monkeypatch, fake_git)
    assert result.decision == "deny"
    assert "origin" in result.reason


def test_canonical_push_denies_effective_pushurl_mismatch(monkeypatch):
    def fake_git(_cwd, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): ("https://github.com/tomo-chan/agent-harness.git", None),
            ("remote", "get-url", "--push", "--all", "origin"): ("https://github.com/other/repository.git", None),
        }
        return values[tuple(args)]

    result = _allow(NORMAL_PUSH, monkeypatch, fake_git)
    assert result.decision == "deny"
    assert "push URL" in result.reason


def test_canonical_push_denies_multiple_effective_push_urls(monkeypatch):
    def fake_git(_cwd, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): ("https://github.com/tomo-chan/agent-harness.git", None),
            ("remote", "get-url", "--push", "--all", "origin"): (
                "https://github.com/tomo-chan/agent-harness.git\nhttps://github.com/tomo-chan/agent-harness.git", None
            ),
        }
        return values[tuple(args)]

    result = _allow(NORMAL_PUSH, monkeypatch, fake_git)
    assert result.decision == "deny"
    assert "exactly one" in result.reason


def test_canonical_push_denies_mirror_remote(monkeypatch):
    def fake_git(_cwd, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): ("https://github.com/tomo-chan/agent-harness.git", None),
            ("remote", "get-url", "--push", "--all", "origin"): ("https://github.com/tomo-chan/agent-harness.git", None),
            ("config", "--bool", "--get", "remote.origin.mirror"): ("true", None),
        }
        return values[tuple(args)]

    result = _allow(NORMAL_PUSH, monkeypatch, fake_git)
    assert result.decision == "deny"
    assert "mirror" in result.reason


def test_plain_push_denies_wrong_upstream(monkeypatch):
    def fake_git(_cwd, args):
        values = dict()
        if tuple(args) == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return "origin/other", None
        return _published_feature_git(_cwd, args)

    result = _allow(NORMAL_PUSH, monkeypatch, fake_git)
    assert result.decision == "deny"
    assert f"origin/{BRANCH}" in result.reason


def test_plain_push_without_upstream_requires_first_publish_form(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return None, "no upstream configured"
        return _published_feature_git(_cwd, args)

    result = _allow(NORMAL_PUSH, monkeypatch, fake_git)
    assert result.decision == "deny"
    assert "first publish" in result.reason


def test_first_publish_form_allows_when_no_upstream_exists(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return None, "no upstream configured"
        return _published_feature_git(_cwd, args)

    result = _allow(FIRST_PUSH, monkeypatch, fake_git)
    assert result.decision == "allow"


def test_first_publish_form_denies_when_upstream_already_exists(monkeypatch):
    result = _allow(FIRST_PUSH, monkeypatch, _published_feature_git)
    assert result.decision == "deny"
    assert "first publication" in result.reason


def test_control_plane_review_uses_authoritative_github_base_sha(monkeypatch):
    monkeypatch.setattr(common, "_github_branch_head", lambda _cwd, repo, branch: ("deadbeef", None))

    def fake_git(_cwd, args):
        values = {
            ("cat-file", "-e", "deadbeef^{commit}"): ("", None),
            ("diff", "--name-only", "deadbeef...HEAD"): ("src/app.py\nreference/harness/common.py", None),
        }
        if tuple(args) == ("diff", "--name-only", "origin/main...HEAD"):
            raise AssertionError("mutable remote-tracking ref must not be publication authority")
        return values[tuple(args)]

    monkeypatch.setattr(common, "_run_git", fake_git)
    result = common._control_plane_publication_decision(ROOT, _report("READY"))
    assert result is not None
    assert result.decision == "ask"
    assert result.rule == "control-plane-publication"


def test_control_plane_review_denies_when_github_head_unavailable(monkeypatch):
    monkeypatch.setattr(common, "_github_branch_head", lambda _cwd, repo, branch: (None, "GitHub unavailable"))
    result = common._control_plane_publication_decision(ROOT, _report("READY"))
    assert result is not None
    assert result.decision == "deny"


def test_control_plane_review_denies_when_authoritative_commit_missing_locally(monkeypatch):
    monkeypatch.setattr(common, "_github_branch_head", lambda _cwd, repo, branch: ("deadbeef", None))
    monkeypatch.setattr(common, "_run_git", lambda _cwd, args: (None, "missing object"))
    result = common._control_plane_publication_decision(ROOT, _report("READY"))
    assert result is not None
    assert result.decision == "deny"


def test_control_plane_publication_approval_is_applied_after_authority_checks(monkeypatch):
    monkeypatch.setenv("AGENT_HARNESS_APPROVED_RULES", "control-plane-publication")
    monkeypatch.setattr(common.PolicyEngine, "from_file", lambda _path: SimpleNamespace(evaluate=lambda _action: Decision("allow", "ok", "canonical-git-push")))
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("READY"))
    monkeypatch.setattr(common, "_run_git", _published_feature_git)
    monkeypatch.setattr(
        common,
        "_control_plane_publication_decision",
        lambda _cwd, _report: Decision("ask", "control-plane changed", "control-plane-publication"),
    )
    result = common.evaluate(_raw(NORMAL_PUSH), "codex")
    assert result.decision == "allow"
    assert result.rule == "control-plane-publication"


def test_blocked_cannot_be_overridden_by_external_approval(monkeypatch):
    monkeypatch.setenv("AGENT_HARNESS_APPROVED_RULES", "*")
    monkeypatch.setattr(common.PolicyEngine, "from_file", lambda _path: SimpleNamespace(evaluate=lambda _action: Decision("ask", "approval required", "scm-merge-release")))
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("BLOCKED"))
    result = common.evaluate(_raw("gh pr merge 1 --squash"), "claude")
    assert result.decision == "deny"


def test_pr_create_cannot_override_repository_head_or_base(monkeypatch):
    monkeypatch.setattr(common, "current_repository_posture", lambda *a, **k: _report("READY"))
    for command in (
        "gh pr create --repo other/repo --fill",
        "gh pr create --head other-branch --fill",
        "gh pr create --base other-base --fill",
        "gh pr create -R other/repo --fill",
        "gh pr create -H other-branch --fill",
        "gh pr create -B other-base --fill",
    ):
        raw = _raw(command)
        action = common.normalize(raw, "codex")
        result = common._enforce_repository_posture(raw, action, Decision("allow", "ok", "pr-publish"))
        assert result.decision == "deny"


def test_pr_create_allows_current_published_feature_branch(monkeypatch):
    result = _allow("gh pr create --fill", monkeypatch, _published_feature_git, "pr-publish")
    assert result.decision == "allow"


def test_pr_create_denies_detached_head(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("branch", "--show-current"):
            return "", None
        raise AssertionError(args)

    result = _allow("gh pr create --fill", monkeypatch, fake_git, "pr-publish")
    assert result.decision == "deny"


def test_pr_create_denies_default_branch(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("branch", "--show-current"):
            return "main", None
        raise AssertionError(args)

    result = _allow("gh pr create --fill", monkeypatch, fake_git, "pr-publish")
    assert result.decision == "deny"


def test_pr_create_denies_origin_repository_mismatch(monkeypatch):
    def fake_git(_cwd, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): ("https://github.com/other/repository.git", None),
        }
        return values[tuple(args)]

    result = _allow("gh pr create --fill", monkeypatch, fake_git, "pr-publish")
    assert result.decision == "deny"


def test_pr_create_requires_published_current_branch_upstream(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return None, "no upstream configured"
        return _published_feature_git(_cwd, args)

    result = _allow("gh pr create --fill", monkeypatch, fake_git, "pr-publish")
    assert result.decision == "deny"


def test_pr_create_denies_wrong_upstream(monkeypatch):
    def fake_git(_cwd, args):
        if tuple(args) == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return "origin/other", None
        return _published_feature_git(_cwd, args)

    result = _allow("gh pr create --fill", monkeypatch, fake_git, "pr-publish")
    assert result.decision == "deny"
