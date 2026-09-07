#!/usr/bin/env python3
"""Launch fixed vendor adapters from the trusted Agent Harness installation.

S6 extends the S1 trust boundary only with a closed vendor-to-adapter mapping. It
does not reintroduce arbitrary adapter overrides. Trusted policy, repository
minimum policy, and expected repository are validated through the same S1 rules
before the selected adapter replaces this process.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from trusted_policy_hook import _inside, _trusted_file, _trusted_repository

_VENDOR_ADAPTERS = {
    "claude": Path("reference/harness/claude.py"),
    "codex": Path("reference/harness/codex.py"),
    "devin": Path("reference/harness/devin.py"),
}


def main() -> int:
    """Validate S1 trusted inputs and exec one fixed S6 vendor adapter."""
    if len(sys.argv) != 2 or sys.argv[1] not in _VENDOR_ADAPTERS:
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
        adapter = (trusted_root / _VENDOR_ADAPTERS[sys.argv[1]]).resolve()
        if not _inside(trusted_root, adapter) or not adapter.is_file():
            raise RuntimeError(f"trusted vendor adapter does not exist inside trusted root: {adapter}")
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
    os.environ.pop("AGENT_HARNESS_TRUSTED_ADAPTER", None)

    os.execv(sys.executable, [sys.executable, str(adapter)])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
