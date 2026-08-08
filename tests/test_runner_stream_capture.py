from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


RUNNER_ROOT = Path(__file__).parents[1] / "shared" / "claude-runner"
sys.path.insert(0, str(RUNNER_ROOT))

from runner.stream_capture import StreamObservation, StreamProtocolError  # noqa: E402


SESSION_ID = "0c2fb298-155f-4af0-bc6f-35e229fd27f3"


class StreamObservationTests(unittest.TestCase):
    def tool_use_event(
        self,
        *,
        tool_name: str = "Bash",
        command: str = "git add .permission-probe",
    ) -> dict[str, object]:
        return {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_denied",
                        "name": tool_name,
                        "input": {"command": command},
                    }
                ]
            },
            "session_id": SESSION_ID,
        }

    def denial_event(
        self,
        *,
        tool_use_id: str = "toolu_denied",
        tool_name: str = "Bash",
    ) -> dict[str, object]:
        return {
            "type": "system",
            "subtype": "permission_denied",
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "decision_reason_type": "other",
            "decision_reason": "This command requires approval",
            "message": "This command requires approval",
            "session_id": SESSION_ID,
        }

    def observe(self, observation: StreamObservation, event: dict[str, object]) -> None:
        observation.observe_line(json.dumps(event).encode() + b"\n", 1.0)

    def test_permission_denial_correlates_verbatim_event_and_complete_tool_call(self) -> None:
        observation = StreamObservation()
        self.observe(observation, self.tool_use_event())
        denial = self.denial_event()

        self.observe(observation, denial)

        self.assertEqual(
            observation.permission_denial,
            {
                "request": denial,
                "tool_name": "Bash",
                "tool_input": {"command": "git add .permission-probe"},
            },
        )

    def test_permission_denial_with_unknown_tool_use_id_fails_closed(self) -> None:
        observation = StreamObservation()
        self.observe(observation, self.tool_use_event())

        with self.assertRaises(StreamProtocolError):
            self.observe(observation, self.denial_event(tool_use_id="toolu_unknown"))

    def test_permission_denial_with_mismatched_tool_name_fails_closed(self) -> None:
        observation = StreamObservation()
        self.observe(observation, self.tool_use_event())

        with self.assertRaises(StreamProtocolError):
            self.observe(observation, self.denial_event(tool_name="Write"))

    def test_duplicate_tool_use_id_with_different_input_fails_closed(self) -> None:
        observation = StreamObservation()
        self.observe(observation, self.tool_use_event(command="git add first.txt"))

        with self.assertRaisesRegex(StreamProtocolError, "duplicate tool_use_id"):
            self.observe(observation, self.tool_use_event(command="git add second.txt"))

        self.assertIsNone(observation.permission_denial)


if __name__ == "__main__":
    unittest.main()
