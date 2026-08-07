from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ContractError(ValueError):
    """Raised when persisted adapter state violates its owned contract."""


class InvalidTransition(ContractError):
    """Raised when a state transition or field mutation is not allowed."""


class WorkUnitStatus(str, Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    PERMISSION_REQUIRED = "permission_required"
    INTERRUPTED = "interrupted"
    BACKEND_FAILURE = "backend_failure"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    FINISHED = "finished"


class SegmentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PERMISSION_REQUIRED = "permission_required"
    INTERRUPTED = "interrupted"
    COMPLETE = "complete"
    FAILED = "failed"


ALLOWED_TRANSITIONS = {
    WorkUnitStatus.INITIALIZED: {WorkUnitStatus.RUNNING, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.RUNNING: {
        WorkUnitStatus.PERMISSION_REQUIRED,
        WorkUnitStatus.INTERRUPTED,
        WorkUnitStatus.BACKEND_FAILURE,
        WorkUnitStatus.IMPLEMENTATION_COMPLETE,
    },
    WorkUnitStatus.PERMISSION_REQUIRED: {
        WorkUnitStatus.INTERRUPTED,
        WorkUnitStatus.BACKEND_FAILURE,
    },
    WorkUnitStatus.INTERRUPTED: {WorkUnitStatus.RUNNING, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.BACKEND_FAILURE: {WorkUnitStatus.RUNNING},
    WorkUnitStatus.IMPLEMENTATION_COMPLETE: {WorkUnitStatus.RUNNING, WorkUnitStatus.FINISHED},
    WorkUnitStatus.FINISHED: set(),
}

TOP_LEVEL_FIELDS = {
    "schema_version",
    "work_unit_id",
    "workflow",
    "native_ref",
    "working_root",
    "fixed_point",
    "executor",
    "status",
    "segments",
    "permissions",
    "runtime",
    "progress_claims",
    "evidence",
    "commits",
    "result",
}

SEGMENT_FIELDS = {
    "segment_id", "kind", "scope", "verification_commands", "status", "session_id",
    "attempt", "resume_count", "created_at", "started_at", "finished_at", "finding_ids", "capability",
}
SEGMENT_REQUIRED = SEGMENT_FIELDS - {"finding_ids", "capability"}


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def upgrade_state_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("adapter state must be an object")
    data = copy.deepcopy(dict(value))
    version = data.get("schema_version")
    if version == 2:
        return data
    if version != 1:
        raise ContractError("unsupported schema_version")
    try:
        permissions = data["permissions"]
        segments = data["segments"]
        runtime = data["runtime"]
        if not isinstance(permissions, dict) or not isinstance(segments, list) or not isinstance(runtime, dict):
            raise ContractError("legacy adapter state has invalid nested fields")
        data["schema_version"] = 2
        permissions["resolved"] = []
        for segment in segments:
            if not isinstance(segment, dict):
                raise ContractError("legacy Segment must be an object")
            segment["resume_count"] = 0
            if segment.get("session_id") is not None and segment.get("attempt") == 0:
                segment["attempt"] = 1
        if data.get("status") == "timeout_suspected":
            data["status"] = "running"
        elif data.get("status") == "cleaned":
            data["status"] = "finished"
        pending = permissions.get("pending")
        if pending is not None and "segment_id" not in pending:
            candidates = [
                segment["segment_id"]
                for segment in segments
                if segment.get("status") == "permission_required"
            ]
            if len(candidates) != 1:
                raise ContractError("legacy pending permission does not identify one Segment")
            pending["segment_id"] = candidates[0]
        runtime.setdefault("result_history", [])
    except KeyError as exc:
        raise ContractError(f"legacy adapter state is missing {exc.args[0]}") from exc
    return data


@dataclass
class ProgressReceipt:
    work_unit_id: str
    sequence: int
    received_at: str
    raw_event_offset: int | None
    claim: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "work_unit_id": self.work_unit_id,
            "sequence": self.sequence,
            "received_at": self.received_at,
            "raw_event_offset": self.raw_event_offset,
            "claim": self.claim,
        }


@dataclass
class WorkUnitState:
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkUnitState":
        if not isinstance(value, Mapping):
            raise ContractError("adapter state must be an object")
        data = copy.deepcopy(dict(value))
        unknown = set(data) - TOP_LEVEL_FIELDS
        missing = TOP_LEVEL_FIELDS - set(data)
        if unknown:
            raise ContractError(f"unowned adapter-state fields: {sorted(unknown)}")
        if missing:
            raise ContractError(f"missing adapter-state fields: {sorted(missing)}")
        if data["schema_version"] != 2:
            raise ContractError("unsupported schema_version")
        if data["workflow"] not in {"superpowers", "matt"}:
            raise ContractError("workflow must be superpowers or matt")
        executor = data["executor"]
        if not isinstance(executor, dict) or set(executor) != {"agent", "capability"}:
            raise ContractError("executor must contain exactly agent and capability")
        if executor.get("agent") != "claude-code" or executor.get("capability") not in {"sonnet", "opus"}:
            raise ContractError("executor must use claude-code with sonnet or opus capability")
        try:
            WorkUnitStatus(data["status"])
        except ValueError as exc:
            raise ContractError("invalid Work Unit status") from exc
        if not isinstance(data["segments"], list) or not data["segments"]:
            raise ContractError("at least one segment is required")
        identifiers: set[str] = set()
        for segment in data["segments"]:
            _validate_segment(segment)
            if segment["segment_id"] in identifiers:
                raise ContractError("segment_id values must be unique")
            identifiers.add(segment["segment_id"])
        permissions = data["permissions"]
        if not isinstance(permissions, dict) or set(permissions) != {"initial", "approved", "pending", "resolved"}:
            raise ContractError("permissions must contain exactly initial, approved, pending, and resolved")
        if not isinstance(permissions["initial"], list) or not isinstance(permissions["approved"], list):
            raise ContractError("permission allowlists must be arrays")
        if not isinstance(permissions["resolved"], list):
            raise ContractError("resolved permissions must be an array")
        if permissions["pending"] is not None and not isinstance(permissions["pending"], dict):
            raise ContractError("pending permission must be an object or null")
        if permissions["pending"] is not None:
            segment_id = permissions["pending"].get("segment_id")
            if not isinstance(segment_id, str) or segment_id not in identifiers:
                raise ContractError("pending permission must identify an existing Segment")
        if not isinstance(data["runtime"], dict):
            raise ContractError("runtime must be an object")
        if not isinstance(data["progress_claims"], list) or not isinstance(data["commits"], list):
            raise ContractError("progress_claims and commits must be arrays")
        evidence = data["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != {"declared", "verified"}:
            raise ContractError("evidence must contain exactly declared and verified")
        if not isinstance(evidence["declared"], list) or not isinstance(evidence["verified"], list):
            raise ContractError("evidence fields must be arrays")
        if data["result"] is not None and not isinstance(data["result"], dict):
            raise ContractError("result must be an object or null")
        try:
            uuid.UUID(str(data["work_unit_id"]))
        except ValueError as exc:
            raise ContractError("work_unit_id must be a UUID") from exc
        return cls(data)

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def __getattr__(self, name: str) -> Any:
        try:
            return self.data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def transition_to(self, status: WorkUnitStatus | str) -> None:
        target = WorkUnitStatus(status)
        current = WorkUnitStatus(self.data["status"])
        if target == current:
            return
        if target not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransition(f"cannot transition from {current.value} to {target.value}")
        self.data["status"] = target.value


def _validate_segment(segment: object) -> None:
    if not isinstance(segment, dict):
        raise ContractError("each segment must be an object")
    unknown = set(segment) - SEGMENT_FIELDS
    missing = SEGMENT_REQUIRED - set(segment)
    if unknown or missing:
        raise ContractError(f"invalid segment fields; missing={sorted(missing)}, unknown={sorted(unknown)}")
    if not all(isinstance(segment[field], str) and segment[field] for field in ("segment_id", "kind", "scope", "created_at")):
        raise ContractError("segment identity, kind, scope, and created_at must be non-empty strings")
    if not isinstance(segment["verification_commands"], list) or any(not isinstance(item, str) for item in segment["verification_commands"]):
        raise ContractError("verification_commands must be an array of strings")
    try:
        SegmentStatus(segment["status"])
    except ValueError as exc:
        raise ContractError("invalid Segment status") from exc
    if segment["session_id"] is not None:
        try:
            uuid.UUID(str(segment["session_id"]))
        except ValueError as exc:
            raise ContractError("segment session_id must be a UUID or null") from exc
    for field in ("attempt", "resume_count"):
        if not isinstance(segment[field], int) or isinstance(segment[field], bool) or segment[field] < 0:
            raise ContractError(f"segment {field} must be a non-negative integer")
    for field in ("started_at", "finished_at"):
        if segment[field] is not None and not isinstance(segment[field], str):
            raise ContractError(f"{field} must be a string or null")
    if "finding_ids" in segment and (
        not isinstance(segment["finding_ids"], list) or any(not isinstance(item, str) for item in segment["finding_ids"])
    ):
        raise ContractError("finding_ids must be an array of strings")
    if "capability" in segment and segment["capability"] not in {"sonnet", "opus"}:
        raise ContractError("segment capability must be sonnet or opus")


def validate_json_schema(instance: object, schema: Mapping[str, Any], path: str = "$") -> None:
    """Validate the JSON Schema subset used by the bundled result contract."""
    if "const" in schema and instance != schema["const"]:
        raise ContractError(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ContractError(f"{path} is not one of {schema['enum']!r}")
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(instance, expected_type):
        raise ContractError(f"{path} has the wrong JSON type")
    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in instance]
        if missing:
            raise ContractError(f"{path} is missing required fields {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(instance) - set(properties)
            if unknown:
                raise ContractError(f"{path} contains unknown fields {sorted(unknown)}")
        for key, child_schema in properties.items():
            if key in instance:
                validate_json_schema(instance[key], child_schema, f"{path}.{key}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise ContractError(f"{path} has too few items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ContractError(f"{path} has too many items")
        if "items" in schema:
            for index, item in enumerate(instance):
                validate_json_schema(item, schema["items"], f"{path}[{index}]")
        if "contains" in schema and not any(_schema_matches(item, schema["contains"]) for item in instance):
            raise ContractError(f"{path} does not contain a matching item")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise ContractError(f"{path} is too short")
        if schema.get("format") == "uuid":
            try:
                uuid.UUID(instance)
            except ValueError as exc:
                raise ContractError(f"{path} must be a UUID") from exc
    for subschema in schema.get("allOf", []):
        validate_json_schema(instance, subschema, path)
    if "if" in schema and _schema_matches(instance, schema["if"]):
        validate_json_schema(instance, schema.get("then", {}), path)
    if "not" in schema and _schema_matches(instance, schema["not"]):
        raise ContractError(f"{path} matches a forbidden schema")


def _schema_matches(instance: object, schema: Mapping[str, Any]) -> bool:
    try:
        validate_json_schema(instance, schema)
        return True
    except ContractError:
        return False


def _matches_type(instance: object, expected: str | list[str]) -> bool:
    names = [expected] if isinstance(expected, str) else expected
    checks = {
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
        "string": lambda value: isinstance(value, str),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
        "null": lambda value: value is None,
    }
    return any(checks[name](instance) for name in names)
