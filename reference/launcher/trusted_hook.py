#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

SUPPORTED_VENDORS = {"claude", "codex", "devin"}


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _trusted_path(root: Path, env_name: str, default: Path) -> Path:
    value = os.environ.get(env_name)
    path = Path(value).expanduser().resolve() if value else default.resolve()
    if not _inside(root, path):
        raise RuntimeError(f"{env_name} must resolve inside AGENT_HARNESS_TRUSTED_ROOT")
    if not path.is_file():
        raise RuntimeError(f"trusted file does not exist: {path}")
    return path


def main() -> int:
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
        repository_policy = _trusted_path(
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

    # The existing harness modules already consume these variables. Override them here
    # so repository-controlled files cannot redirect production evaluation to a mutable
    # policy or posture policy.
    os.environ["AGENT_HARNESS_POLICY"] = str(policy)
    os.environ["AGENT_HARNESS_REPOSITORY_SECURITY_POLICY"] = str(repository_policy)

    os.execv(sys.executable, [sys.executable, str(adapter)])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
