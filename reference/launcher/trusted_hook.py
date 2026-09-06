#!/usr/bin/env python3
"""Launch vendor hook adapters from the trusted harness installation.

This module is part of the production trust boundary. It validates that the
configured harness root matches the installation containing this file, resolves
trusted policy and adapter paths only inside that root, and then replaces the
current process with the selected vendor adapter.

Repository-local posture configuration is intentionally not replaced here. The
trusted posture file is exported as a minimum baseline; the checker later treats
``.agent-harness/security.json`` as untrusted input that may only strengthen that
baseline.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SUPPORTED_VENDORS = {"claude", "codex", "devin"}


def _inside(root: Path, path: Path) -> bool:
    """Return whether ``path`` resolves inside the trusted ``root`` directory."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _trusted_path(root: Path, env_name: str, default: Path) -> Path:
    """Resolve a trusted file path and reject paths outside the trusted root.

    Args:
        root: Trusted harness root established by the launcher.
        env_name: Optional environment variable that overrides ``default``.
        default: Default file path inside ``root``.

    Returns:
        The resolved existing file path.

    Raises:
        RuntimeError: If the path escapes ``root`` or does not name a file.
    """
    value = os.environ.get(env_name)
    path = Path(value).expanduser().resolve() if value else default.resolve()
    if not _inside(root, path):
        raise RuntimeError(f"{env_name} must resolve inside AGENT_HARNESS_TRUSTED_ROOT")
    if not path.is_file():
        raise RuntimeError(f"trusted file does not exist: {path}")
    return path


def main() -> int:
    """Validate trusted launcher state and execute the selected vendor adapter.

    The function fails closed when trusted-root identity or trusted files cannot
    be established. On success, ``os.execv`` replaces this process and therefore
    does not normally return.
    """
    if len(sys.argv) != 2 or sys.argv[1] not in SUPPORTED_VENDORS:
        print("usage: trusted_hook.py <claude|codex|devin>", file=sys.stderr)
        return 2

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
        policy = _trusted_path(
            trusted_root,
            "AGENT_HARNESS_TRUSTED_POLICY",
            trusted_root / "reference" / "policies" / "policy.example.json",
        )
        posture_baseline = _trusted_path(
            trusted_root,
            "AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY",
            trusted_root / "reference" / "policies" / "repository-security.example.json",
        )
        adapter = _trusted_path(
            trusted_root,
            "AGENT_HARNESS_TRUSTED_ADAPTER",
            trusted_root / "reference" / "harness" / f"{sys.argv[1]}.py",
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    os.environ["AGENT_HARNESS_POLICY"] = str(policy)
    os.environ["AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY"] = str(posture_baseline)
    os.environ.pop("AGENT_HARNESS_REPOSITORY_SECURITY_POLICY", None)

    os.execv(sys.executable, [sys.executable, str(adapter)])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
