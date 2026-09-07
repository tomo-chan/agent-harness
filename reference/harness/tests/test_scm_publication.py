from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from reference.harness import scm_publication
from reference.hooks.policy_engine import Decision

BRANCH = "feature/review-fix"
REFSPEC = f"HEAD:refs/heads/{BRANCH}"
NORMAL_PUSH = f"git push origin {REFSPEC}"
FIRST_PUSH = f"git push --set-upstream origin {REFSPEC}"
HEAD = "abc123"


def _raw(tmp_path: Path, command: str) -> dict:
    return {
        "tool": "exec",
        "input": {"command": command},
        "cwd": str(tmp_path),
        "session_id": "s3-test",
    }


def _action(command: str) -> dict:
    return {"tool": "exec", "input": {"command": command}}


def _report(state: str = "READY"):
    return SimpleNamespace(
        state=state,
        repository="tomo-chan/agent-harness",
        default_branch="main",
        summary=lambda: f"repository posture {state}",
    )


def _published_feature_git(_cwd: Path, args):
    values = {
        ("branch", "--show-current"): (BRANCH, None),
        ("remote", "get-url", "origin"): (
            "https://github.com/tomo-chan/agent-harness.git",
            None,
        ),
        ("remote", "get-url", "--push", "--all", "origin"): (
            "https://github.com/tomo-chan/agent-harness.git",
            None,
        ),
        ("config", "--bool", "--get", "remote.origin.mirror"): ("false", None),
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): (
            f"origin/{BRANCH}",
            None,
        ),
        ("rev-parse", "HEAD"): (HEAD, None),
    }
    return values[tuple(args)]


def _allow_publication(tmp_path: Path, monkeypatch, command: str, fake_git):
    monkeypatch.setattr(
        scm_publication.authority,
        "enforce_repository_authority",
        lambda raw, result, **kwargs: result,
    )
    monkeypatch.setattr(
        scm_publication.authority,
        "current_repository_posture",
        lambda *args, **kwargs: _report("READY"),
    )
    monkeypatch.setattr(scm_publication, "_run_git", fake_git)
    monkeypatch.setattr(
        scm_publication,
        "_github_branch_head",
        lambda cwd, repository, branch: (HEAD, None),
    )
    return scm_publication.validate_autonomous_publication(
        _raw(tmp_path, command),
        _action(command),
        Decision("allow", "candidate", "candidate"),
    )


def test_direct_push_and_pr_create_are_restricted_publications() -> None:
    assert scm_publication.is_scm_publication(_action(NORMAL_PUSH)) is True
    assert scm_publication.is_scm_publication(_action("gh pr create --fill")) is True
    assert scm_publication.is_scm_publication(_action("git status")) is False


def test_restricted_authority_precedes_publication_semantics(
    tmp_path: Path, monkeypatch
) -> None:
    observed: dict[str, object] = {}

    def fake_authority(raw, result, *, mutation, restricted_operation):
        observed["mutation"] = mutation
        observed["restricted_operation"] = restricted_operation
        return Decision("deny", "restricted", "repository-authority")

    monkeypatch.setattr(scm_publication.authority, "enforce_repository_authority", fake_authority)
    result = scm_publication.validate_autonomous_publication(
        _raw(tmp_path, NORMAL_PUSH),
        _action(NORMAL_PUSH),
        Decision("allow", "candidate", "canonical-git-push"),
    )
    assert result.decision == "deny"
    assert result.rule == "repository-authority"
    assert observed["mutation"] is True
    assert observed["restricted_operation"] is True


def test_noncanonical_push_is_not_autonomously_allowed(tmp_path: Path, monkeypatch) -> None:
    result = _allow_publication(
        tmp_path, monkeypatch, "git push origin feature/review-fix", _published_feature_git
    )
    assert result.decision == "deny"
    assert result.rule == "canonical-git-push"


def test_canonical_push_allows_checked_current_branch(tmp_path: Path, monkeypatch) -> None:
    result = _allow_publication(tmp_path, monkeypatch, NORMAL_PUSH, _published_feature_git)
    assert result.decision == "allow"


def test_canonical_push_denies_detached_head(tmp_path: Path, monkeypatch) -> None:
    def fake_git(_cwd: Path, args):
        if tuple(args) == ("branch", "--show-current"):
            return "", None
        raise AssertionError(args)

    result = _allow_publication(tmp_path, monkeypatch, NORMAL_PUSH, fake_git)
    assert result.decision == "deny"
    assert "detached HEAD" in result.reason


def test_canonical_push_denies_default_branch(tmp_path: Path, monkeypatch) -> None:
    command = "git push origin HEAD:refs/heads/main"

    def fake_git(_cwd: Path, args):
        if tuple(args) == ("branch", "--show-current"):
            return "main", None
        raise AssertionError(args)

    result = _allow_publication(tmp_path, monkeypatch, command, fake_git)
    assert result.decision == "deny"
    assert "default branch" in result.reason


def test_canonical_push_denies_origin_mismatch(tmp_path: Path, monkeypatch) -> None:
    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): ("https://github.com/other/repository.git", None),
        }
        return values[tuple(args)]

    result = _allow_publication(tmp_path, monkeypatch, NORMAL_PUSH, fake_git)
    assert result.decision == "deny"
    assert "origin" in result.reason


