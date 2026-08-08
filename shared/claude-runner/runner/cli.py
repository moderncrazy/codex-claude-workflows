from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .contracts import ContractError, WorkUnitState, WorkUnitStatus, utc_now
from .permission_hooks import build_hook_settings, handle_permission_denied, handle_permission_request
from .progress_mcp import serve_progress_mcp
from .state_store import StateStore
from .supervisor import (
    INTERRUPT_CONTROL_SIGNAL,
    TERMINATE_CONTROL_SIGNAL,
    ActiveRunError,
    ClaudeInvocation,
    Supervisor,
    active_lease_held,
    inactive_lease_guard,
)


CONTROL_RESERVATION_WAIT_SECONDS = 1.0
CONTROL_RESERVATION_POLL_SECONDS = 0.01


class CliError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def _state_summary(store: StateStore, *, events: list[dict[str, object]] | None = None) -> dict[str, object]:
    state = store.load()
    payload: dict[str, object] = {
        "work_unit_id": state.work_unit_id,
        "state_dir": str(store.state_dir),
        "status": state.status,
        "segments": state.segments,
        "permissions": state.permissions,
        "result": state.result,
    }
    if events is not None:
        payload["runner_events"] = events
    return payload


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="claude_runner.py")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--working-root", required=True, type=Path)
    init.add_argument("--workflow", required=True, choices=["superpowers", "matt"])
    init.add_argument("--native-ref", required=True)
    init.add_argument("--fixed-point", required=True)
    init.add_argument("--capability", required=True, choices=["sonnet", "opus"])
    init.add_argument("--result-schema", required=True, type=Path)
    init.add_argument("--claude-executable", default="claude", type=Path)
    init.add_argument("--prompt", required=True)
    init.add_argument("--allowed-tool", action="append", default=[])
    init.add_argument("--segments-json", required=True)
    init.add_argument("--work-unit-id")
    init.add_argument("--model-idle-seconds", type=float, default=600)
    init.add_argument("--tool-idle-seconds", type=float, default=1800)
    init.add_argument("--work-unit-seconds", type=float, default=14400)
    init.add_argument("--heartbeat-seconds", type=float, default=30)
    init.add_argument("--termination-grace-seconds", type=float, default=15)

    for name in ("run", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--state-dir", required=True, type=Path)
        command.add_argument("--segment-id")
        if name == "resume":
            command.add_argument("--continuation-context")
    for name in ("status", "interrupt", "terminate"):
        command = commands.add_parser(name)
        command.add_argument("--state-dir", required=True, type=Path)
    finish = commands.add_parser("finish")
    finish.add_argument("--state-dir", required=True, type=Path)
    finish.add_argument("--native-workflow-complete", action="store_true")
    wait = commands.add_parser("wait")
    wait.add_argument("--state-dir", required=True, type=Path)
    wait.add_argument("--after-sequence", type=int, default=0)
    wait.add_argument("--poll-seconds", type=float, default=0.25)
    wait.add_argument("--max-wait-seconds", type=float)

    approve = commands.add_parser("approve-permission")
    approve.add_argument("--state-dir", required=True, type=Path)
    approve.add_argument("--expected-tool-name", required=True)
    approve.add_argument("--allow-rule", required=True)

    for name in ("deny-permission", "dismiss-permission"):
        resolution = commands.add_parser(name)
        resolution.add_argument("--state-dir", required=True, type=Path)
        resolution.add_argument("--expected-tool-name", required=True)
        resolution.add_argument("--reason", required=True)

    extend = commands.add_parser("extend")
    extend.add_argument("--state-dir", required=True, type=Path)
    extend.add_argument("--clock", required=True, choices=["model", "tool", "work_unit"])
    extend.add_argument("--seconds", required=True, type=float)

    verify = commands.add_parser("record-verification")
    verify.add_argument("--state-dir", required=True, type=Path)
    verify.add_argument("--command", dest="verification_command", required=True)
    verify.add_argument("--exit-code", required=True, type=int)
    verify.add_argument("--evidence-ref", required=True)
    verify.add_argument("--segment-id")

    repair = commands.add_parser("add-repair-segment")
    repair.add_argument("--state-dir", required=True, type=Path)
    repair.add_argument("--scope", required=True)
    repair.add_argument("--finding-id", action="append", required=True)
    repair.add_argument("--verification-command", action="append", default=[])
    repair.add_argument("--capability", choices=["sonnet", "opus"])

    restart = commands.add_parser("restart-segment-session")
    restart.add_argument("--state-dir", required=True, type=Path)
    restart.add_argument("--segment-id", required=True)
    restart.add_argument("--reason", required=True)

    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--state-dir", required=True, type=Path)
    cleanup.add_argument("--native-workflow-complete", action="store_true")

    hook = commands.add_parser("hook")
    hook.add_argument("event", choices=["permission-request", "permission-denied"])
    hook.add_argument("--state-dir", required=True, type=Path)
    reporter = commands.add_parser("report-progress")
    reporter.add_argument("--state-dir", required=True, type=Path)
    return root


def _validated_root(root: Path) -> Path:
    root = root.resolve()
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0 or Path(completed.stdout.strip()).resolve() != root:
        raise CliError("invalid_working_root", "working root must be the repository root")
    ignored = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", ".tmp/codex-claude-workflows/probe"],
        check=False,
    )
    if ignored.returncode != 0:
        raise CliError("tmp_not_ignored", "add /.tmp/ to .gitignore before fixing the implementation baseline")
    return root


