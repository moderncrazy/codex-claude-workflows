from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path


RUNNER_ROOT = Path(__file__).parents[1] / "shared" / "claude-runner"
FIXTURE = Path(__file__).parent / "fixtures" / "fake_claude.py"
RESULT_SCHEMA = Path(__file__).parents[1] / "skills" / "superpowers-claude-workflow" / "references" / "claude-result.schema.json"
sys.path.insert(0, str(RUNNER_ROOT))

from runner.permission_hooks import build_hook_settings  # noqa: E402
from runner.contracts import ContractError  # noqa: E402
from runner.state_store import StateStore  # noqa: E402
from runner.supervisor import ActiveRunError, ClaudeInvocation, Supervisor  # noqa: E402
from tests.test_runner_state import sample_work_unit  # noqa: E402


SESSION_ID = "0c2fb298-155f-4af0-bc6f-35e229fd27f3"


class SupervisorTests(unittest.TestCase):
    def make_supervisor(self, root: Path, scenario: str, **thresholds: float) -> tuple[StateStore, Supervisor, list[dict[str, object]]]:
        state = sample_work_unit(root)
        store = StateStore.create(state)
        settings = build_hook_settings(store.state_dir, Path(sys.executable), RUNNER_ROOT / "claude_runner.py")
        invocation = ClaudeInvocation(
            executable=FIXTURE,
            working_root=root,
            segment_id="segment-1",
            session_id=SESSION_ID,
            resume=False,
            capability="sonnet",
            allowed_tools=("Bash(pytest *)", "mcp__codegraph__explore"),
            reporter_config_json=json.dumps({"mcpServers": {"codex_claude_runner": {"command": "python3"}}}),
            hook_settings_json=json.dumps(settings),
            result_schema=RESULT_SCHEMA,
            prompt="Implement the fixture",
        )
        events: list[dict[str, object]] = []
        environment = dict(os.environ, FAKE_CLAUDE_SCENARIO=scenario, FAKE_CLAUDE_DELAY="0.12")
        supervisor = Supervisor(store, invocation, event_sink=events.append, environment=environment, **thresholds)
        return store, supervisor, events

    def test_concurrent_initial_launch_reserves_one_session_under_active_lease(self) -> None:
        class BarrierSupervisor(Supervisor):
            def _acquire_active_lease(self) -> None:
                launch_barrier.wait(timeout=5)
                super()._acquire_active_lease()

            def _install_control_handlers(self) -> None:
                pass

            def _restore_control_handlers(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = sample_work_unit(root)
            store = StateStore.create(state)
            settings = build_hook_settings(store.state_dir, Path(sys.executable), RUNNER_ROOT / "claude_runner.py")
            launch_barrier = threading.Barrier(2)
            session_ids = (
                "0c2fb298-155f-4af0-bc6f-35e229fd27f3",
                "3ec1c07a-584c-4fef-a29b-3bd55b056ab4",
            )
            supervisors = [
                BarrierSupervisor(
                    store,
                    ClaudeInvocation(
                        executable=FIXTURE,
                        working_root=root,
                        segment_id="segment-1",
                        session_id=session_id,
                        resume=False,
                        capability="sonnet",
                        allowed_tools=(),
                        reporter_config_json=json.dumps({"mcpServers": {}}),
                        hook_settings_json=json.dumps(settings),
                        result_schema=RESULT_SCHEMA,
                        prompt="Implement the fixture",
                    ),
                    environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="model-idle", FAKE_CLAUDE_DELAY="0.4"),
                )
                for session_id in session_ids
            ]
            outcomes: list[tuple[int, int | BaseException]] = []

            def launch(index: int) -> None:
                try:
                    outcomes.append((index, supervisors[index].run()))
                except BaseException as exc:
                    outcomes.append((index, exc))

            threads = [threading.Thread(target=launch, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            successful = [index for index, result in outcomes if result == 0]
            rejected = [result for _, result in outcomes if isinstance(result, ActiveRunError)]
            self.assertEqual(len(successful), 1, outcomes)
            self.assertEqual(len(rejected), 1, outcomes)
            persisted = store.load().segments[0]
            self.assertEqual(persisted["session_id"], session_ids[successful[0]])
            self.assertEqual(persisted["attempt"], 1)

    def test_post_spawn_reservation_mismatch_reaps_child_and_records_failure(self) -> None:
        class MismatchingSupervisor(Supervisor):
            def _set_running(self, process: object) -> None:
                self.store.update(
                    lambda state: state.segments[0].__setitem__(
                        "session_id", "3ec1c07a-584c-4fef-a29b-3bd55b056ab4"
                    )
                )
                super()._set_running(process)

        with tempfile.TemporaryDirectory() as directory:
            store, original, _ = self.make_supervisor(Path(directory), "model-idle")
            supervisor = MismatchingSupervisor(
                store,
                original.invocation,
                environment=original.environment,
            )

            self.assertEqual(supervisor.run(), 1)
            state = store.load()
            self.assertEqual(state.status, "backend_failure")
            self.assertEqual(state.segments[0]["status"], "failed")
            self.assertIsNone(supervisor.process)

    def test_invocation_contains_required_flags_and_no_bypass_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, supervisor, _ = self.make_supervisor(Path(directory), "success")
            argv = supervisor.invocation.argv()

            self.assertEqual(argv[1], "-p")
            self.assertIn("--session-id", argv)
            self.assertNotIn("--resume", argv)
            self.assertEqual(argv.count("--allowedTools"), 3)
            self.assertIn("mcp__codex_claude_runner__report_progress", argv)
            self.assertIn("stream-json", argv)
            self.assertIn("--verbose", argv)
            self.assertNotIn("--strict-mcp-config", argv)
            self.assertNotIn("--include-partial-messages", argv)
            self.assertNotIn("bypassPermissions", argv)
            self.assertIn(SESSION_ID, argv[-1])
            self.assertIn("mcp__codex_claude_runner__report_progress", argv[-1])
            self.assertIn("required progress channel", argv[-1])

    def test_success_preserves_stdout_and_records_structured_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(Path(directory), "success")

            code = supervisor.run()

            raw = (store.state_dir / "raw-events.jsonl").read_bytes()
            self.assertEqual(code, 0)
            self.assertTrue(raw.startswith(b'{"type":"system"'))
            self.assertIn(b'"structured_output"', raw)
            self.assertEqual(store.load().status, "implementation_complete")
            self.assertEqual(store.load().result["summary"], "fixture complete")
            self.assertEqual(store.load().segments[0]["status"], "complete")
            self.assertEqual(store.load().segments[0]["attempt"], 1)
            self.assertEqual(store.load().segments[0]["resume_count"], 0)
            self.assertEqual(store.load().runtime["result_history"][-1]["result"]["summary"], "fixture complete")
            self.assertTrue(any(event["kind"] == "process_exited" for event in events))

    def test_progress_tool_authorization_is_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, supervisor, _ = self.make_supervisor(Path(directory), "success")
            supervisor.invocation = replace(
                supervisor.invocation,
                allowed_tools=(
                    *supervisor.invocation.allowed_tools,
                    "mcp__codex_claude_runner__report_progress",
                ),
            )

            argv = supervisor.invocation.argv()

            self.assertEqual(argv.count("mcp__codex_claude_runner__report_progress"), 1)

    def test_unknown_tool_is_preserved_raw_but_not_surfaced_semantically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(Path(directory), "unknown-tool")

            self.assertEqual(supervisor.run(), 0)

            self.assertIn(b"do-not-surface", (store.state_dir / "raw-events.jsonl").read_bytes())
            self.assertNotIn("do-not-surface", json.dumps(events))

    def test_invalid_json_and_wrong_session_become_backend_failure(self) -> None:
        for scenario in ("invalid-json", "wrong-session", "invalid-result"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                store, supervisor, _ = self.make_supervisor(Path(directory), scenario)
                store.update(
                    lambda state: state.data.__setitem__(
                        "result", {"status": "DONE", "summary": "stale"}
                    )
                )

                self.assertNotEqual(supervisor.run(), 0)
                state = store.load()
                self.assertEqual(state.status, "backend_failure")
                self.assertIsNone(state.result)
                self.assertEqual(state.segments[0]["status"], "failed")

    def test_stderr_is_preserved_as_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, _ = self.make_supervisor(Path(directory), "stderr-bytes")

            self.assertEqual(supervisor.run(), 0)
            self.assertEqual((store.state_dir / "raw-stderr.log").read_bytes(), b"stderr:\xe4\xb8\xad:\xff\n")

    def test_timeout_observation_does_not_terminate_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(
                Path(directory), "model-idle", model_idle_seconds=0.03, heartbeat_seconds=0.02
            )

            self.assertEqual(supervisor.run(), 0)

            timeout_events = [event for event in events if event["kind"] == "timeout_suspected"]
            self.assertTrue(timeout_events)
            self.assertEqual(timeout_events[0]["clock"], "model")
            self.assertTrue(any(event["kind"] == "heartbeat" for event in events))
            self.assertEqual(store.load().status, "implementation_complete")

    def test_permission_hook_stop_is_not_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, _ = self.make_supervisor(Path(directory), "permission")

            self.assertNotEqual(supervisor.run(), 0)

            self.assertEqual(store.load().status, "permission_required")
            self.assertEqual(store.load().permissions["pending"]["tool_name"], "Bash")
            self.assertEqual(store.load().segments[0]["status"], "permission_required")

    def test_permission_denied_hook_stop_is_brokered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, _ = self.make_supervisor(Path(directory), "permission-denied")

            self.assertNotEqual(supervisor.run(), 0)

            state = store.load()
            self.assertEqual(state.status, "permission_required")
            self.assertEqual(state.segments[0]["status"], "permission_required")
            self.assertEqual(state.permissions["pending"]["tool_input"], {"command": "git status --short"})

    def test_stream_permission_denial_is_brokered_and_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(
                Path(directory),
                "stream-permission-denied",
                termination_grace_seconds=0.05,
            )
            supervisor.environment["FAKE_CLAUDE_DELAY"] = "5"

            started = time.monotonic()
            self.assertEqual(supervisor.run(), 3)
            elapsed = time.monotonic() - started

            state = store.load()
            denial = {
                "type": "system",
                "subtype": "permission_denied",
                "tool_name": "Bash",
                "tool_use_id": "toolu_denied",
                "decision_reason_type": "other",
                "decision_reason": "This command requires approval",
                "message": "This command requires approval",
                "session_id": SESSION_ID,
            }
            self.assertLess(elapsed, 2)
            self.assertEqual(state.status, "permission_required")
            self.assertEqual(state.segments[0]["status"], "permission_required")
            self.assertEqual(
                state.permissions["pending"],
                {
                    "segment_id": "segment-1",
                    "request": denial,
                    "tool_name": "Bash",
                    "tool_input": {"command": "git add .permission-probe"},
                    "received_at": state.permissions["pending"]["received_at"],
                },
            )
            self.assertNotIn("control_requested", state.runtime)
            self.assertNotIn("git add .permission-probe", json.dumps(events))
            self.assertTrue(any(event["kind"] == "permission_required" for event in events))

    def test_duplicate_tool_use_id_permission_denial_is_backend_failure_without_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(
                Path(directory),
                "duplicate-tool-use-id-permission-denied",
                termination_grace_seconds=0.05,
            )
            supervisor.environment["FAKE_CLAUDE_DELAY"] = "1"

            started = time.monotonic()
            self.assertNotEqual(supervisor.run(), 0)
            elapsed = time.monotonic() - started

            state = store.load()
            self.assertLess(elapsed, 0.5)
            self.assertEqual(state.status, "backend_failure")
            self.assertEqual(state.segments[0]["status"], "failed")
            self.assertIsNone(state.permissions["pending"])
            self.assertNotIn("control_requested", state.runtime)
            self.assertIn("duplicate tool_use_id", state.runtime["backend_failure"]["message"])
            self.assertNotIn("git add first.txt", json.dumps(events))
            self.assertNotIn("git add second.txt", json.dumps(events))

    def test_supervisor_refuses_dispatch_while_permission_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, _ = self.make_supervisor(Path(directory), "success")

            def add_pending(state: object) -> None:
                state.permissions["pending"] = {
                    "segment_id": "segment-1",
                    "request": {"tool_name": "Bash"},
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest --version"},
                    "received_at": "2026-08-06T00:00:00Z",
                }

            store.update(add_pending)

            with self.assertRaises(ContractError):
                supervisor.run()
            self.assertEqual(store.load().status, "initialized")

    def test_non_completion_structured_results_preserve_the_segment_for_resume(self) -> None:
        for scenario, expected_status in (
            ("needs-context", "interrupted"),
            ("blocked", "interrupted"),
            ("structured-permission", "permission_required"),
        ):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                store, supervisor, _ = self.make_supervisor(Path(directory), scenario)

                self.assertNotEqual(supervisor.run(), 0)

                state = store.load()
                self.assertEqual(state.status, expected_status)
                self.assertEqual(
                    state.segments[0]["status"],
                    "permission_required" if expected_status == "permission_required" else "interrupted",
                )
                self.assertEqual(state.result["status"], {
                    "needs-context": "NEEDS_CONTEXT",
                    "blocked": "BLOCKED",
                    "structured-permission": "PERMISSION_REQUIRED",
                }[scenario])
                if scenario == "structured-permission":
                    self.assertEqual(state.permissions["pending"]["tool_name"], "Bash")

    def test_public_interrupt_records_an_interrupted_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(
                Path(directory), "model-idle", heartbeat_seconds=0.02
            )

            def request_interrupt(event: dict[str, object]) -> None:
                events.append(event)
                if event["kind"] == "heartbeat":
                    supervisor.interrupt()

            supervisor.event_sink = request_interrupt

            self.assertNotEqual(supervisor.run(), 0)
            self.assertEqual(store.load().status, "interrupted")
            self.assertEqual(store.load().segments[0]["status"], "interrupted")

    def test_interrupt_escalates_twice_for_unresponsive_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(
                Path(directory),
                "ignore-interrupt-and-term",
                termination_grace_seconds=0.05,
            )
            supervisor.environment["FAKE_CLAUDE_DELAY"] = "5"

            def request_interrupt(event: dict[str, object]) -> None:
                events.append(event)
                if event["kind"] == "tool_started":
                    supervisor.interrupt()

            supervisor.event_sink = request_interrupt

            started = time.monotonic()
            self.assertNotEqual(supervisor.run(), 0)
            elapsed = time.monotonic() - started

            state = store.load()
            self.assertLess(elapsed, 2)
            self.assertEqual(state.status, "interrupted")
            self.assertEqual(state.segments[0]["status"], "interrupted")
            self.assertEqual(
                [item["stage"] for item in state.runtime["control_requested"]["stages"]],
                ["interrupt", "terminate", "kill"],
            )

    def test_process_exit_during_stage_persistence_finishes_interrupt(self) -> None:
        class ExitingDuringStagePersistenceSupervisor(Supervisor):
            def _record_control_stage(self, stage: str) -> None:
                if stage == "terminate":
                    assert self.process is not None
                    self.process.kill()
                    self.process.wait(timeout=1)
                super()._record_control_stage(stage)

        with tempfile.TemporaryDirectory() as directory:
            store, original, events = self.make_supervisor(
                Path(directory),
                "ignore-interrupt-and-term",
            )
            supervisor = ExitingDuringStagePersistenceSupervisor(
                store,
                original.invocation,
                environment=original.environment,
                termination_grace_seconds=0.02,
            )

            def request_interrupt(event: dict[str, object]) -> None:
                events.append(event)
                if event["kind"] == "tool_started":
                    supervisor.interrupt()

            supervisor.event_sink = request_interrupt

            try:
                result = supervisor.run()
            except (ProcessLookupError, RuntimeError) as exc:
                self.fail(f"process disappearance escaped interrupt finalization: {exc}")

            state = store.load()
            self.assertNotEqual(result, 0)
            self.assertEqual(state.status, "interrupted")
            self.assertEqual(state.segments[0]["status"], "interrupted")
            self.assertIsNone(supervisor.process)

    def test_interrupt_grace_deadline_starts_after_signal(self) -> None:
        class SlowPersistenceSupervisor(Supervisor):
            def __init__(self, *args: object, **kwargs: object):
                super().__init__(*args, **kwargs)
                self.signal_times: list[tuple[signal.Signals, float]] = []

            def _record_control_request(self, action: str, stage: str) -> None:
                super()._record_control_request(action, stage)
                time.sleep(0.08)

            def _signal(self, sig: signal.Signals) -> None:
                self.signal_times.append((sig, time.monotonic()))
                super()._signal(sig)

        with tempfile.TemporaryDirectory() as directory:
            store, original, events = self.make_supervisor(
                Path(directory),
                "ignore-interrupt-and-term",
            )
            original.environment["FAKE_CLAUDE_DELAY"] = "5"
            supervisor = SlowPersistenceSupervisor(
                store,
                original.invocation,
                environment=original.environment,
                termination_grace_seconds=0.05,
            )

            def request_interrupt(event: dict[str, object]) -> None:
                events.append(event)
                if event["kind"] == "tool_started":
                    supervisor.interrupt()

            supervisor.event_sink = request_interrupt

            self.assertNotEqual(supervisor.run(), 0)

            self.assertEqual(
                [sig for sig, _ in supervisor.signal_times],
                [signal.SIGINT, signal.SIGTERM, signal.SIGKILL],
            )
            interrupt_at = supervisor.signal_times[0][1]
            terminate_at = supervisor.signal_times[1][1]
            self.assertGreaterEqual(terminate_at - interrupt_at, 0.045)

    def test_explicit_terminate_escalates_after_grace_without_pid_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(
                Path(directory), "ignore-term", termination_grace_seconds=0.05
            )

            def request_terminate(event: dict[str, object]) -> None:
                events.append(event)
                if event["kind"] == "tool_started":
                    supervisor.terminate()

            supervisor.event_sink = request_terminate

            started = time.monotonic()
            self.assertNotEqual(supervisor.run(), 0)

            self.assertGreaterEqual(time.monotonic() - started, 0.04)
            self.assertEqual(store.load().status, "interrupted")
            self.assertEqual(store.load().segments[0]["status"], "interrupted")
            self.assertTrue(any(event["kind"] == "interrupted" for event in events))


if __name__ == "__main__":
    unittest.main()
