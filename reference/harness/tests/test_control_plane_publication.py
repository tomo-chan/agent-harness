from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from reference.harness import control_plane_publication
from reference.hooks.policy_engine import Decision


def _raw(tmp_path: Path) -> dict:
    return {"cwd": str(tmp_path), "session_id": "s4-test"}


def _report():
    return SimpleNamespace(
        state="READY",
        repository="tomo-chan/agent-harness",
        default_branch="main",
        summary=lambda: "repository posture READY",
    )


def test_control_plane_path_classification() -> None:
    assert control_plane_publication.is_control_plane_path("reference/harness/scm_publication.py")
    assert control_plane_publication.is_control_plane_path(".github/workflows/test.yml")
    assert control_plane_publication.is_control_plane_path("AGENTS.md")
    assert not control_plane_publication.is_control_plane_path("src/application.py")


def test_review_uses_authoritative_github_default_head(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        control_plane_publication,
        "_github_branch_head",
        lambda cwd, repository, branch: ("deadbeef", None),
    )

    observed: list[tuple[str, ...]] = []

    def fake_git(_cwd: Path, args):
        key = tuple(args)
        observed.append(key)
        values = {
            ("cat-file", "-e", "deadbeef^{commit}"): ("", None),
            ("diff", "--name-only", "deadbeef...HEAD"): (
                "src/app.py\nreference/harness/scm_publication.py",
                None,
            ),
        }
        if key == ("diff", "--name-only", "origin/main...HEAD"):
            raise AssertionError("mutable remote-tracking ref must not be authority")
        return values[key]

    monkeypatch.setattr(control_plane_publication, "_run_git", fake_git)
    result = control_plane_publication.control_plane_publication_decision(
        _raw(tmp_path), _report()
    )

    assert result is not None
    assert result.decision == "ask"
    assert result.rule == "control-plane-publication"
    assert ("diff", "--name-only", "deadbeef...HEAD") in observed


def test_non_control_plane_diff_remains_autonomous(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        control_plane_publication,
        "_github_branch_head",
        lambda cwd, repository, branch: ("deadbeef", None),
    )

    def fake_git(_cwd: Path, args):
        values = {
            ("cat-file", "-e", "deadbeef^{commit}"): ("", None),
            ("diff", "--name-only", "deadbeef...HEAD"): ("src/app.py\nREADME.md", None),
        }
        return values[tuple(args)]

    monkeypatch.setattr(control_plane_publication, "_run_git", fake_git)
    assert (
        control_plane_publication.control_plane_publication_decision(
            _raw(tmp_path), _report()
        )
        is None
    )


def test_missing_github_default_head_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        control_plane_publication,
        "_github_branch_head",
        lambda cwd, repository, branch: (None, "GitHub unavailable"),
    )
    result = control_plane_publication.control_plane_publication_decision(
        _raw(tmp_path), _report()
    )
    assert result is not None
    assert result.decision == "deny"
    assert "GitHub default-branch head" in result.reason


def test_missing_authoritative_commit_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        control_plane_publication,
        "_github_branch_head",
        lambda cwd, repository, branch: ("deadbeef", None),
    )
    monkeypatch.setattr(
        control_plane_publication,
        "_run_git",
        lambda cwd, args: (None, "missing commit"),
    )
    result = control_plane_publication.control_plane_publication_decision(
        _raw(tmp_path), _report()
    )
    assert result is not None
    assert result.decision == "deny"
    assert "not available locally" in result.reason


def test_s4_runs_only_after_s3_allows_publication(tmp_path: Path, monkeypatch) -> None:
    action = {"tool": "exec", "input": {"command": "git push origin HEAD:refs/heads/x"}}
    monkeypatch.setattr(
        control_plane_publication.scm_publication,
        "validate_autonomous_publication",
        lambda raw, action, result: Decision("ask", "S3 review", "s3"),
    )
    monkeypatch.setattr(
        control_plane_publication.scm_publication,
        "is_scm_publication",
        lambda action: True,
    )
    result = control_plane_publication.validate_publication(
        _raw(tmp_path), action, Decision("allow", "candidate", "candidate")
    )
    assert result.decision == "ask"
    assert result.rule == "s3"


def test_s4_promotes_allowed_publication_to_review(tmp_path: Path, monkeypatch) -> None:
    action = {"tool": "exec", "input": {"command": "git push origin HEAD:refs/heads/x"}}
    monkeypatch.setattr(
        control_plane_publication.scm_publication,
        "validate_autonomous_publication",
        lambda raw, action, result: Decision("allow", "S3 clear", "s3"),
    )
    monkeypatch.setattr(
        control_plane_publication.scm_publication,
        "is_scm_publication",
        lambda action: True,
    )
    monkeypatch.setattr(
        control_plane_publication.authority,
        "current_repository_posture",
        lambda *args, **kwargs: _report(),
    )
    monkeypatch.setattr(
        control_plane_publication,
        "control_plane_publication_decision",
        lambda raw, report: Decision("ask", "control plane", "control-plane-publication"),
    )

    result = control_plane_publication.validate_publication(
        _raw(tmp_path), action, Decision("allow", "candidate", "candidate")
    )
    assert result.decision == "ask"
    assert result.rule == "control-plane-publication"
