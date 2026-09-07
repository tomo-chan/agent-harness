#!/usr/bin/env python3
"""Launch the generic policy adapter from a trusted harness installation.

S1 establishes only the trusted execution and policy boundary. Vendor-specific
adapter selection belongs to S6, so this launcher binds one fixed generic hook
adapter plus trusted policy inputs inside ``AGENT_HARNESS_TRUSTED_ROOT``.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PYTHON_STARTUP_ENV = {
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "PYTHONINSPECT",
}


def _inside(root: Path, path: Path) -> bool:
    """Return whether ``path`` resolves inside the trusted ``root`` directory."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _trusted_file(root: Path, env_name: str, default: Path) -> Path:
    """Resolve one trusted file and reject paths outside the trusted root."""
    value = os.environ.get(env_name)
    path = Path(value).expanduser().resolve() if value else default.resolve()
    if not _inside(root, path):
        raise RuntimeError(f"{env_name} must resolve inside AGENT_HARNESS_TRUSTED_ROOT")
    if not path.is_file():
        raise RuntimeError(f"trusted file does not exist: {path}")
    return path


def _trusted_repository() -> str | None:
    """Return the deployment-supplied expected repository in canonical form."""
    value = os.environ.get("AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY")
    if value is None:
        return None
    value = value.strip()
    if not _REPOSITORY_RE.fullmatch(value):
        raise RuntimeError(
            "AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY must be owner/repository"
        )
    return value


def _sanitize_python_startup_environment() -> None:
    """Remove inherited Python startup controls before entering trusted code.

    Repository-controlled startup variables must not influence the fresh Python
    interpreter used for the trusted adapter. The adapter is also launched with
    ``-I`` so user site packages and environment-based Python path configuration
    remain disabled even when this launcher itself was not started in isolated
    mode.
    """
    for name in _PYTHON_STARTUP_ENV:
        os.environ.pop(name, None)


def main() -> int:
    """Validate trusted files and identity, then exec the fixed policy adapter."""
    configured = os.environ.get("AGENT_HARNESS_TRUSTED_ROOT")
    if not configured:
        print("AGENT_HARNESS_TRUSTED_ROOT is required", file=sys.stderr)
        return 2

    trusted_root = Path(configured).expanduser().resolve()
    actual_root = Path(__file__).resolve().parents[2]
    if actual_root != trusted_root:
        print(
            f"trusted harness root mismatch: configured={trusted_root} actual={actual_root}",
            file=sys.stderr,
        )
        return 2

    try:
        policy = _trusted_file(
            trusted_root,
            "AGENT_HARNESS_TRUSTED_POLICY",
            trusted_root / "reference" / "policies" / "policy.example.json",
        )
        repository_security = _trusted_file(
            trusted_root,
            "AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY",
            trusted_root / "reference" / "policies" / "repository-security.example.json",
        )
        expected_repository = _trusted_repository()
        adapter = (
            trusted_root / "reference" / "hooks" / "pre_tool_use_adapter.py"
        ).resolve()
        if not _inside(trusted_root, adapter) or not adapter.is_file():
            raise RuntimeError(f"trusted adapter does not exist inside trusted root: {adapter}")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    os.environ["AGENT_HARNESS_POLICY"] = str(policy)
    os.environ["AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY"] = str(
        repository_security
    )
    if expected_repository is None:
        os.environ.pop("AGENT_HARNESS_EXPECTED_REPOSITORY", None)
    else:
        os.environ["AGENT_HARNESS_EXPECTED_REPOSITORY"] = expected_repository

    os.environ.pop("AGENT_POLICY", None)
    os.environ.pop("AGENT_HARNESS_REPOSITORY_SECURITY_POLICY", None)
    os.environ.pop("AGENT_HARNESS_MINIMUM_POSTURE_MODE", None)
    _sanitize_python_startup_environment()
    os.execv(sys.executable, [sys.executable, "-I", str(adapter)])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
