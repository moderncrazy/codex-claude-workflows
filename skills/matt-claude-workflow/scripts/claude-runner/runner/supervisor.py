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
        self.terminate_deadline: float | None = None

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
            active = state.runtime.get("active_run")
            if isinstance(active, dict):
                state.runtime.setdefault("stale_runs", []).append(active)
            if state.status != "running":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.runtime.pop("control_requested", None)
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
            self._record_control_request("interrupt")
            self._signal(signal.SIGINT)
        if self.terminate_requested and self.control_applied is None:
            self.control_applied = "terminate"
            self._record_control_request("terminate")
            self._signal(signal.SIGTERM)
            self.terminate_deadline = now + self.termination_grace_seconds
        if (
            self.control_applied == "terminate"
            and self.terminate_deadline is not None
            and now >= self.terminate_deadline
            and self.process is not None
            and self.process.poll() is None
        ):
            self._signal(signal.SIGKILL)
            self.terminate_deadline = None

    def _record_control_request(self, action: str) -> None:
        def mutate(state: object) -> None:
            state.runtime["control_requested"] = {"action": action, "requested_at": utc_now()}

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
                        "segment_id": next(
                            segment["segment_id"]
                            for segment in state.segments
                            if segment["session_id"] == self.invocation.session_id
                        ),
                        "session_id": self.invocation.session_id,
                        "context": self.invocation.continuation_context,
                        "supplied_at": utc_now(),
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
        except (OSError, RuntimeError, ActiveRunError) as exc:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
            self.process = None
            self._backend_failure(f"failed to establish Runner process identity: {exc}")
            return 1
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
        if state.runtime.get("control_requested") is not None:
            self._interrupted(return_code)
            return return_code or 130
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
            state.runtime["pid"] = None
            state.runtime["process_group_id"] = None
            state.runtime["active_run"] = None

        self.store.update(mutate)
        self._emit("permission_required", exit_code=return_code)

    def _interrupted(self, return_code: int) -> None:
        def mutate(state: object) -> None:
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.transition_to(WorkUnitStatus.INTERRUPTED)
            state.runtime["last_exit_code"] = return_code
            state.runtime["pid"] = None
            state.runtime["process_group_id"] = None
            state.runtime["active_run"] = None

        self.store.update(mutate)
        self._emit("interrupted", exit_code=return_code)

    def _backend_failure(self, message: str) -> None:
        def mutate(state: object) -> None:
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.transition_to(WorkUnitStatus.BACKEND_FAILURE)
            state.runtime["backend_failure"] = {"message": message, "recorded_at": utc_now()}
            state.runtime["pid"] = None
            state.runtime["process_group_id"] = None
            state.runtime["active_run"] = None

        self.store.update(mutate)
        self._emit("backend_failure", message=message)

    def _complete(self, result: dict[str, object]) -> None:
        def mutate(state: object) -> None:
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.data["result"] = result
            state.runtime["pid"] = None
            state.runtime["process_group_id"] = None
            state.runtime["active_run"] = None
            for segment in state.segments:
                if segment["session_id"] == self.invocation.session_id:
                    segment["status"] = "complete"
                    segment["finished_at"] = utc_now()
                    break
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
            if state.status == "timeout_suspected":
                state.transition_to(WorkUnitStatus.RUNNING)
            state.data["result"] = result
            state.transition_to(target)
            if result_status == "PERMISSION_REQUIRED":
                request = result["permission_requests"][0]
                state.permissions["pending"] = {
                    "request": {"origin": "structured_result", **request},
                    "tool_name": request["tool"],
                    "tool_input": {"scope": request["scope"]},
                    "received_at": utc_now(),
                }
            state.runtime["pid"] = None
            state.runtime["process_group_id"] = None
            state.runtime["active_run"] = None
            for segment in state.segments:
                if segment["session_id"] == self.invocation.session_id:
                    segment["status"] = (
                        "permission_required" if target == WorkUnitStatus.PERMISSION_REQUIRED else "interrupted"
                    )
                    break

        self.store.update(mutate)
        self._emit("continuation_required", result_status=result_status, result=result)

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