def test_canonical_push_denies_effective_pushurl_mismatch(tmp_path: Path, monkeypatch) -> None:
    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): (
                "https://github.com/tomo-chan/agent-harness.git",
                None,
            ),
            ("remote", "get-url", "--push", "--all", "origin"): (
                "https://github.com/other/repository.git",
                None,
            ),
        }
        return values[tuple(args)]

    result = _allow_publication(tmp_path, monkeypatch, NORMAL_PUSH, fake_git)
    assert result.decision == "deny"
    assert "push URL" in result.reason


def test_canonical_push_denies_multiple_push_urls(tmp_path: Path, monkeypatch) -> None:
    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): (
                "https://github.com/tomo-chan/agent-harness.git",
                None,
            ),
            ("remote", "get-url", "--push", "--all", "origin"): (
                "https://github.com/tomo-chan/agent-harness.git\n"
                "https://github.com/tomo-chan/agent-harness.git",
                None,
            ),
        }
        return values[tuple(args)]

    result = _allow_publication(tmp_path, monkeypatch, NORMAL_PUSH, fake_git)
    assert result.decision == "deny"
    assert "exactly one" in result.reason


def test_canonical_push_denies_mirror_remote(tmp_path: Path, monkeypatch) -> None:
    def fake_git(_cwd: Path, args):
        values = {
            ("branch", "--show-current"): (BRANCH, None),
            ("remote", "get-url", "origin"): (
                "https://github.com/tomo-chan/agent-harness.git",
                None,
            ),
            ("remote", "get-url", "--push", "--all", "origin"): (
                "https://github.com/tomo-chan/agent-harness.git",
                None,
            ),
            ("config", "--bool", "--get", "remote.origin.mirror"): ("true", None),
        }
        return values[tuple(args)]

    result = _allow_publication(tmp_path, monkeypatch, NORMAL_PUSH, fake_git)
    assert result.decision == "deny"
    assert "mirror" in result.reason


def test_plain_push_requires_matching_upstream(tmp_path: Path, monkeypatch) -> None:
    def fake_git(_cwd: Path, args):
        if tuple(args) == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return "origin/other", None
        return _published_feature_git(_cwd, args)

    result = _allow_publication(tmp_path, monkeypatch, NORMAL_PUSH, fake_git)
    assert result.decision == "deny"
    assert f"origin/{BRANCH}" in result.reason


def test_first_publish_form_allows_without_upstream(tmp_path: Path, monkeypatch) -> None:
    def fake_git(_cwd: Path, args):
        if tuple(args) == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return None, "no upstream configured"
        return _published_feature_git(_cwd, args)

    result = _allow_publication(tmp_path, monkeypatch, FIRST_PUSH, fake_git)
    assert result.decision == "allow"


def test_first_publish_form_denies_when_upstream_exists(tmp_path: Path, monkeypatch) -> None:
    result = _allow_publication(tmp_path, monkeypatch, FIRST_PUSH, _published_feature_git)
    assert result.decision == "deny"
    assert "first publication" in result.reason


def test_pr_create_requires_published_current_branch(tmp_path: Path, monkeypatch) -> None:
    result = _allow_publication(tmp_path, monkeypatch, "gh pr create --fill", _published_feature_git)
    assert result.decision == "allow"


def test_pr_create_rejects_target_overrides_in_separate_and_equals_forms(
    tmp_path: Path, monkeypatch
) -> None:
    commands = (
        "gh pr create --repo other/repo --fill",
        "gh pr create --repo=other/repo --fill",
        "gh pr create --head=other --fill",
        "gh pr create --base=other --fill",
        "gh pr create -Rother/repo --fill",
    )
    for command in commands:
        result = _allow_publication(tmp_path, monkeypatch, command, _published_feature_git)
        assert result.decision == "deny"
        assert "may not override" in result.reason


def test_pr_create_denies_when_local_head_is_not_published(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        scm_publication.authority,
        "enforce_repository_authority",
        lambda raw, result, **kwargs: result,
    )
    monkeypatch.setattr(
        scm_publication.authority,
        "current_repository_posture",
        lambda *args, **kwargs: _report("READY"),
    )
    monkeypatch.setattr(scm_publication, "_run_git", _published_feature_git)
    monkeypatch.setattr(
        scm_publication,
        "_github_branch_head",
        lambda cwd, repository, branch: ("different", None),
    )
    result = scm_publication.validate_autonomous_publication(
        _raw(tmp_path, "gh pr create --fill"),
        _action("gh pr create --fill"),
        Decision("allow", "candidate", "canonical-pr-create"),
    )
    assert result.decision == "deny"
    assert "not the published head" in result.reason


def test_compound_shell_with_push_is_still_classified_as_publication() -> None:
    command = f"git status && {NORMAL_PUSH}"
    assert scm_publication.has_compound_shell(command) is True
    assert scm_publication.is_scm_publication(_action(command)) is True


def test_compound_shell_cannot_be_autonomously_allowed(tmp_path: Path, monkeypatch) -> None:
    command = f"git status && {NORMAL_PUSH}"
    observed: dict[str, object] = {}

    def fake_authority(raw, result, *, mutation, restricted_operation):
        observed["restricted_operation"] = restricted_operation
        return result

    monkeypatch.setattr(scm_publication.authority, "enforce_repository_authority", fake_authority)
    result = scm_publication.validate_autonomous_publication(
        _raw(tmp_path, command),
        _action(command),
        Decision("allow", "overbroad lower policy", "allow-git-read"),
    )
    assert observed["restricted_operation"] is True
    assert result.decision == "ask"
    assert result.rule == "compound-shell"
