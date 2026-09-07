from __future__ import annotations

from reference.harness import claude, codex, devin
from reference.hooks.policy_engine import Decision


def _capture(module, monkeypatch, raw: dict, *, decision: Decision | None = None, completion=None):
    captured: dict = {}
    monkeypatch.setattr(module, "read_stdin", lambda: raw)
    monkeypatch.setattr(module, "emit", lambda value: captured.setdefault("value", value) or 0)
    if decision is not None:
        monkeypatch.setattr(module, "evaluate_pre_tool_use", lambda payload: decision)
    if completion is not None:
        monkeypatch.setattr(module, "completion", lambda payload: completion)
    return captured


def _pretool(command: str = "git status") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": "/workspace",
        "session_id": "s6-test",
    }


def test_claude_preserves_native_ask(monkeypatch) -> None:
    captured = _capture(
        claude,
        monkeypatch,
        _pretool("terraform plan"),
        decision=Decision("ask", "approval", "cloud"),
    )
    claude.main()
    assert captured["value"]["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_codex_maps_ask_to_deny(monkeypatch) -> None:
    captured = _capture(
        codex,
        monkeypatch,
        _pretool("terraform plan"),
        decision=Decision("ask", "approval", "cloud"),
    )
    codex.main()
    output = captured["value"]["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "approval required" in output["permissionDecisionReason"]


def test_devin_maps_deny_to_block(monkeypatch) -> None:
    captured = _capture(
        devin,
        monkeypatch,
        _pretool("git push --force origin x"),
        decision=Decision("deny", "force push", "force"),
    )
    devin.main()
    assert captured["value"]["decision"] == "block"


def test_all_adapters_use_shared_session_start_context(monkeypatch) -> None:
    for module in (claude, codex, devin):
        raw = {"hook_event_name": "SessionStart", "cwd": "/workspace"}
        captured = _capture(module, monkeypatch, raw)
        monkeypatch.setattr(module, "session_start_context", lambda payload: "shared-context")
        module.main()
        assert (
            captured["value"]["hookSpecificOutput"]["additionalContext"]
            == "shared-context"
        )


def test_all_adapters_block_failed_completion(monkeypatch) -> None:
    for module in (claude, codex, devin):
        raw = {"hook_event_name": "Stop", "cwd": "/workspace"}
        captured = _capture(module, monkeypatch, raw, completion=(False, "gate failed"))
        module.main()
        assert captured["value"] == {"decision": "block", "reason": "gate failed"}


def test_all_adapters_allow_successful_completion(monkeypatch) -> None:
    for module in (claude, codex, devin):
        raw = {"hook_event_name": "Stop", "cwd": "/workspace"}
        captured = _capture(module, monkeypatch, raw, completion=(True, "ok"))
        module.main()
        assert captured["value"] == {}
