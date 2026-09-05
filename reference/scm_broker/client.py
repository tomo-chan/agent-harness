#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import sys
from typing import Any


def request(payload: dict[str, Any]) -> dict[str, Any]:
    path = os.environ.get("AGENT_HARNESS_SCM_SOCKET", "/run/agent-harness/scm.sock")
    data = (json.dumps(payload) + "\n").encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(path)
        sock.sendall(data)
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return json.loads(b"".join(chunks).decode())


def main() -> int:
    payload = json.load(sys.stdin)
    result = request(payload)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
