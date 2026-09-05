#!/usr/bin/env python3
"""Deterministic application-architecture gate.

The harness supplies enforcement primitives. This gate lets an application declare
machine-verifiable architectural invariants without depending on an LLM review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SUPPORTED_CHECKS = {
    "path_exists",
    "path_absent",
    "file_contains_regex",
    "file_not_contains_regex",
}


@dataclass(frozen=True)
class CheckResult:
    id: str
    status: str  # pass | fail | waived
    reason: str


@dataclass(frozen=True)
class GateResult:
    status: str  # pass | fail
    checks: list[CheckResult]

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "checks": [asdict(item) for item in self.checks]}


class GateConfigError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GateConfigError("architecture contract must be a JSON object")
    if value.get("version") != 1:
        raise GateConfigError("architecture contract version must be 1")
    checks = value.get("checks")
    if not isinstance(checks, list) or not checks:
        raise GateConfigError("checks must be a non-empty array")
    ids: set[str] = set()
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise GateConfigError(f"checks[{index}] must be an object")
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id:
            raise GateConfigError(f"checks[{index}].id is required")
        if check_id in ids:
            raise GateConfigError(f"duplicate check id: {check_id}")
        ids.add(check_id)
        if check.get("type") not in SUPPORTED_CHECKS:
            raise GateConfigError(f"unsupported check type for {check_id}: {check.get('type')}")
        if not isinstance(check.get("path"), str) or not check["path"]:
            raise GateConfigError(f"path is required for {check_id}")
        if check["type"] in {"file_contains_regex", "file_not_contains_regex"}:
            pattern = check.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                raise GateConfigError(f"pattern is required for {check_id}")
            re.compile(pattern)
    waivers = value.get("waivers", [])
    if not isinstance(waivers, list):
        raise GateConfigError("waivers must be an array")
    for index, waiver in enumerate(waivers):
        if not isinstance(waiver, dict):
            raise GateConfigError(f"waivers[{index}] must be an object")
        if waiver.get("check_id") not in ids:
            raise GateConfigError(f"waivers[{index}] references unknown check")
        for key in ("reason", "owner", "expires"):
            if not isinstance(waiver.get(key), str) or not waiver[key]:
                raise GateConfigError(f"waivers[{index}].{key} is required")
        try:
            dt.date.fromisoformat(waiver["expires"])
        except ValueError as exc:
            raise GateConfigError(f"invalid waiver expiry: {waiver['expires']}") from exc
    return value


def _safe_path(root: Path, raw: str) -> Path:
    target = (root / raw).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise GateConfigError(f"architecture check path escapes repository: {raw}") from exc
    return target


def _evaluate_check(root: Path, check: dict[str, Any]) -> CheckResult:
    check_id = check["id"]
    target = _safe_path(root, check["path"])
    kind = check["type"]
    if kind == "path_exists":
        ok = target.exists()
        return CheckResult(check_id, "pass" if ok else "fail", f"path {'exists' if ok else 'missing'}: {check['path']}")
    if kind == "path_absent":
        ok = not target.exists()
        return CheckResult(check_id, "pass" if ok else "fail", f"path {'absent' if ok else 'present'}: {check['path']}")
    if not target.is_file():
        return CheckResult(check_id, "fail", f"file missing: {check['path']}")
    text = target.read_text(encoding="utf-8")
    matched = re.search(check["pattern"], text, flags=re.MULTILINE) is not None
    if kind == "file_contains_regex":
        return CheckResult(check_id, "pass" if matched else "fail", f"required pattern {'found' if matched else 'not found'} in {check['path']}")
    ok = not matched
    return CheckResult(check_id, "pass" if ok else "fail", f"forbidden pattern {'absent' if ok else 'found'} in {check['path']}")


def _active_waiver(config: dict[str, Any], check_id: str, today: dt.date) -> dict[str, Any] | None:
    for waiver in config.get("waivers", []):
        if waiver["check_id"] == check_id and dt.date.fromisoformat(waiver["expires"]) >= today:
            return waiver
    return None


def evaluate(root: Path, contract: Path, today: dt.date | None = None) -> GateResult:
    root = root.resolve()
    config = _load(contract)
    today = today or dt.date.today()
    results: list[CheckResult] = []
    for check in config["checks"]:
        result = _evaluate_check(root, check)
        if result.status == "fail":
            waiver = _active_waiver(config, result.id, today)
            if waiver is not None:
                result = CheckResult(
                    result.id,
                    "waived",
                    f"{result.reason}; waiver owner={waiver['owner']} expires={waiver['expires']}: {waiver['reason']}",
                )
        results.append(result)
    status = "fail" if any(item.status == "fail" for item in results) else "pass"
    return GateResult(status, results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--contract", default=".agent-harness/application-architecture.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    contract = Path(args.contract)
    if not contract.is_absolute():
        contract = root / contract
    try:
        result = evaluate(root, contract)
    except Exception as exc:
        if args.json:
            json.dump({"status": "fail", "error": str(exc)}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"FAIL architecture gate configuration: {exc}")
        return 2
    if args.json:
        json.dump(result.as_dict(), sys.stdout)
        sys.stdout.write("\n")
    else:
        for item in result.checks:
            print(f"{item.status.upper():7} {item.id}: {item.reason}")
        print(f"ARCHITECTURE GATE: {result.status.upper()}")
    return 0 if result.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
