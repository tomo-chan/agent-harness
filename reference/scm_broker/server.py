#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SOCKET_PATH = Path(os.environ.get("SCM_BROKER_SOCKET", "/run/agent-harness/scm.sock"))
WORKSPACE_ROOT = Path(os.environ.get("SCM_BROKER_WORKSPACE_ROOT", "/workspace")).resolve()
REPOSITORY = os.environ.get("SCM_BROKER_REPOSITORY", "")
TOKEN = os.environ.get("SCM_BROKER_GH_TOKEN", "")
REAL_GIT = os.environ.get("SCM_BROKER_GIT", "/usr/bin/git")
REAL_GH = os.environ.get("SCM_BROKER_GH", "/usr/bin/gh")

ALLOWED_GIT_REMOTE_OPS = {"push", "fetch", "pull", "clone"}
ALLOWED_GH_OPS = {
    ("pr", "create"),
    ("pr", "view"),
    ("pr", "status"),
    ("pr", "checks"),
}


def _workspace(value: str) -> Path:
    path = Path(value).resolve()
    if path != WORKSPACE_ROOT and WORKSPACE_ROOT not in path.parents:
        raise ValueError("workspace is outside the broker workspace root")
    return path


def _remote_url() -> str:
    if not REPOSITORY or "/" not in REPOSITORY:
        raise ValueError("SCM_BROKER_REPOSITORY must be owner/name")
    return f"https://github.com/{REPOSITORY}.git"


def _base_env() -> dict[str, str]:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C.UTF-8",
    }
    return env


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=300)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _git(payload: dict[str, Any]) -> dict[str, Any]:
    args = [str(x) for x in payload.get("args", [])]
    if not args or args[0] not in ALLOWED_GIT_REMOTE_OPS:
        return {"ok": False, "error": "unsupported git remote operation"}
    cwd = _workspace(str(payload.get("cwd", WORKSPACE_ROOT)))
    if not TOKEN:
        return {"ok": False, "error": "broker credential unavailable"}

    with tempfile.TemporaryDirectory(prefix="agent-harness-git-") as td:
        askpass = Path(td) / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' 'x-access-token' ;; *) printf '%s\\n' \"$SCM_BROKER_GH_TOKEN\" ;; esac\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
        env = _base_env()
        env.update({"GIT_ASKPASS": str(askpass), "SCM_BROKER_GH_TOKEN": TOKEN})

        op = args[0]
        rest = args[1:]
        if op in {"push", "fetch", "pull"}:
            # Never trust the repository's remote URL; substitute the broker-owned URL.
            if rest and not rest[0].startswith("-"):
                rest = rest[1:]
            argv = [
                REAL_GIT,
                "-c", "core.hooksPath=/dev/null",
                "-c", "credential.helper=",
                op,
                _remote_url(),
                *rest,
            ]
            return _run(argv, cwd, env)
        if op == "clone":
            target = rest[-1] if rest else "."
            argv = [REAL_GIT, "-c", "core.hooksPath=/dev/null", "clone", _remote_url(), target]
            return _run(argv, cwd, env)
    return {"ok": False, "error": "unreachable"}


def _gh(payload: dict[str, Any]) -> dict[str, Any]:
    args = [str(x) for x in payload.get("args", [])]
    if len(args) < 2 or tuple(args[:2]) not in ALLOWED_GH_OPS:
        return {"ok": False, "error": "unsupported gh operation"}
    cwd = _workspace(str(payload.get("cwd", WORKSPACE_ROOT)))
    if not TOKEN:
        return {"ok": False, "error": "broker credential unavailable"}
    env = _base_env()
    env.update({"GH_TOKEN": TOKEN, "GH_REPO": REPOSITORY, "GH_PROMPT_DISABLED": "1"})
    return _run([REAL_GH, *args], cwd, env)


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        kind = payload.get("kind")
        if kind == "git":
            return _git(payload)
        if kind == "gh":
            return _gh(payload)
        return {"ok": False, "error": "unsupported request kind"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def serve() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o660)
        server.listen(32)
        while True:
            conn, _ = server.accept()
            with conn:
                raw = b""
                while not raw.endswith(b"\n"):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                result = handle(json.loads(raw.decode()))
                conn.sendall((json.dumps(result) + "\n").encode())


if __name__ == "__main__":
    serve()
