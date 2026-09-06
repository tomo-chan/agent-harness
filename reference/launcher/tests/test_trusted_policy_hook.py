from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "reference" / "launcher" / "trusted_policy_hook.py"


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the trusted S1 launcher with a controlled environment."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def test_trusted_policy_hook_requires_trusted_root() -> None:
    env = os.environ.copy()
    env.pop("AGENT_HARNESS_TRUSTED_ROOT", None)
    result = _run(env)
    assert result.returncode != 0
    assert "AGENT_HARNESS_TRUSTED_ROOT is required" in result.stderr


def test_trusted_policy_hook_rejects_root_mismatch(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["AGENT_HARNESS_TRUSTED_ROOT"] = str(tmp_path)
    result = _run(env)
    assert result.returncode != 0
    assert "trusted harness root mismatch" in result.stderr


def test_trusted_policy_hook_rejects_policy_outside_trusted_root(tmp_path: Path) -> None:
    outside = tmp_path / "policy.json"
    outside.write_text('{"default":"ask"}', encoding="utf-8")
    env = os.environ.copy()
    env["AGENT_HARNESS_TRUSTED_ROOT"] = str(ROOT)
    env["AGENT_HARNESS_TRUSTED_POLICY"] = str(outside)
    result = _run(env)
    assert result.returncode != 0
    assert "must resolve inside AGENT_HARNESS_TRUSTED_ROOT" in result.stderr


def test_trusted_policy_hook_rejects_repository_security_outside_root(
    tmp_path: Path,
) -> None:
    """The S2 minimum baseline must be selected through the S1 trust boundary."""
    outside = tmp_path / "repository-security.json"
    outside.write_text('{"mode":"warn"}', encoding="utf-8")
    env = os.environ.copy()
    env["AGENT_HARNESS_TRUSTED_ROOT"] = str(ROOT)
    env["AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY"] = str(outside)
    result = _run(env)
    assert result.returncode != 0
    assert "must resolve inside AGENT_HARNESS_TRUSTED_ROOT" in result.stderr


def test_trusted_policy_hook_rejects_invalid_trusted_repository() -> None:
    """Repository identity crosses S1 only in canonical owner/repository form."""
    env = os.environ.copy()
    env["AGENT_HARNESS_TRUSTED_ROOT"] = str(ROOT)
    env["AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY"] = "not a repository"
    result = _run(env)
    assert result.returncode != 0
    assert "must be owner/repository" in result.stderr


def test_trusted_policy_hook_does_not_accept_adapter_override() -> None:
    """S1 fixes the generic adapter; vendor or repository input cannot replace it."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "AGENT_HARNESS_TRUSTED_ADAPTER" not in text


def test_trusted_policy_hook_sanitizes_untrusted_policy_overrides() -> None:
    """Legacy and weakening policy selectors must not survive the trusted entrypoint."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'os.environ["AGENT_HARNESS_POLICY"]' in text
    assert 'os.environ["AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY"]' in text
    assert 'os.environ.pop("AGENT_POLICY", None)' in text
    assert 'os.environ.pop("AGENT_HARNESS_REPOSITORY_SECURITY_POLICY", None)' in text
    assert 'os.environ.pop("AGENT_HARNESS_MINIMUM_POSTURE_MODE", None)' in text


def test_trusted_policy_hook_rebinds_expected_repository() -> None:
    """Only the trusted repository selector may populate the S2 compatibility input."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'os.environ.get("AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY")' in text
    assert 'os.environ["AGENT_HARNESS_EXPECTED_REPOSITORY"] = expected_repository' in text
    assert 'os.environ.pop("AGENT_HARNESS_EXPECTED_REPOSITORY", None)' in text
