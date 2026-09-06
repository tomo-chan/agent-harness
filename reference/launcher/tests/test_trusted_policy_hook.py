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
