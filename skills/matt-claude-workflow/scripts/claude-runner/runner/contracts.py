from __future__ import annotations

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
    TIMEOUT_SUSPECTED = "timeout_suspected"
    INTERRUPTED = "interrupted"
    BACKEND_FAILURE = "backend_failure"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    CLEANED = "cleaned"


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
        WorkUnitStatus.TIMEOUT_SUSPECTED,
        WorkUnitStatus.INTERRUPTED,
        WorkUnitStatus.BACKEND_FAILURE,
        WorkUnitStatus.IMPLEMENTATION_COMPLETE,
    },
    WorkUnitStatus.PERMISSION_REQUIRED: {WorkUnitStatus.RUNNING, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.TIMEOUT_SUSPECTED: {
        WorkUnitStatus.RUNNING,
        WorkUnitStatus.INTERRUPTED,
        WorkUnitStatus.BACKEND_FAILURE,
    },
    WorkUnitStatus.INTERRUPTED: {WorkUnitStatus.RUNNING, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.BACKEND_FAILURE: {WorkUnitStatus.RUNNING},
    WorkUnitStatus.IMPLEMENTATION_COMPLETE: {WorkUnitStatus.RUNNING, WorkUnitStatus.CLEANED},
    WorkUnitStatus.CLEANED: set(),
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


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        data = dict(value)
        unknown = set(data) - TOP_LEVEL_FIELDS
        missing = TOP_LEVEL_FIELDS - set(data)
        if unknown:
            raise ContractError(f"unowned adapter-state fields: {sorted(unknown)}")
        if missing:
            raise ContractError(f"missing adapter-state fields: {sorted(missing)}")
        if data["schema_version"] != 1:
            raise ContractError("unsupported schema_version")
        if data["workflow"] not in {"superpowers", "matt"}:
            raise ContractError("workflow must be superpowers or matt")
        executor = data["executor"]
        if executor.get("agent") != "claude-code" or executor.get("capability") not in {"sonnet", "opus"}:
            raise ContractError("executor must use claude-code with sonnet or opus capability")
        WorkUnitStatus(data["status"])
        if not isinstance(data["segments"], list) or not data["segments"]:
            raise ContractError("at least one segment is required")
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
