"""Connect vendor lifecycle adapters to the S1-S5 guarantee implementation.

This module contains no vendor response schema. It supplies the common lifecycle
operations used by Claude Code, Codex, and Devin adapters: trusted PreToolUse
evaluation, non-authoritative SessionStart context, and authoritative Stop-time
completion assurance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference.harness.authority import repository_posture_context  # noqa: E402
from reference.harness.completion import capture_session_start, completion_check  # noqa: E402
from reference.hooks.pre_tool_use_adapter import evaluate as evaluate_pre_tool_use  # noqa: E402


def read_stdin() -> dict[str, Any]:
    """Read one vendor hook payload and require a JSON object."""
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    return value


def emit(value: dict[str, Any]) -> int:
    """Emit one compact JSON hook response."""
    json.dump(value, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


def session_start_context(raw: dict[str, Any]) -> str:
    """Return diagnostic posture and completion context for SessionStart."""
    return f"{repository_posture_context(raw)} {capture_session_start(raw)}"


def completion(raw: dict[str, Any]) -> tuple[bool, str]:
    """Run S5 Stop-time completion assurance for one vendor event."""
    return completion_check(raw)
