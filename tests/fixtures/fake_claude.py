#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time


def option(name: str) -> str | None:
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except (ValueError, IndexError):
        return None


def emit(payload: object) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    return data


def main() -> int:
    scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "success")
    if scenario == "ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    session_id = option("--session-id") or option("--resume") or "missing"
    if scenario == "wrong-session":
        session_id = "00000000-0000-4000-8000-000000000000"
    if scenario == "missing-executable":
        return 127

    emit({"type": "system", "subtype": "init", "session_id": session_id})
    if scenario == "invalid-json":
        sys.stdout.buffer.write(b"this is not json\n")
        sys.stdout.buffer.flush()
        return 0
    if scenario == "stderr-bytes":
        sys.stderr.buffer.write(b"stderr:\xe4\xb8\xad:\xff\n")
        sys.stderr.buffer.flush()
    if scenario == "unknown-tool":
        emit(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "toolu_secret", "name": "mcp__future__opaque", "input": {"secret": "do-not-surface"}}
                    ]
                },
            }
        )
        emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_secret", "content": "opaque"}]}})
    elif scenario == "model-idle":
        time.sleep(float(os.environ.get("FAKE_CLAUDE_DELAY", "0.15")))
    elif scenario == "tool-idle":
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_wait", "name": "Bash", "input": {}}]}})
        time.sleep(float(os.environ.get("FAKE_CLAUDE_DELAY", "0.15")))
        emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_wait", "content": "done"}]}})
    elif scenario == "permission":
        settings = json.loads(option("--settings") or "{}")
        command = settings["hooks"]["PermissionRequest"][0]["hooks"][0]["command"]
        request = {
            "session_id": session_id,
            "cwd": os.getcwd(),
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest --version"},
        }
        subprocess.run(shlex.split(command), input=json.dumps(request).encode(), stdout=subprocess.PIPE, check=False)
        return 3
    elif scenario == "ignore-term":
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_term_ready", "name": "Bash", "input": {}}]}})
        time.sleep(float(os.environ.get("FAKE_CLAUDE_DELAY", "5")))

    status = {
        "needs-context": "NEEDS_CONTEXT",
        "blocked": "BLOCKED",
        "structured-permission": "PERMISSION_REQUIRED",
    }.get(scenario, "DONE" if scenario != "invalid-result" else "INVENTED")
    emit(
        {
            "type": "result",
            "session_id": session_id,
            "structured_output": {
                "status": status,
                "summary": "fixture complete",
                "session_id": session_id,
                "commits": [],
                "tests": [{"command": "fixture-test", "status": "passed", "summary": "passed"}],
                "concerns": [],
                "context_requests": ["missing fixture detail"] if scenario == "needs-context" else [],
                "permission_requests": (
                    [{"tool": "Bash", "scope": "pytest --version", "reason": "inspect test tool"}]
                    if scenario == "structured-permission"
                    else []
                ),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
