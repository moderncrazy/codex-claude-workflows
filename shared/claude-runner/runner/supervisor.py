from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Literal, Mapping, Sequence

from .contracts import ContractError, WorkUnitStatus, utc_now, validate_json_schema
from .permission_hooks import record_pending_permission
from .state_store import StateStore
from .stream_capture import StreamObservation, StreamProtocolError


class ActiveRunError(RuntimeError):
    pass


def capture_process_identity(pid: int) -> dict[str, object]:
    identity: dict[str, object] = {"pid": pid}
    if os.name != "nt":
        identity["process_group_id"] = os.getpgid(pid)
    return identity


@contextmanager
def inactive_lease_guard(state_dir: Path) -> Iterator[None]:
    path = state_dir / StateStore.RAW_FILES["stdout"]
    descriptor = os.open(path, os.O_RDWR)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            os.close(descriptor)
            raise ActiveRunError("this Work Unit already has a live Runner-owned process") from exc
        try:
            yield
        finally:
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            os.close(descriptor)
        return

    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise ActiveRunError("this Work Unit already has a live Runner-owned process") from exc
    try:
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def active_lease_held(state_dir: Path) -> bool:
    try:
        with inactive_lease_guard(state_dir):
            return False
    except ActiveRunError:
        return True


INTERRUPT_CONTROL_SIGNAL = getattr(signal, "SIGUSR1", signal.SIGINT)
TERMINATE_CONTROL_SIGNAL = getattr(signal, "SIGUSR2", signal.SIGTERM)
PROGRESS_TOOL_IDENTIFIER = "mcp__codex_claude_runner__report_progress"