def _segments(value: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CliError("invalid_segments", str(exc)) from exc
    if not isinstance(parsed, list) or not parsed:
        raise CliError("invalid_segments", "segments-json must be a non-empty JSON array")
    now = utc_now()
    result = []
    for item in parsed:
        if not isinstance(item, dict):
            raise CliError("invalid_segments", "each segment must be an object")
        result.append(
            {
                "segment_id": str(item["segment_id"]),
                "kind": str(item["kind"]),
                "scope": str(item["scope"]),
                "verification_commands": list(item.get("verification_commands", [])),
                "status": "pending",
                "session_id": None,
                "attempt": 0,
                "resume_count": 0,
                "created_at": now,
                "started_at": None,
                "finished_at": None,
            }
        )
    return result


def _executable_value(executable: Path) -> str:
    if not executable.is_absolute() and executable.parent == Path("."):
        return str(executable)
    return str(executable.resolve())


def _init(args: argparse.Namespace) -> int:
    root = _validated_root(args.working_root)
    result_schema = args.result_schema.resolve()
    if not result_schema.is_file():
        raise CliError("missing_result_schema", str(result_schema))
    work_unit_id = args.work_unit_id or str(uuid.uuid4())
    try:
        uuid.UUID(work_unit_id)
    except ValueError as exc:
        raise CliError("invalid_work_unit_id", work_unit_id) from exc
    runtime = {
        "configuration": {
            "claude_executable": _executable_value(args.claude_executable),
            "result_schema": str(result_schema),
            "prompt": args.prompt,
            "thresholds": {
                "model_idle_seconds": args.model_idle_seconds,
                "tool_idle_seconds": args.tool_idle_seconds,
                "work_unit_seconds": args.work_unit_seconds,
                "heartbeat_seconds": args.heartbeat_seconds,
                "termination_grace_seconds": args.termination_grace_seconds,
            },
        },
        "result_history": [],
    }
    state = WorkUnitState.from_dict(
        {
            "schema_version": 2,
            "work_unit_id": work_unit_id,
            "workflow": args.workflow,
            "native_ref": args.native_ref,
            "working_root": str(root),
            "fixed_point": args.fixed_point,
            "executor": {"agent": "claude-code", "capability": args.capability},
            "status": "initialized",
            "segments": _segments(args.segments_json),
            "permissions": {"initial": list(args.allowed_tool), "approved": [], "pending": None, "resolved": []},
            "runtime": runtime,
            "progress_claims": [],
            "evidence": {"declared": [], "verified": []},
            "commits": [],
            "result": None,
        }
    )
    store = StateStore.create(state)
    _emit(_state_summary(store))
    return 0


def _entrypoint() -> Path:
    return Path(__file__).parents[1] / "claude_runner.py"


def _segment_verified(state: WorkUnitState, segment_id: str) -> bool:
    return any(
        item.get("segment_id") == segment_id and item.get("exit_code") == 0
        for item in state.evidence["verified"]
    )


def _run(args: argparse.Namespace, *, resume: bool) -> int:
    store = StateStore(args.state_dir)
    state = store.load()
    if state.status == "finished":
        raise CliError("work_unit_finished", "a finished Work Unit cannot be dispatched")
    if state.permissions["pending"] is not None:
        raise CliError("pending_permission", "approve or deny the pending permission before dispatch")
    if args.segment_id:
        segment = next((item for item in state.segments if item["segment_id"] == args.segment_id), None)
        if segment is None:
            raise CliError("unknown_segment", args.segment_id)
    else:
        segment = next((item for item in state.segments if item["status"] != "complete"), None)
    if segment is None:
        raise CliError("no_pending_segment", "all segments are complete")
    segment_index = next(index for index, item in enumerate(state.segments) if item["segment_id"] == segment["segment_id"])
    if not resume and segment_index > 0:
        predecessor = state.segments[segment_index - 1]
        if predecessor["status"] != "complete":
            raise CliError(
                "segment_incomplete",
                f"complete {predecessor['segment_id']} before starting {segment['segment_id']}",
            )
    if resume:
        if not segment["session_id"]:
            raise CliError("missing_session", "resume requires the recorded Segment Session ID")
        continuation_context = args.continuation_context
        if state.result and state.result.get("status") == "NEEDS_CONTEXT" and not continuation_context:
            raise CliError(
                "continuation_context_required",
                "resume requires Codex-supplied continuation context for NEEDS_CONTEXT",
            )
        if continuation_context and len(continuation_context.encode("utf-8")) > 65536:
            raise CliError("continuation_context_too_large", "continuation context exceeds 65536 UTF-8 bytes")
        session_id = str(segment["session_id"])
    else:
        session_id = str(uuid.uuid4())
    configuration = state.runtime["configuration"]
    reporter = {
        "mcpServers": {
            "codex_claude_runner": {
                "command": sys.executable,
                "args": [str(_entrypoint()), "report-progress", "--state-dir", str(store.state_dir)],
            }
        }
    }
    settings = build_hook_settings(store.state_dir, Path(sys.executable), _entrypoint())
    invocation = ClaudeInvocation(
        executable=Path(configuration["claude_executable"]),
        working_root=Path(state.working_root),
        segment_id=str(segment["segment_id"]),
        session_id=session_id,
        resume=resume,
        capability=segment.get("capability", state.executor["capability"]),
        allowed_tools=tuple(
            state.permissions["initial"] + [approval["rule"] for approval in state.permissions["approved"]]
        ),
        reporter_config_json=json.dumps(reporter, separators=(",", ":")),
        hook_settings_json=json.dumps(settings, separators=(",", ":")),
        result_schema=Path(configuration["result_schema"]),
        continuation_context=args.continuation_context if resume else None,
        prompt=(
            f"{configuration['prompt']}\n\nExecution Segment scope: {segment['scope']}"
            + (f"\n\nCodex continuation context:\n{args.continuation_context}" if resume and args.continuation_context else "")
        ),
    )
    supervisor = Supervisor(store, invocation, event_sink=_emit, environment=os.environ, **configuration["thresholds"])
    try:
        code = supervisor.run()
    except ActiveRunError as exc:
        raise CliError("work_unit_active", str(exc)) from exc
    _emit(_state_summary(store))
    return code


def _resolve_permission(
    store: StateStore,
    *,
    expected_tool_name: str,
    resolution: str,
    reason: str | None,
    allow_rule: str | None,
) -> None:
    def mutate(state: WorkUnitState) -> None:
        pending = state.permissions["pending"]
        if pending is None:
            raise CliError("no_pending_permission", "there is no permission request to resolve")
        if pending.get("tool_name") != expected_tool_name:
            raise CliError("permission_mismatch", "pending tool does not match expected-tool-name")
        segment = next(
            (item for item in state.segments if item["segment_id"] == pending["segment_id"]),
            None,
        )
        if segment is None:
            raise CliError("unknown_segment", str(pending["segment_id"]))
        resolved_at = utc_now()
        if resolution == "approved":
            assert allow_rule is not None
            state.permissions["approved"].append(
                {"rule": allow_rule, "approved_at": resolved_at, "request": pending["request"]}
            )
        state.permissions["resolved"].append(
            {
                "resolution": resolution,
                "reason": reason,
                "rule": allow_rule,
                "segment_id": segment["segment_id"],
                "request": pending["request"],
                "resolved_at": resolved_at,
            }
        )
        state.permissions["pending"] = None
        segment["status"] = "interrupted"
        segment["finished_at"] = None
        state.transition_to(WorkUnitStatus.INTERRUPTED)

    try:
        with inactive_lease_guard(store.state_dir):
            store.update(mutate)
    except ActiveRunError as exc:
        raise CliError("active_process", "cannot resolve permission while the Runner is active") from exc


def _approve(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)
    _resolve_permission(
        store,
        expected_tool_name=args.expected_tool_name,
        resolution="approved",
        reason=None,
        allow_rule=args.allow_rule,
    )

    _emit(_state_summary(store))
    return 0


def _reject_permission(args: argparse.Namespace, resolution: str) -> int:
    store = StateStore(args.state_dir)
    _resolve_permission(
        store,
        expected_tool_name=args.expected_tool_name,
        resolution=resolution,
        reason=args.reason,
        allow_rule=None,
    )

    _emit(_state_summary(store))
    return 0


def _record_verification(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)

    def mutate(state: WorkUnitState) -> None:
        segment_id = args.segment_id
        if segment_id is None:
            candidates = [
                segment["segment_id"]
                for segment in state.segments
                if segment["status"] == "complete" and not _segment_verified(state, segment["segment_id"])
            ]
            if len(candidates) != 1:
                raise CliError("segment_id_required", "specify the Segment receiving this verification")
            segment_id = candidates[0]
        if not any(segment["segment_id"] == segment_id and segment["status"] == "complete" for segment in state.segments):
            raise CliError("segment_not_complete", "verification requires a completed Segment")
        state.evidence["verified"].append(
            {
                "segment_id": segment_id,
                "command": args.verification_command,
                "exit_code": args.exit_code,
                "evidence_ref": args.evidence_ref,
                "verified_at": utc_now(),
            }
        )

    store.update(mutate)
    _emit(_state_summary(store))
    return 0


def _finish(args: argparse.Namespace) -> int:
    if not args.native_workflow_complete:
        raise CliError("native_completion_required", "finish requires Codex's native workflow completion assertion")
    store = StateStore(args.state_dir)

    def mutate(state: WorkUnitState) -> None:
        if state.permissions["pending"] is not None:
            raise CliError("pending_permission", "resolve the pending permission before finish")
        if state.status != "implementation_complete" or any(segment["status"] != "complete" for segment in state.segments):
            raise CliError("segments_incomplete", "all Execution Segments must be complete")
        state.transition_to(WorkUnitStatus.FINISHED)
        state.runtime["finished_at"] = utc_now()

    try:
        with inactive_lease_guard(store.state_dir):
            store.update(mutate)
    except ActiveRunError as exc:
        raise CliError("active_process", "cannot finish while the Runner is active") from exc
    _emit(_state_summary(store))
    return 0


def _cleanup(args: argparse.Namespace) -> int:
    supplied = args.state_dir.absolute()
    if supplied.is_symlink():
        raise CliError("unsafe_cleanup_target", "state directory must not be a symlink")
    store = StateStore(supplied)
    def validate_cleanup(state: WorkUnitState) -> None:
        if state.status != "finished":
            raise CliError("finish_required", "finish must record native completion before cleanup")
        root = Path(state.working_root).resolve()
        expected = root / ".tmp" / "codex-claude-workflows" / state.work_unit_id
        if supplied.resolve() != expected or supplied.name != state.work_unit_id:
            raise CliError("unsafe_cleanup_target", "state directory is outside the owned Work Unit path")

    try:
        with inactive_lease_guard(store.state_dir):
            state = store.update(validate_cleanup)
    except ActiveRunError as exc:
        raise CliError("active_process", "cannot clean an active Work Unit") from exc
    shutil.rmtree(supplied)
    _emit({"work_unit_id": state.work_unit_id, "state_dir": str(supplied), "status": "cleaned"})
    return 0


def _extend(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)
    key = f"{args.clock}_seconds" if args.clock != "work_unit" else "work_unit_seconds"

    def mutate(state: WorkUnitState) -> None:
        state.runtime["configuration"]["thresholds"][key] = args.seconds
        state.runtime.setdefault("timeout_extensions", []).append({"clock": args.clock, "seconds": args.seconds, "at": utc_now()})
    store.update(mutate)
    _emit(_state_summary(store))
    return 0


def _add_repair(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)

    def mutate(state: WorkUnitState) -> None:
        if state.status == "finished":
            raise CliError("work_unit_finished", "a finished Work Unit cannot add a Repair Segment")
        if any(segment["status"] != "complete" for segment in state.segments):
            raise CliError("segments_incomplete", "all existing Segments must be complete before a Repair Segment")
        if state.status == "implementation_complete":
            state.transition_to(WorkUnitStatus.RUNNING)
        state.runtime.pop("implementation_handoff_at", None)
        state.segments.append(
            {
                "segment_id": f"repair-{len(state.segments) + 1}",
                "kind": "repair",
                "scope": args.scope,
                "finding_ids": list(args.finding_id),
                "capability": args.capability or state.executor["capability"],
                "verification_commands": list(args.verification_command),
                "status": "pending",
                "session_id": None,
                "attempt": 0,
                "resume_count": 0,
                "created_at": utc_now(),
                "started_at": None,
                "finished_at": None,
            }
        )

    try:
        with inactive_lease_guard(store.state_dir):
            store.update(mutate)
    except ActiveRunError as exc:
        raise CliError("active_process", "cannot add a Repair Segment while the Runner is active") from exc
    _emit(_state_summary(store))
    return 0


def _restart_segment_session(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)
    state = store.load()
    if state.status == "finished":
        raise CliError("work_unit_finished", "a finished Work Unit cannot restart a Session")
    if state.status != "backend_failure":
        raise CliError("backend_failure_required", "only a backend-failed Work Unit can restart a Session")
    if active_lease_held(store.state_dir):
        raise CliError("active_process", "cannot restart a Session while the Runner is active")

    def mutate(current: WorkUnitState) -> None:
        segment = next((item for item in current.segments if item["segment_id"] == args.segment_id), None)
        if segment is None:
            raise CliError("unknown_segment", args.segment_id)
        if segment["status"] == "complete":
            raise CliError("segment_complete", "cannot replace a completed Segment Session")
        if segment["session_id"] is None:
            raise CliError("missing_session", "the Segment has no failed Session to replace")
        current.runtime.setdefault("abandoned_sessions", []).append(
            {
                "segment_id": segment["segment_id"],
                "session_id": segment["session_id"],
                "reason": args.reason,
                "abandoned_at": utc_now(),
            }
        )
        segment["session_id"] = None
        segment["status"] = "pending"
        segment["started_at"] = None
        segment["finished_at"] = None
        current.data["result"] = None
        current.runtime["active_run"] = None
        current.runtime["pid"] = None
        current.runtime["process_group_id"] = None
        current.runtime.pop("control_requested", None)

    store.update(mutate)
    _emit(_state_summary(store))
    return 0


def _control(args: argparse.Namespace, action: str) -> int:
    store = StateStore(args.state_dir)
    state = store.load()
    if state.status == "interrupted":
        deadline = time.monotonic() + CONTROL_RESERVATION_WAIT_SECONDS
        while active_lease_held(store.state_dir):
            if time.monotonic() >= deadline:
                raise CliError(
                    "unsafe_process_identity",
                    "active Runner did not publish its controller identity",
                )
            time.sleep(CONTROL_RESERVATION_POLL_SECONDS)
            state = store.load()
            if state.status != "interrupted":
                break
        else:
            _emit({"work_unit_id": state.work_unit_id, "status": state.status, "control": action})
            return 0
    active = state.runtime.get("active_run")
    if not isinstance(active, dict) or not active_lease_held(store.state_dir):
        def fail(current: WorkUnitState) -> None:
            if current.status == "running":
                current.transition_to(WorkUnitStatus.BACKEND_FAILURE)
            for segment in current.segments:
                if segment["status"] == "running":
                    segment["status"] = "failed"
                    segment["finished_at"] = utc_now()
            current.data["result"] = None
            current.runtime["active_run"] = None
            current.runtime["pid"] = None
            current.runtime["process_group_id"] = None
            current.runtime["backend_failure"] = {
                "message": "unsafe or stale Runner process identity",
                "recorded_at": utc_now(),
            }

        store.update(fail)
        raise CliError("unsafe_process_identity", "no validated Runner-owned process identity")
    controller_pid = active.get("controller_pid")
    if not isinstance(controller_pid, int):
        raise CliError("unsafe_process_identity", "active lease lacks its Runner controller PID")
    control_signal = INTERRUPT_CONTROL_SIGNAL if action == "interrupt" else TERMINATE_CONTROL_SIGNAL
    try:
        os.kill(controller_pid, control_signal)
    except ProcessLookupError as exc:
        raise CliError("control_failed", str(exc)) from exc
    _emit({"work_unit_id": state.work_unit_id, "status": state.status, "control": action})
    return 0


def _wait(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)
    after = args.after_sequence
    started = time.monotonic()
    terminal = {"permission_required", "backend_failure", "implementation_complete", "interrupted", "finished"}
    while True:
        state = store.load()
        for event in state.runtime.get("runner_events", []):
            if int(event.get("sequence", 0)) > after:
                _emit(event)
                after = int(event["sequence"])
        if state.status in terminal:
            _emit(_state_summary(store))
            return 0
        if args.max_wait_seconds is not None and time.monotonic() - started >= args.max_wait_seconds:
            _emit({"work_unit_id": state.work_unit_id, "status": state.status, "wait_timed_out": True})
            return 3
        time.sleep(args.poll_seconds)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "run":
            return _run(args, resume=False)
        if args.command == "resume":
            return _run(args, resume=True)
        if args.command == "status":
            _emit(_state_summary(StateStore(args.state_dir)))
            return 0
        if args.command == "wait":
            return _wait(args)
        if args.command == "approve-permission":
            return _approve(args)
        if args.command == "deny-permission":
            return _reject_permission(args, "denied")
        if args.command == "dismiss-permission":
            return _reject_permission(args, "dismissed")
        if args.command == "extend":
            return _extend(args)
        if args.command == "record-verification":
            return _record_verification(args)
        if args.command == "finish":
            return _finish(args)
        if args.command == "add-repair-segment":
            return _add_repair(args)
        if args.command == "restart-segment-session":
            return _restart_segment_session(args)
        if args.command == "cleanup":
            return _cleanup(args)
        if args.command == "interrupt":
            return _control(args, "interrupt")
        if args.command == "terminate":
            return _control(args, "terminate")
        if args.command == "report-progress":
            return serve_progress_mcp(args.state_dir)
        if args.event == "permission-request":
            return handle_permission_request(args.state_dir)
        return handle_permission_denied(args.state_dir)
    except CliError as exc:
        _emit({"error": exc.code, "message": str(exc)})
        return 2
    except (ContractError, json.JSONDecodeError, OSError, TimeoutError) as exc:
        _emit({"error": "invalid_or_unavailable_state", "message": str(exc)})
        return 2
