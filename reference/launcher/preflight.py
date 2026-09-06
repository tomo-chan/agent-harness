#!/usr/bin/env python3
"""Check repository security posture before launching an agent session."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POSTURE_DIR = ROOT / "reference" / "posture"
if str(POSTURE_DIR) not in sys.path:
    sys.path.insert(0, str(POSTURE_DIR))

from checker import check_repository_posture  # noqa: E402


def main() -> int:
    """Evaluate repository posture and return a launcher-friendly exit status.

    Exit status 2 represents a blocked or failed posture evaluation. With
    ``--require-ready``, exit status 1 represents a valid but non-READY state.
    """
    parser = argparse.ArgumentParser(
        description="Check repository security posture before starting an agent session."
    )
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return non-zero unless the posture state is READY",
    )
    args = parser.parse_args()

    try:
        report = check_repository_posture(Path(args.cwd))
    except Exception as exc:
        if args.json:
            print(json.dumps({"state": "UNKNOWN", "error": str(exc)}))
        else:
            print(f"repository posture UNKNOWN: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary())

    if report.state == "BLOCKED":
        return 2
    if args.require_ready and report.state != "READY":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
