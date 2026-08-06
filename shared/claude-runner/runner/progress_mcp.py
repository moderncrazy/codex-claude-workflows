from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from . import PROGRESS_TOOL_NAME, __version__
from .state_store import StateStore


CLAIM_KINDS = {
    "segment_started",
    "before_long_operation",
    "verification_claim",
    "segment_completed",
    "blocked",
    "permission_claim",
    "completion_claim",
}

CLAIM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "message", "next_action", "evidence_refs"],
    "properties": {
        "kind": {"enum": sorted(CLAIM_KINDS)},
        "message": {"type": "string", "minLength": 1},
        "next_action": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_claim(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("arguments must be an object")
    required = {"kind", "message", "next_action", "evidence_refs"}
    if set(value) != required:
        raise ValueError("claim must contain exactly kind, message, next_action, and evidence_refs")
    if value["kind"] not in CLAIM_KINDS:
        raise ValueError("invalid claim kind")
    if not isinstance(value["message"], str) or not value["message"]:
        raise ValueError("message must be a non-empty string")
    if not isinstance(value["next_action"], str):
        raise ValueError("next_action must be a string")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("evidence_refs must be an array of strings")
    return value


def _response(request_id: object, *, result: object | None = None, error: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result if result is not None else {}
    return payload


def _handle(store: StateStore, request: dict[str, Any]) -> dict[str, object] | None:
    if "id" not in request:
        return None
    request_id = request["id"]
    method = request.get("method")
    if method == "initialize":
        protocol = request.get("params", {}).get("protocolVersion", "2024-11-05")
        return _response(
            request_id,
            result={
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "codex-claude-runner", "version": __version__},
            },
        )
    if method == "ping":
        return _response(request_id, result={})
    if method == "tools/list":
        return _response(
            request_id,
            result={
                "tools": [
                    {
                        "name": PROGRESS_TOOL_NAME,
                        "description": "Record an unverified Claude progress claim verbatim for Codex.",
                        "inputSchema": CLAIM_SCHEMA,
                    }
                ]
            },
        )
    if method == "tools/call":
        params = request.get("params", {})
        if params.get("name") != PROGRESS_TOOL_NAME:
            return _response(request_id, error={"code": -32602, "message": "unknown tool"})
        try:
            claim = validate_claim(params.get("arguments"))
        except ValueError as exc:
            return _response(request_id, error={"code": -32602, "message": str(exc)})
        raw_path = store.state_dir / store.RAW_FILES["stdout"]
        offset = raw_path.stat().st_size if raw_path.exists() else None
        receipt = store.record_progress_claim(claim, raw_event_offset=offset)
        return _response(
            request_id,
            result={
                "content": [{"type": "text", "text": f"Progress claim recorded as receipt {receipt.sequence}"}],
                "isError": False,
            },
        )
    return _response(request_id, error={"code": -32601, "message": f"method not found: {method}"})


def serve_progress_mcp(
    state_dir: Path,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout
    diagnostics = error_stream or sys.stderr
    store = StateStore(state_dir)
    for line in source:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request is not an object")
        except (json.JSONDecodeError, ValueError) as exc:
            diagnostics.write(f"invalid JSON-RPC input: {exc}\n")
            diagnostics.flush()
            continue
        response = _handle(store, request)
        if response is not None:
            sink.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sink.flush()
    return 0
