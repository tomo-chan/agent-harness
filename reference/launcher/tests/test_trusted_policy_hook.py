from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "reference" / "launcher" / "trusted_policy_hook.py"


def test_trusted_policy_hook_requires_trusted_root() -> None:
    env = os.environ.copy()
    env.pop("AGENT_HARNESS_TRUSTED_ROOT", None)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "AGENT_HARNESS_TRUSTED_ROOT is required" in result.stderr


def test_trusted_policy_hook_rejects_root_mismatch(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["AGENT_HARNESS_TRUSTED_ROOT"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "trusted harness root mismatch" in result.stderr


def test_trusted_policy_hook_rejects_policy_outside_trusted_root(tmp_path: Path) -> None:
    outside = tmp_path / "policy.json"
    outside.write_text('{"default":"ask"}', encoding="utf-8")
    env = os.environ.copy()
    env["AGENT_HARNESS_TRUSTED_ROOT"] = str(ROOT)
    env["AGENT_HARNESS_TRUSTED_POLICY"] = str(outside)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "must resolve inside AGENT_HARNESS_TRUSTED_ROOT" in result.stderr


def test_trusted_policy_hook_does_not_accept_adapter_override(tmp_path: Path) -> None:
    """S1 fixes the generic adapter; vendor or repository input cannot replace it."""
    fake_adapter = tmp_path / "adapter.py"
    fake_adapter.write_text("raise SystemExit(0)\n", encoding="utf-8")
    text = SCRIPT.read_text(encoding="utf-8")
    assert "AGENT_HARNESS_TRUSTED_ADAPTER" not in text


def test_trusted_policy_hook_removes_legacy_repository_policy_variable() -> None:
    """The launcher must not leave the legacy repository-selectable policy path active."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'os.environ.pop("AGENT_POLICY", None)' in text
    assert 'os.environ["AGENT_HARNESS_POLICY"]' in text
