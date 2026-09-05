#!/usr/bin/env python3
"""Launch a trusted SCM helper outside the agent sandbox, then exec the agent.

The GitHub credential is read by this trusted launcher and passed only to the helper.
The agent process is exec'd with a scrubbed environment and must rely on its sandbox
plus the narrow Unix-socket SCM API for authenticated remote operations.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SECRET_ENV_NAMES = ("GH_TOKEN", "GITHUB_TOKEN", "SCM_BROKER_GH_TOKEN")


def _read_token() -> str:
    token_file = Path(os.environ.get("AGENT_HARNESS_GITHUB_TOKEN_FILE", "/run/secrets/scm/token"))
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("GitHub credential file is empty")
    return token


def _scrubbed_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in SECRET_ENV_NAMES:
        env.pop(name, None)
    env["AGENT_HARNESS_SCM_SOCKET"] = os.environ.get(
        "AGENT_HARNESS_SCM_SOCKET", "/run/agent-harness/scm.sock"
    )
    shim_dir = str(Path(__file__).resolve().parents[1] / "shims")
    env["PATH"] = f"{shim_dir}:{env.get('PATH', '/usr/local/bin:/usr/bin:/bin')}"
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("agent", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.agent:
        parser.error("agent command is required after --")

    token = _read_token()
    helper_env = _scrubbed_env()
    helper_env["SCM_BROKER_GH_TOKEN"] = token

    server = Path(__file__).resolve().parents[1] / "scm_broker" / "server.py"
    helper = subprocess.Popen([sys.executable, str(server)], env=helper_env)

    # Remove any accidental credential values from this process before replacing it
    # with the agent runtime. The helper is now the only process with the token.
    for name in SECRET_ENV_NAMES:
        os.environ.pop(name, None)
    token = ""  # best-effort lifetime reduction; Python strings are not secure memory.

    agent_env = _scrubbed_env()
    try:
        os.execvpe(args.agent[0], args.agent, agent_env)
    except Exception:
        helper.terminate()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
