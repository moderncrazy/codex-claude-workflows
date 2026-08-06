from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


RUNNER_ROOT = Path(__file__).parents[1] / "shared" / "claude-runner"
FIXTURE = Path(__file__).parent / "fixtures" / "fake_claude.py"
RESULT_SCHEMA = Path(__file__).parents[1] / "skills" / "superpowers-claude-workflow" / "references" / "claude-result.schema.json"
sys.path.insert(0, str(RUNNER_ROOT))

from runner.permission_hooks import build_hook_settings  # noqa: E402
from runner.state_store import StateStore  # noqa: E402
from runner.supervisor import ClaudeInvocation, Supervisor  # noqa: E402
from tests.test_runner_state import sample_work_unit  # noqa: E402


SESSION_ID = "0c2fb298-155f-4af0-bc6f-35e229fd27f3"


class SupervisorTests(unittest.TestCase):
    def make_supervisor(self, root: Path, scenario: str, **thresholds: float) -> tuple[StateStore, Supervisor, list[dict[str, object]]]:
        state = sample_work_unit(root)
        state.segments[0]["session_id"] = SESSION_ID
        store = StateStore.create(state)
        settings = build_hook_settings(store.state_dir, Path(sys.executable), RUNNER_ROOT / "claude_runner.py")
        invocation = ClaudeInvocation(
            executable=FIXTURE,
            working_root=root,
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

    def test_invocation_contains_required_flags_and_no_bypass_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, supervisor, _ = self.make_supervisor(Path(directory), "success")
            argv = supervisor.invocation.argv()

            self.assertEqual(argv[1], "-p")
            self.assertIn("--session-id", argv)
            self.assertNotIn("--resume", argv)
            self.assertEqual(argv.count("--allowedTools"), 2)
            self.assertIn("stream-json", argv)
            self.assertNotIn("--strict-mcp-config", argv)
            self.assertNotIn("--include-partial-messages", argv)
            self.assertNotIn("bypassPermissions", argv)

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
            self.assertTrue(any(event["kind"] == "process_exited" for event in events))

    def test_unknown_tool_is_preserved_raw_but_not_surfaced_semantically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(Path(directory), "unknown-tool")

            self.assertEqual(supervisor.run(), 0)

            self.assertIn(b"do-not-surface", (store.state_dir / "raw-events.jsonl").read_bytes())
            self.assertNotIn("do-not-surface", json.dumps(events))

    def test_invalid_json_and_wrong_session_become_backend_failure(self) -> None:
        for scenario in ("invalid-json", "wrong-session"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                store, supervisor, _ = self.make_supervisor(Path(directory), scenario)

                self.assertNotEqual(supervisor.run(), 0)
                self.assertEqual(store.load().status, "backend_failure")

    def test_stderr_is_preserved_as_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, _ = self.make_supervisor(Path(directory), "stderr-bytes")

            self.assertEqual(supervisor.run(), 0)
            self.assertEqual((store.state_dir / "raw-stderr.log").read_bytes(), b"stderr:\xe4\xb8\xad:\xff\n")

    def test_timeout_observation_does_not_terminate_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, events = self.make_supervisor(Path(directory), "model-idle", model_idle_seconds=0.03)

            self.assertEqual(supervisor.run(), 0)

            timeout_events = [event for event in events if event["kind"] == "timeout_suspected"]
            self.assertTrue(timeout_events)
            self.assertEqual(timeout_events[0]["clock"], "model")
            self.assertEqual(store.load().status, "implementation_complete")

    def test_permission_hook_stop_is_not_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, supervisor, _ = self.make_supervisor(Path(directory), "permission")

            self.assertNotEqual(supervisor.run(), 0)

            self.assertEqual(store.load().status, "permission_required")
            self.assertEqual(store.load().permissions["pending"]["tool_name"], "Bash")


if __name__ == "__main__":
    unittest.main()