@dataclass(frozen=True)
class ClaudeInvocation:
    executable: Path
    working_root: Path
    segment_id: str
    session_id: str
    resume: bool
    capability: Literal["sonnet", "opus"]
    allowed_tools: Sequence[str]
    reporter_config_json: str
    hook_settings_json: str
    result_schema: Path
    prompt: str
    continuation_context: str | None = None

    def protocol_prompt(self) -> str:
        return (
            f"{self.prompt}\n\n"
            "Claude Runner protocol:\n"
            f"- Your exact Session ID is `{self.session_id}`. Copy it exactly into the structured result session_id.\n"
            f"- `{PROGRESS_TOOL_IDENTIFIER}` is the required progress channel to Codex. "
            "Call it at Segment start, before a long operation, after verification, and before the final structured result. "
            "TaskUpdate is internal Claude state and does not reach Codex."
        )

    def argv(self) -> list[str]:
        mode = ["--resume", self.session_id] if self.resume else ["--session-id", self.session_id]
        allowed_rules = tuple(dict.fromkeys((*self.allowed_tools, PROGRESS_TOOL_IDENTIFIER)))
        allowed = [argument for rule in allowed_rules for argument in ("--allowedTools", rule)]
        return [
            str(self.executable),
            "-p",
            *mode,
            "--model",
            self.capability,
            "--permission-mode",
            "acceptEdits",
            *allowed,
            "--verbose",
            "--output-format",
            "stream-json",
            "--mcp-config",
            self.reporter_config_json,
            "--settings",
            self.hook_settings_json,
            "--json-schema",
            self.result_schema.read_text(encoding="utf-8"),
            self.protocol_prompt(),
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
        termination_grace_seconds: float = 15,
    ):
        self.store = store
        self.invocation = invocation
        self.event_sink = event_sink or (lambda event: None)
        self.environment = dict(environment) if environment is not None else None
        self.model_idle_seconds = model_idle_seconds
        self.tool_idle_seconds = tool_idle_seconds
        self.work_unit_seconds = work_unit_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.termination_grace_seconds = termination_grace_seconds
        self.process: subprocess.Popen[bytes] | None = None
        self.launch_token = str(uuid.uuid4())
        self.active_lease_descriptor: int | None = None
        self.previous_signal_handlers: dict[signal.Signals, object] = {}
        self.interrupt_requested = False
        self.terminate_requested = False
        self.control_applied: str | None = None
        self.control_stage: str | None = None
        self.control_deadline: float | None = None

    def _emit(self, kind: str, **fields: object) -> None:
        saved: dict[str, object] | None = None

        def record(state: object) -> None:
            nonlocal saved
            sequence = int(state.runtime.get("runner_event_sequence", 0)) + 1
            saved = {
                "type": "runner_event",
                "kind": kind,
                "sequence": sequence,
                "recorded_at": utc_now(),
                **fields,
            }
            state.runtime["runner_event_sequence"] = sequence
            state.runtime.setdefault("runner_events", []).append(saved)

        self.store.update(record)
        assert saved is not None
        self.event_sink(saved)

    def _reserve_launch(self) -> None:

        def reserve(state: object) -> None:
            if state.permissions["pending"] is not None:
                raise ContractError("pending permission blocks dispatch")
            if state.status == "finished":
                raise ContractError("a finished Work Unit cannot be dispatched")
            segment = next(
                (item for item in state.segments if item["segment_id"] == self.invocation.segment_id),
                None,
            )
            if segment is None:
                raise ContractError(f"unknown Segment {self.invocation.segment_id}")
            segment_index = state.segments.index(segment)
            if not self.invocation.resume and segment_index > 0:
                predecessor = state.segments[segment_index - 1]
                if predecessor["status"] != "complete":
                    raise ContractError(
                        f"complete {predecessor['segment_id']} before starting {segment['segment_id']}"
                    )
            if self.invocation.resume:
                if segment["session_id"] != self.invocation.session_id:
                    raise ContractError("recorded Segment Session ID changed before resume")
                if segment["status"] == "complete":
                    state.evidence["verified"] = [
                        item
                        for item in state.evidence["verified"]
                        if item.get("segment_id") != segment["segment_id"]
                    ]
                    state.runtime.pop("implementation_handoff_at", None)
                segment["resume_count"] += 1
            else:
                if segment["status"] != "pending" or segment["session_id"] is not None:
                    raise ContractError("a new Session requires a pending Segment without a Session ID")
                segment["session_id"] = self.invocation.session_id
                segment["attempt"] += 1
            active = state.runtime.get("active_run")
            if isinstance(active, dict):
                state.runtime.setdefault("stale_runs", []).append(active)
            if state.status != "running":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.runtime.pop("control_requested", None)
            state.data["result"] = None
            segment["status"] = "running"
            segment["started_at"] = segment["started_at"] or utc_now()
            segment["finished_at"] = None
            state.runtime["active_run"] = {
                "launch_token": self.launch_token,
                "controller_pid": os.getpid(),
                "identity": None,
                "reserved_at": utc_now(),
            }

        self.store.update(reserve)

    def _acquire_active_lease(self) -> None:
        path = self.store.state_dir / StateStore.RAW_FILES["stdout"]
        descriptor = os.open(path, os.O_RDWR)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                os.close(descriptor)
                raise ActiveRunError("this Work Unit already has a live Runner-owned process") from exc
        else:
            import fcntl

            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(descriptor)
                raise ActiveRunError("this Work Unit already has a live Runner-owned process") from exc
        self.active_lease_descriptor = descriptor

    def _release_active_lease(self) -> None:
        if self.active_lease_descriptor is None:
            return
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.active_lease_descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.active_lease_descriptor, fcntl.LOCK_UN)
        os.close(self.active_lease_descriptor)
        self.active_lease_descriptor = None

    def _install_control_handlers(self) -> None:
        for control_signal, attribute in (
            (INTERRUPT_CONTROL_SIGNAL, "interrupt_requested"),
            (TERMINATE_CONTROL_SIGNAL, "terminate_requested"),
        ):
            self.previous_signal_handlers[control_signal] = signal.getsignal(control_signal)
            signal.signal(control_signal, lambda _signum, _frame, name=attribute: setattr(self, name, True))

    def _restore_control_handlers(self) -> None:
        for control_signal, previous in self.previous_signal_handlers.items():
            signal.signal(control_signal, previous)
        self.previous_signal_handlers.clear()

    def _apply_control_requests(self, now: float) -> None:
        if self.interrupt_requested and self.control_applied is None:
            self.control_applied = "interrupt"
            self.control_stage = "interrupt"
            self._record_control_request("interrupt", "interrupt")
            if self._signal_control_stage(signal.SIGINT):
                self.control_deadline = time.monotonic() + self.termination_grace_seconds
        if self.terminate_requested and self.control_applied is None:
            self.control_applied = "terminate"
            self.control_stage = "terminate"
            self._record_control_request("terminate", "terminate")
            if self._signal_control_stage(signal.SIGTERM):
                self.control_deadline = time.monotonic() + self.termination_grace_seconds
        if (
            self.control_deadline is not None
            and now >= self.control_deadline
            and self.process is not None
            and self.process.poll() is None
        ):
            if self.control_stage == "interrupt":
                self.control_stage = "terminate"
                self._record_control_stage("terminate")
                if self._signal_control_stage(signal.SIGTERM):
                    self.control_deadline = time.monotonic() + self.termination_grace_seconds
                else:
                    self.control_deadline = None
            elif self.control_stage == "terminate":
                self.control_stage = "kill"
                self._record_control_stage("kill")
                self._signal_control_stage(signal.SIGKILL)
                self.control_deadline = None

    def _record_control_request(self, action: str, stage: str) -> None:
        def mutate(state: object) -> None:
            started_at = utc_now()
            state.runtime["control_requested"] = {
                "action": action,
                "requested_at": started_at,
                "stage": stage,
                "stage_started_at": started_at,
                "stages": [{"stage": stage, "started_at": started_at}],
            }

        self.store.update(mutate)

    def _record_control_stage(self, stage: str) -> None:
        def mutate(state: object) -> None:
            started_at = utc_now()
            control = state.runtime["control_requested"]
            control["stage"] = stage
            control["stage_started_at"] = started_at
            control["stages"].append({"stage": stage, "started_at": started_at})

        self.store.update(mutate)

    def _set_running(self, process: subprocess.Popen[bytes]) -> None:
        identity = capture_process_identity(process.pid)

        def mutate(state: object) -> None:
            active = state.runtime.get("active_run")
            if not isinstance(active, dict) or active.get("launch_token") != self.launch_token:
                raise ActiveRunError("Runner launch lease changed before process start")
            active["identity"] = identity
            state.runtime.update(
                {
                    "pid": process.pid,
                    "process_group_id": identity.get("process_group_id"),
                    "process_started_at": utc_now(),
                    "last_raw_event_at": None,
                    "last_invocation_capability": self.invocation.capability,
                }
            )
            if self.invocation.continuation_context is not None:
                state.runtime.setdefault("continuation_inputs", []).append(
                    {
                        "segment_id": self.invocation.segment_id,
                        "session_id": self.invocation.session_id,
                        "context": self.invocation.continuation_context,
                        "supplied_at": utc_now(),
                    }
                )
            segment = next(
                (item for item in state.segments if item["segment_id"] == self.invocation.segment_id),
                None,
            )
            if segment is None or segment["session_id"] != self.invocation.session_id:
                raise ActiveRunError("reserved Segment changed before process start")

        self.store.update(mutate)

    def run(self) -> int:
        self._acquire_active_lease()
        self._install_control_handlers()
        try:
            return self._run_with_lease()
        finally:
            self._restore_control_handlers()
            self._release_active_lease()

    def _run_with_lease(self) -> int:
        self._reserve_launch()
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
        try:
            self._set_running(process)
        except Exception as exc:
            self._reap_failed_launch(process)
            self._backend_failure(f"failed to establish Runner process identity: {exc}")
            return 1
        started = last_event = time.monotonic()
        next_heartbeat = started + self.heartbeat_seconds
        observation = StreamObservation()
        permission_denial_handled = False
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
            self._apply_control_requests(now)
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
                    if protocol_error is None:
                        try:
                            for event in observation.observe_line(line_with_newline, last_event):
                                self._emit(**event)
                            if observation.permission_denial is not None and not permission_denial_handled:
                                self._broker_stream_permission_denial(observation.permission_denial)
                                permission_denial_handled = True
                                self.interrupt()
                        except StreamProtocolError as exc:
                            protocol_error = str(exc)
                    if timeout_keys:
                        timeout_keys.clear()
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
            return 3
        if state.runtime.get("control_requested") is not None:
            self._interrupted(return_code)
            return return_code or 130
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
        try:
            schema = json.loads(self.invocation.result_schema.read_text(encoding="utf-8"))
            validate_json_schema(observation.result, schema)
            if observation.result.get("session_id") != self.invocation.session_id:
                raise ContractError("structured result Session ID did not match the invocation")
        except (OSError, json.JSONDecodeError, ContractError) as exc:
            self._backend_failure(f"structured result validation failed: {exc}")
            return 1
        if observation.result["status"] not in {"DONE", "DONE_WITH_CONCERNS"}:
            self._continuation_required(observation.result)
            return 3
        self._complete(observation.result)
        self._emit("process_exited", exit_code=return_code)
        return 0

    def _reap_failed_launch(self, process: subprocess.Popen[bytes]) -> None:
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        except ProcessLookupError:
            process.wait(timeout=5)
        finally:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            self.process = None

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
                state.runtime.setdefault("timeout_observations", []).append({**fields, "observed_at": utc_now()})

            self.store.update(mutate)

    def _update_last_raw_event(self) -> None:
        def mutate(state: object) -> None:
            state.runtime["last_raw_event_at"] = utc_now()

        self.store.update(mutate)

    def _broker_stream_permission_denial(self, denial: dict[str, object]) -> None:
        def mutate(state: object) -> None:
            if state.permissions["pending"] is None:
                record_pending_permission(
                    state,
                    denial["request"],
                    tool_name=denial["tool_name"],
                    tool_input=denial["tool_input"],
                )

        self.store.update(mutate)

    def _permission_required(self, return_code: int) -> None:
        def mutate(state: object) -> None:
            state.transition_to(WorkUnitStatus.PERMISSION_REQUIRED)
            state.runtime["last_exit_code"] = return_code
            state.runtime.pop("control_requested", None)
            self._finish_invocation_state(state, "permission_required")

        self.store.update(mutate)
        self.interrupt_requested = False
        self.terminate_requested = False
        self.control_applied = None
        self.control_stage = None
        self.control_deadline = None
        self._emit("permission_required", exit_code=return_code)

    def _interrupted(self, return_code: int) -> None:
        def mutate(state: object) -> None:
            state.transition_to(WorkUnitStatus.INTERRUPTED)
            state.runtime["last_exit_code"] = return_code
            self._finish_invocation_state(state, "interrupted")

        self.store.update(mutate)
        self._emit("interrupted", exit_code=return_code)

    def _backend_failure(self, message: str) -> None:
        def mutate(state: object) -> None:
            state.transition_to(WorkUnitStatus.BACKEND_FAILURE)
            state.runtime["backend_failure"] = {"message": message, "recorded_at": utc_now()}
            self._finish_invocation_state(state, "failed", require_session_match=False)

        self.store.update(mutate)
        self._emit("backend_failure", message=message)

    def _complete(self, result: dict[str, object]) -> None:
        def mutate(state: object) -> None:
            state.data["result"] = result
            segment = self._finish_invocation_state(state, "complete")
            self._record_result(state, segment, result)
            if all(segment["status"] == "complete" for segment in state.segments):
                state.transition_to(WorkUnitStatus.IMPLEMENTATION_COMPLETE)

        self.store.update(mutate)

    def _continuation_required(self, result: dict[str, object]) -> None:
        result_status = str(result["status"])
        target = (
            WorkUnitStatus.PERMISSION_REQUIRED
            if result_status == "PERMISSION_REQUIRED"
            else WorkUnitStatus.INTERRUPTED
        )

        def mutate(state: object) -> None:
            state.data["result"] = result
            state.transition_to(target)
            segment = self._finish_invocation_state(
                state,
                "permission_required" if target == WorkUnitStatus.PERMISSION_REQUIRED else "interrupted",
            )
            self._record_result(state, segment, result)
            if result_status == "PERMISSION_REQUIRED":
                request = result["permission_requests"][0]
                state.permissions["pending"] = {
                    "segment_id": segment["segment_id"],
                    "request": {"origin": "structured_result", **request},
                    "tool_name": request["tool"],
                    "tool_input": {"scope": request["scope"]},
                    "received_at": utc_now(),
                }
        self.store.update(mutate)
        self._emit("continuation_required", result_status=result_status, result=result)

    def _finish_invocation_state(
        self,
        state: object,
        segment_status: str,
        *,
        require_session_match: bool = True,
    ) -> dict[str, object]:
        state.runtime["pid"] = None
        state.runtime["process_group_id"] = None
        state.runtime["active_run"] = None
        segment = next(
            item for item in state.segments if item["segment_id"] == self.invocation.segment_id
        )
        if require_session_match and segment["session_id"] != self.invocation.session_id:
            raise ContractError("reserved Segment Session ID changed before invocation completion")
        segment["status"] = segment_status
        if segment_status in {"complete", "failed"}:
            segment["finished_at"] = utc_now()
        return segment

    def _record_result(
        self,
        state: object,
        segment: dict[str, object],
        result: dict[str, object],
    ) -> None:
        state.runtime.setdefault("result_history", []).append(
            {
                "segment_id": segment["segment_id"],
                "session_id": self.invocation.session_id,
                "launch_token": self.launch_token,
                "result": result,
                "recorded_at": utc_now(),
            }
        )

    def interrupt(self) -> None:
        self.interrupt_requested = True

    def terminate(self) -> None:
        self.terminate_requested = True

    def _signal(self, sig: signal.Signals) -> None:
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("no active Runner-owned Claude process")
        if os.name == "nt":
            self.process.send_signal(sig)
        else:
            os.killpg(self.process.pid, sig)

    def _signal_control_stage(self, sig: signal.Signals) -> bool:
        try:
            self._signal(sig)
        except (ProcessLookupError, RuntimeError):
            return False
        return True
