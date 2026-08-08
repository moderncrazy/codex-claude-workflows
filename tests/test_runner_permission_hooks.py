from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


RUNNER_ROOT = Path(__file__).parents[1] / "shared" / "claude-runner"
sys.path.insert(0, str(RUNNER_ROOT))

from runner.permission_hooks import (  # noqa: E402
    build_hook_settings,
    handle_permission_denied,
    handle_permission_request,
)
from runner.state_store import StateStore  # noqa: E402
from tests.test_runner_state import sample_work_unit  # noqa: E402


class PermissionHookTests(unittest.TestCase):
    def running_store(self, root: Path) -> StateStore:
        state = sample_work_unit(root)
        state.transition_to("running")
        state.segments[0]["status"] = "running"
        state.segments[0]["session_id"] = "2b30da4c-4a0b-4d77-a5d9-75c785218daf"
        return StateStore.create(state)

    def test_permission_request_is_recorded_verbatim_then_interrupts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.running_store(Path(directory))
            request = {
                "session_id": "2b30da4c-4a0b-4d77-a5d9-75c785218daf",
                "cwd": "/repo",
                "hook_event_name": "PermissionRequest",
                "tool_name": "mcp__codegraph__explore",
                "tool_input": {"query": "find callers"},
            }
            output = io.StringIO()

            code = handle_permission_request(store.state_dir, io.StringIO(json.dumps(request)), output)

            self.assertEqual(code, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["decision"]["behavior"], "deny")
            self.assertTrue(result["decision"]["interrupt"])
            pending = store.load().permissions["pending"]
            self.assertEqual(pending["request"], request)
            self.assertEqual(pending["tool_input"], {"query": "find callers"})
            self.assertEqual(pending["segment_id"], "segment-1")

    def test_second_permission_cannot_overwrite_pending_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.running_store(Path(directory))
            first = {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "pytest"}}
            second = {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "git push"}}
            handle_permission_request(store.state_dir, io.StringIO(json.dumps(first)), io.StringIO())

            output = io.StringIO()
            code = handle_permission_request(store.state_dir, io.StringIO(json.dumps(second)), output)

            self.assertNotEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())["continue"])
            self.assertEqual(store.load().permissions["pending"]["request"], first)

    def test_permission_denied_is_recorded_verbatim_then_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.running_store(Path(directory))
            request = {
                "session_id": "2b30da4c-4a0b-4d77-a5d9-75c785218daf",
                "cwd": "/repo",
                "hook_event_name": "PermissionDenied",
                "tool_name": "Bash",
                "tool_input": {"command": "git status --short"},
            }
            denied = io.StringIO()

            self.assertEqual(
                handle_permission_denied(
                    store.state_dir,
                    io.StringIO(json.dumps(request)),
                    denied,
                ),
                0,
            )
            self.assertEqual(
                json.loads(denied.getvalue()),
                {
                    "continue": False,
                    "stopReason": "Claude Code permission was denied; execution is stopped for Codex review",
                    "suppressOutput": True,
                },
            )
            pending = store.load().permissions["pending"]
            self.assertEqual(pending["segment_id"], "segment-1")
            self.assertEqual(pending["request"], request)
            self.assertEqual(pending["tool_name"], "Bash")
            self.assertEqual(pending["tool_input"], {"command": "git status --short"})

    def test_second_permission_denial_cannot_overwrite_pending_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.running_store(Path(directory))
            first = {"hook_event_name": "PermissionDenied", "tool_name": "Bash", "tool_input": {"command": "git status --short"}}
            second = {"hook_event_name": "PermissionDenied", "tool_name": "Bash", "tool_input": {"command": "git push"}}
            handle_permission_denied(store.state_dir, io.StringIO(json.dumps(first)), io.StringIO())

            output = io.StringIO()
            code = handle_permission_denied(store.state_dir, io.StringIO(json.dumps(second)), output)

            self.assertNotEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())["continue"])
            self.assertEqual(store.load().permissions["pending"]["request"], first)

    def test_permission_denied_without_one_running_segment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            output = io.StringIO()

            code = handle_permission_denied(
                store.state_dir,
                io.StringIO(json.dumps({"hook_event_name": "PermissionDenied", "tool_name": "Bash"})),
                output,
            )

            self.assertNotEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())["continue"])
            self.assertIsNone(store.load().permissions["pending"])

    def test_malformed_permission_request_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            malformed = io.StringIO()

            self.assertNotEqual(handle_permission_request(store.state_dir, io.StringIO("nope"), malformed), 0)
            self.assertFalse(json.loads(malformed.getvalue())["continue"])

    def test_permission_request_without_one_running_segment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            output = io.StringIO()

            code = handle_permission_request(
                store.state_dir,
                io.StringIO(json.dumps({"hook_event_name": "PermissionRequest", "tool_name": "Bash"})),
                output,
            )

            self.assertNotEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())["continue"])
            self.assertIsNone(store.load().permissions["pending"])

    def test_settings_are_inline_and_target_only_two_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            settings = build_hook_settings(store.state_dir, Path(sys.executable), RUNNER_ROOT / "claude_runner.py")

            self.assertEqual(set(settings["hooks"]), {"PermissionRequest", "PermissionDenied"})
            serialized = json.dumps(settings)
            self.assertIn(str(store.state_dir), serialized)
            self.assertNotIn("PreToolUse", serialized)


if __name__ == "__main__":
    unittest.main()
