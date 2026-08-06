from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class StreamProtocolError(ValueError):
    pass


@dataclass
class StreamObservation:
    session_ids: set[str] = field(default_factory=set)
    open_tools: dict[str, float] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    event_count: int = 0

    def observe_line(self, line: bytes, now: float) -> list[dict[str, object]]:
        try:
            event = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StreamProtocolError(f"invalid stream-json line: {exc}") from exc
        if not isinstance(event, dict):
            raise StreamProtocolError("stream-json event must be an object")
        self.event_count += 1
        session_id = event.get("session_id")
        if isinstance(session_id, str):
            self.session_ids.add(session_id)
        observations: list[dict[str, object]] = []
        for block in _content_blocks(event):
            if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                tool_id = block["id"]
                self.open_tools[tool_id] = now
                observations.append({"kind": "tool_started", "tool_use_id": tool_id})
            elif block.get("type") == "tool_result" and isinstance(block.get("tool_use_id"), str):
                tool_id = block["tool_use_id"]
                self.open_tools.pop(tool_id, None)
                observations.append({"kind": "tool_finished", "tool_use_id": tool_id})
        if event.get("type") == "result":
            structured = event.get("structured_output")
            if isinstance(structured, dict):
                self.result = structured
            else:
                raw_result = event.get("result")
                if isinstance(raw_result, dict):
                    self.result = raw_result
                elif isinstance(raw_result, str):
                    try:
                        parsed = json.loads(raw_result)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        self.result = parsed
        return observations


def _content_blocks(value: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list):
            blocks.extend(item for item in content if isinstance(item, dict))
        for key in ("message",):
            blocks.extend(_content_blocks(value.get(key)))
    return blocks

