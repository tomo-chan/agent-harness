from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_project_hook_configs_require_trusted_root() -> None:
    paths = [
        ROOT / ".claude" / "settings.json",
        ROOT / ".codex" / "hooks.json",
        ROOT / ".devin" / "hooks.v1.json",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "AGENT_HARNESS_TRUSTED_ROOT" in text
        assert "reference/launcher/trusted_hook.py" in text
        assert "git rev-parse --show-toplevel" not in text


def test_trusted_wrapper_rejects_missing_trusted_root() -> None:
    script = ROOT / "reference" / "launcher" / "trusted_hook.py"
    env = os.environ.copy()
    env.pop("AGENT_HARNESS_TRUSTED_ROOT", None)
    result = subprocess.run(
        [sys.executable, str(script), "claude"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "AGENT_HARNESS_TRUSTED_ROOT is required" in result.stderr


def test_trusted_wrapper_rejects_root_mismatch(tmp_path: Path) -> None:
    script = ROOT / "reference" / "launcher" / "trusted_hook.py"
    env = os.environ.copy()
    env["AGENT_HARNESS_TRUSTED_ROOT"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(script), "claude"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "trusted harness root mismatch" in result.stderr


def test_kubernetes_baseline_uses_read_only_trusted_root() -> None:
    text = (ROOT / "reference" / "kubernetes" / "agent-pod.yaml").read_text(encoding="utf-8")
    assert "AGENT_HARNESS_TRUSTED_ROOT" in text
    assert "value: /opt/agent-harness" in text
    assert "readOnlyRootFilesystem: true" in text
    assert "AGENT_HARNESS_REPOSITORY_SECURITY_POLICY" in text


def test_hook_configs_remain_valid_json() -> None:
    for path in [
        ROOT / ".claude" / "settings.json",
        ROOT / ".codex" / "hooks.json",
        ROOT / ".devin" / "hooks.v1.json",
    ]:
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
