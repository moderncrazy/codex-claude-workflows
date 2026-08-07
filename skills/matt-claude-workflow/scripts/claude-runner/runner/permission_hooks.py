from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, TextIO

from .contracts import InvalidTransition, utc_now
from .state_store import StateStore


PERMISSION_REQUEST_RESPONSE = {
    "decision": {
        "behavior": "deny",
        "message": "Permission captured for the Codex Permission Broker",
        "interrupt": True,
    },
    "suppressOutput": True,
}

PERMISSION_DENIED_RESPONSE = {
    "continue": False,
    "stopReason": "Claude Code permission was denied; execution is stopped for Codex review",
    "suppressOutput": True,
}


def _command(arguments: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(arguments)
    return shlex.join(arguments)


def build_hook_settings(state_dir: Path, python: Path, entrypoint: Path) -> dict[str, object]:
    base = [str(python), str(entrypoint), "hook"]

    def hook(event: str) -> list[dict[str, object]]:
        command = _command(base + [event, "--state-dir", str(state_dir.resolve())])
        return [{"hooks": [{"type": "command", "command": command}]}]

    return {"hooks": {"PermissionRequest": hook("permission-request"), "PermissionDenied": hook("permission-denied")}}


def _read_request(source: TextIO) -> dict[str, Any]:
    content = source.read()
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("hook input must be one JSON object")
    return parsed


def _write(sink: TextIO, payload: dict[str, object]) -> None:
    sink.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sink.flush()


def _fail_closed(sink: TextIO, reason: str) -> int:
    _write(
        sink,
        {
            "continue": False,
            "stopReason": f"Claude Code permission hook failed closed: {reason}",
            "suppressOutput": True,
        },
    )
    return 2


def handle_permission_request(state_dir: Path, source: TextIO | None = None, sink: TextIO | None = None) -> int:
    input_stream = source or sys.stdin
    output_stream = sink or sys.stdout
    try:
        request = _read_request(input_stream)
        if request.get("hook_event_name") != "PermissionRequest":
            raise ValueError("unexpected hook_event_name")
        store = StateStore(state_dir)

        def record(state: Any) -> None:
            pending = state.permissions["pending"]
            if pending is not None:
                raise InvalidTransition("a permission request is already pending")
            candidates = [segment for segment in state.segments if segment["status"] == "running"]
            if len(candidates) != 1:
                raise InvalidTransition("permission request does not identify one running Segment")
            state.permissions["pending"] = {
                "segment_id": candidates[0]["segment_id"],
                "request": request,
                "tool_name": request.get("tool_name"),
                "tool_input": request.get("tool_input"),
                "received_at": utc_now(),
            }

        store.update(record)
        _write(output_stream, PERMISSION_REQUEST_RESPONSE)
        return 0
    except Exception as exc:
        return _fail_closed(output_stream, str(exc))

def handle_permission_denied(state_dir: Path, source: TextIO | None = None, sink: TextIO | None = None) -> int:
    input_stream = source or sys.stdin
    output_stream = sink or sys.stdout
    try:
        request = _read_request(input_stream)
        if request.get("hook_event_name") != "PermissionDenied":
            raise ValueError("unexpected hook_event_name")
        store = StateStore(state_dir)

        def record(state: Any) -> None:
            state.runtime["last_permission_denied"] = {"request": request, "received_at": utc_now()}

        store.update(record)
        _write(output_stream, PERMISSION_DENIED_RESPONSE)
        return 0
    except Exception as exc:
        return _fail_closed(output_stream, str(exc))
