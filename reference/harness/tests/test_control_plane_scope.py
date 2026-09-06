"""Regression checks for publication control-plane scope and SCM detection."""

from __future__ import annotations

from reference.harness import common


def _action(command: str) -> dict:
    """Build the minimal normalized action needed for SCM mutation detection."""
    return {"input": {"command": command}}


def test_security_relevant_reference_paths_are_control_plane() -> None:
    """Protect runtime assurance, deployment, and managed configuration paths."""
    protected = (
        "reference/scripts/completion_gate.sh",
        "reference/kubernetes/agent-pod.yaml",
        "reference/claude/managed-settings.example.json",
        "reference/codex/config.example.toml",
        ".github/pull_request_template.md",
    )
    for path in protected:
        assert common._is_control_plane_path(path), path


def test_ordinary_source_and_docs_are_not_control_plane() -> None:
    """Keep ordinary application code and explanatory documents outside this gate."""
    assert not common._is_control_plane_path("src/app.py")
    assert not common._is_control_plane_path("docs/03-security-model.md")


def test_restricted_scm_detection_handles_git_global_options() -> None:
    """Recognize direct Git push even when Git global options precede the subcommand."""
    assert common._is_scm_mutation(_action("git -c credential.helper= push"))
    assert common._is_scm_mutation(_action("/usr/bin/git -c foo.bar=baz push origin HEAD"))


def test_restricted_scm_detection_handles_gh_global_options() -> None:
    """Recognize GitHub CLI mutations with global options before subcommands."""
    assert common._is_scm_mutation(_action("gh --repo acme/widget pr create --fill"))
    assert common._is_scm_mutation(_action("gh --hostname github.com pr merge 42"))


def test_scm_detection_does_not_claim_dynamic_child_process_mediation() -> None:
    """Do not pretend dynamically constructed child commands are directly observable."""
    assert not common._is_scm_mutation(_action("sh -c \"$SCM_COMMAND\""))
