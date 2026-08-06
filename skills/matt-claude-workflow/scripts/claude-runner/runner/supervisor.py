from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Mapping, Sequence

from .contracts import WorkUnitStatus, utc_now
from .state_store import StateStore
from .stream_capture import StreamObservation, StreamProtocolError


@dataclass(frozen=True)
class ClaudeInvocation:
    executable: Path
    working_root: Path
    session_id: str
    resume: bool
    capability: Literal["sonnet", "opus"]
    allowed_tools: Sequence[str]
    reporter_config_json: str
    hook_settings_json: str
    result_schema: Path
    prompt: str

    def argv(self) -> list[str]:
        mode = ["--resume", self.session_id] if self.resume else ["--session-id", self.session_id]
        allowed = [argument for rule in self.allowed_tools for argument in ("--allowedTools", rule)]
        return [
            str(self.executable),
            "-p",
            *mode,
            "--model",
            self.capability,
            "--permission-mode",
            "acceptEdits",
            *allowed,
            "--output-format",
            "stream-json",
            "--mcp-config",
            self.reporter_config_json,
            "--settings",
            self.hook_settings_json,
            "--json-schema",
            self.result_schema.read_text(encoding="utf-8"),
            self.prompt,
        ]


class Supervisor:
    def __init__(
        self,
        store: StateStore,
        invocation: ClaudeInvocation,
        *,
        event_sink: Callable[[dict[str, object]], None] | None = None,
        environment: Mapping[str, str] | None = None,
        model_idle_seconds: float = 600,
        tool_idle_seconds: float = 1800,
        work_unit_seconds: float = 14400,
        heartbeat_seconds: float = 30,
    ):
        self.store = store
        self.invocation = invocation
        self.event_sink = event_sink or (lambda event: None)
        self.environment = dict(environment) if environment is not None else None
        self.model_idle_seconds = model_idle_seconds
        self.tool_idle_seconds = tool_idle_seconds
        self.work_unit_seconds = work_unit_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.process: subprocess.Popen[bytes] | None = None

    def _emit(self, kind: str, **fields: object) -> None:
        self.event_sink({"type": "runner_event", "kind": kind, **fields})

    def _set_running(self, process: subprocess.Popen[bytes]) -> None:
        def mutate(state: object) -> None:
            state.transition_to(WorkUnitStatus.RUNNING)
            state.runtime.update(
                {
                    "pid": process.pid,
                    "process_group_id": process.pid if os.name != "nt" else None,
                    "process_started_at": utc_now(),
                    "last_raw_event_at": None,
                }
            )
            for segment in state.segments:
                if segment["session_id"] == self.invocation.session_id:
                    segment["status"] = "running"
                    segment["attempt"] += 1
                    segment["started_at"] = segment["started_at"] or utc_now()
                    break

        self.store.update(mutate)

    def run(self) -> int:
        try:
            process = subprocess.Popen(
                self.invocation.argv(),
                cwd=self.invocation.working_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.environment,
                start_new_session=True,
            )
        except OSError as exc:
            self._backend_failure(f"failed to start Claude: {exc}")
            return 1
        self.process = process
        self._set_running(process)
        started = last_event = time.monotonic()
        next_heartbeat = started + self.heartbeat_seconds
        observation = StreamObservation()
        stdout_buffer = b""
        protocol_error: str | None = None
        timeout_keys: set[str] = set()
        selector = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")

        while selector.get_map():
            ready = selector.select(timeout=0.02)
            now = time.monotonic()
            if now >= next_heartbeat:
                self._heartbeat(started, now)
                next_heartbeat = now + self.heartbeat_seconds
            if not ready:
                self._observe_timeouts(started, last_event, observation, now, timeout_keys)
                if process.poll() is not None:
                    for key in list(selector.get_map().values()):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if data:
                            if key.data == "stdout":
                                self.store.append_raw("stdout", data)
                                stdout_buffer += data
                            else:
                                self.store.append_raw("stderr", data)
                        selector.unregister(key.fileobj)
                    break
                continue
            for key, _ in ready:
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stderr":
                    self.store.append_raw("stderr", data)
                    continue
                self.store.append_raw("stdout", data)
                stdout_buffer += data
                while b"\n" in stdout_buffer:
                    line, stdout_buffer = stdout_buffer.split(b"\n", 1)
                    line_with_newline = line + b"\n"
                    last_event = time.monotonic()
                    try:
                        for event in observation.observe_line(line_with_newline, last_event):
                            self._emit(**event)
                    except StreamProtocolError as exc:
                        protocol_error = str(exc)
                    if timeout_keys:
                        timeout_keys.clear()
                        self._restore_running_after_observation()
                self._update_last_raw_event()
            self._observe_timeouts(started, last_event, observation, time.monotonic(), timeout_keys)

        return_code = process.wait()
        process.stdout.close()
        process.stderr.close()
        self.process = None
        if stdout_buffer and protocol_error is None:
            protocol_error = "unterminated stream-json output"
        state = self.store.load()
        if state.permissions["pending"] is not None:
            self._permission_required(return_code)
            return return_code or 3
        if protocol_error is not None:
            self._backend_failure(protocol_error)
            return return_code or 1
        if observation.session_ids != {self.invocation.session_id}:
            self._backend_failure("Claude Session ID did not match the invocation")
            return return_code or 1
        if return_code != 0:
            self._backend_failure(f"Claude exited with status {return_code}")
            return return_code
        if observation.result is None:
            self._backend_failure("Claude stream ended without a structured final result")
            return 1
        self._complete(observation.result)
        self._emit("process_exited", exit_code=return_code)
        return 0

    def _heartbeat(self, started: float, now: float) -> None:
        state = self.store.load()
        last_claim = state.progress_claims[-1]["received_at"] if state.progress_claims else None
        fields = {
            "process_alive": self.process is not None and self.process.poll() is None,
            "elapsed_seconds": round(now - started, 3),
            "last_raw_event_at": state.runtime.get("last_raw_event_at"),
            "last_progress_claim_at": last_claim,
        }
        self._emit("heartbeat", **fields)

        def mutate(current: object) -> None:
            current.runtime["last_heartbeat"] = {**fields, "recorded_at": utc_now()}

        self.store.update(mutate)

    def _observe_timeouts(
        self,
        started: float,
        last_event: float,
        observation: StreamObservation,
        now: float,
        emitted: set[str],
    ) -> None:
        candidates = [("model", now - last_event, self.model_idle_seconds, None), ("work_unit", now - started, self.work_unit_seconds, None)]
        candidates.extend(("tool", now - tool_started, self.tool_idle_seconds, tool_id) for tool_id, tool_started in observation.open_tools.items())
        for clock, elapsed, threshold, tool_id in candidates:
            key = f"{clock}:{tool_id or ''}"
            if elapsed < threshold or key in emitted:
                continue
            emitted.add(key)
            fields: dict[str, object] = {"clock": clock, "elapsed_seconds": round(elapsed, 3)}
            if tool_id:
                fields["tool_use_id"] = tool_id
            self._emit("timeout_suspected", **fields)

            def mutate(state: object) -> None:
                if state.status == "running":
                    state.transition_to(WorkUnitStatus.TIMEOUT_SUSPECTED)
                state.runtime.setdefault("timeout_observations", []).append({**fields, "observed_at": utc_now()})

            self.store.update(mutate)

    def _restore_running_after_observation(self) -> None:
        def mutate(state: object) -> None:
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)

        self.store.update(mutate)

    def _update_last_raw_event(self) -> None:
        def mutate(state: object) -> None:
            state.runtime["last_raw_event_at"] = utc_now()

        self.store.update(mutate)

    def _permission_required(self, return_code: int) -> None:
        def mutate(state: object) -> None:
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.transition_to(WorkUnitStatus.PERMISSION_REQUIRED)
            state.runtime["last_exit_code"] = return_code

        self.store.update(mutate)
        self._emit("permission_required", exit_code=return_code)

    def _backend_failure(self, message: str) -> None:
        def mutate(state: object) -> None:
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.transition_to(WorkUnitStatus.BACKEND_FAILURE)
            state.runtime["backend_failure"] = {"message": message, "recorded_at": utc_now()}

        self.store.update(mutate)
        self._emit("backend_failure", message=message)

    def _complete(self, result: dict[str, object]) -> None:
        def mutate(state: object) -> None:
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.data["result"] = result
            state.runtime["pid"] = None
            for segment in state.segments:
                if segment["session_id"] == self.invocation.session_id:
                    segment["status"] = "complete"
                    segment["finished_at"] = utc_now()
                    break
            if all(segment["status"] == "complete" for segment in state.segments):
                state.transition_to(WorkUnitStatus.IMPLEMENTATION_COMPLETE)

        self.store.update(mutate)

    def interrupt(self) -> None:
        self._signal(signal.SIGINT)

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def _signal(self, sig: signal.Signals) -> None:
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("no active Runner-owned Claude process")
        if os.name == "nt":
            self.process.send_signal(sig)
        else:
            os.killpg(self.process.pid, sig)
