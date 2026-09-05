from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def test_rejects_unknown_request_kind():
    result = server.handle({"kind": "exec", "args": ["sh"]})
    assert result["ok"] is False


def test_rejects_arbitrary_gh_api():
    result = server.handle({"kind": "gh", "args": ["api", "user"], "cwd": str(server.WORKSPACE_ROOT)})
    assert result["ok"] is False
    assert "unsupported gh" in result["error"]


def test_rejects_git_credential_operation():
    result = server.handle({"kind": "git", "args": ["credential", "fill"], "cwd": str(server.WORKSPACE_ROOT)})
    assert result["ok"] is False
    assert "unsupported git" in result["error"]


def test_workspace_escape_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "TOKEN", "not-a-real-token")
    result = server.handle({"kind": "gh", "args": ["pr", "view"], "cwd": "/etc"})
    assert result["ok"] is False
    assert "outside" in result["error"]
