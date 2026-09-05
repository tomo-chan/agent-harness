import datetime as dt
import json
from pathlib import Path

from reference.application_gate.gate import GateConfigError, evaluate


def _write_contract(path: Path, checks, waivers=None):
    path.write_text(json.dumps({"version": 1, "name": "test", "checks": checks, "waivers": waivers or []}), encoding="utf-8")


def test_path_checks_pass(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    contract = tmp_path / "contract.json"
    _write_contract(contract, [
        {"id": "required", "type": "path_exists", "path": "docs/architecture.md"},
        {"id": "forbidden", "type": "path_absent", "path": "scm_broker"},
    ])
    result = evaluate(tmp_path, contract)
    assert result.status == "pass"


def test_regex_checks_are_deterministic(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("from domain import Service\n", encoding="utf-8")
    contract = tmp_path / "contract.json"
    _write_contract(contract, [
        {"id": "required-import", "type": "file_contains_regex", "path": "app.py", "pattern": "^from domain import"},
        {"id": "no-os-system", "type": "file_not_contains_regex", "path": "app.py", "pattern": "os\\.system"},
    ])
    assert evaluate(tmp_path, contract).status == "pass"


def test_failure_is_gate_failure(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    _write_contract(contract, [{"id": "required", "type": "path_exists", "path": "missing.txt"}])
    result = evaluate(tmp_path, contract)
    assert result.status == "fail"
    assert result.checks[0].status == "fail"


def test_active_waiver_is_explicit_and_expiring(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    _write_contract(
        contract,
        [{"id": "required", "type": "path_exists", "path": "missing.txt"}],
        [{"check_id": "required", "reason": "migration", "owner": "platform", "expires": "2026-09-30"}],
    )
    result = evaluate(tmp_path, contract, today=dt.date(2026, 9, 5))
    assert result.status == "pass"
    assert result.checks[0].status == "waived"


def test_expired_waiver_does_not_bypass_gate(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    _write_contract(
        contract,
        [{"id": "required", "type": "path_exists", "path": "missing.txt"}],
        [{"check_id": "required", "reason": "migration", "owner": "platform", "expires": "2026-09-01"}],
    )
    assert evaluate(tmp_path, contract, today=dt.date(2026, 9, 5)).status == "fail"


def test_path_escape_is_rejected(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    _write_contract(contract, [{"id": "escape", "type": "path_exists", "path": "../outside"}])
    try:
        evaluate(tmp_path, contract)
    except GateConfigError:
        return
    raise AssertionError("path escape must be rejected")


def test_unknown_check_type_fails_configuration(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    _write_contract(contract, [{"id": "x", "type": "llm_review", "path": "README.md"}])
    try:
        evaluate(tmp_path, contract)
    except GateConfigError:
        return
    raise AssertionError("non-deterministic check type must not be accepted")
