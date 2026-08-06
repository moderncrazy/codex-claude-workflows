from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from .contracts import InvalidTransition, ProgressReceipt, WorkUnitState, utc_now


class StateStore:
    STATE_NAME = "work-unit.json"
    RAW_FILES = {"stdout": "raw-events.jsonl", "stderr": "raw-stderr.log"}

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.resolve()
        self.state_path = self.state_dir / self.STATE_NAME
        self.lock_path = self.state_dir / ".work-unit.lock"

    @classmethod
    def create(cls, state: WorkUnitState) -> "StateStore":
        working_root = Path(state.working_root).resolve()
        state_dir = working_root / ".tmp" / "codex-claude-workflows" / state.work_unit_id
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        store = cls(state_dir)
        store._write_atomic(state)
        for filename in cls.RAW_FILES.values():
            path = state_dir / filename
            path.touch(mode=0o600, exist_ok=False)
            path.chmod(0o600)
        return store

    @contextmanager
    def _exclusive_lock(self, timeout: float = 10.0) -> Iterator[None]:
        deadline = time.monotonic() + timeout
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(descriptor, f"{os.getpid()}\n".encode())
                os.fsync(descriptor)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out acquiring {self.lock_path}")
                time.sleep(0.01)
        try:
            yield
        finally:
            os.close(descriptor)
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    def _write_atomic(self, state: WorkUnitState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix=".work-unit.", suffix=".tmp", dir=self.state_dir)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.state_path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def load(self) -> WorkUnitState:
        with self.state_path.open(encoding="utf-8") as handle:
            return WorkUnitState.from_dict(json.load(handle))

    def update(self, mutation: Callable[[WorkUnitState], None]) -> WorkUnitState:
        with self._exclusive_lock():
            state = self.load()
            mutation(state)
            validated = WorkUnitState.from_dict(state.to_dict())
            self._write_atomic(validated)
            return validated

    def update_fields(self, fields: Mapping[str, object]) -> WorkUnitState:
        unknown = set(fields) - set(self.load().to_dict())
        if unknown:
            raise InvalidTransition(f"cannot write unowned fields: {sorted(unknown)}")

        def mutate(state: WorkUnitState) -> None:
            if "status" in fields:
                state.transition_to(str(fields["status"]))
            for key, value in fields.items():
                if key != "status":
                    state.data[key] = value

        return self.update(mutate)

    def append_raw(self, target: Literal["stdout", "stderr"], data: bytes) -> int:
        if target not in self.RAW_FILES:
            raise ValueError(f"unknown raw target: {target}")
        with self._exclusive_lock():
            path = self.state_dir / self.RAW_FILES[target]
            with path.open("ab", buffering=0) as handle:
                offset = handle.tell()
                handle.write(data)
                os.fsync(handle.fileno())
                return offset

    def record_progress_claim(self, claim: dict[str, object], raw_event_offset: int | None) -> ProgressReceipt:
        saved: ProgressReceipt | None = None

        def mutate(state: WorkUnitState) -> None:
            nonlocal saved
            saved = ProgressReceipt(
                work_unit_id=state.work_unit_id,
                sequence=len(state.progress_claims) + 1,
                received_at=utc_now(),
                raw_event_offset=raw_event_offset,
                claim=dict(claim),
            )
            state.progress_claims.append(saved.to_dict())

        self.update(mutate)
        assert saved is not None
        return saved
