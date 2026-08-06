from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path


RUNNER_ROOT = Path(__file__).parents[1] / "shared" / "claude-runner"
sys.path.insert(0, str(RUNNER_ROOT))

from runner.contracts import InvalidTransition, WorkUnitState  # noqa: E402
from runner.state_store import StateStore  # noqa: E402


WORK_UNIT_ID = "8c606b8c-89c3-457a-a4bc-754b7513fb2c"


def sample_work_unit(root: Path) -> WorkUnitState:
    return WorkUnitState.from_dict(
        {
            "schema_version": 1,
            "work_unit_id": WORK_UNIT_ID,
            "workflow": "superpowers",
            "native_ref": "Task 1",
            "working_root": str(root.resolve()),
            "fixed_point": "abc123",
            "executor": {"agent": "claude-code", "capability": "sonnet"},
            "status": "initialized",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "kind": "implementation",
                    "scope": "Implement the fixture",
                    "verification_commands": ["python3 -m unittest"],
                    "status": "pending",
                    "session_id": None,
                    "attempt": 0,
                    "created_at": "2026-08-06T00:00:00Z",
                    "started_at": None,
                    "finished_at": None,
                }
            ],
            "permissions": {"initial": [], "approved": [], "pending": None},
            "runtime": {},
            "progress_claims": [],
            "evidence": {"declared": [], "verified": []},
            "commits": [],
            "result": None,
        }
    )


def record_claim(state_dir: str, number: int) -> None:
    store = StateStore(Path(state_dir))
    store.record_progress_claim(
        {
            "kind": "segment_started",
            "message": f"claim-{number}",
            "next_action": "continue",
            "evidence_refs": [],
        },
        raw_event_offset=number,
    )


class StateStoreTests(unittest.TestCase):
    def test_progress_claim_is_stored_verbatim_with_runner_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            claim = {
                "kind": "segment_completed",
                "message": "exact claude text",
                "next_action": "run focused tests",
                "evidence_refs": ["toolu_123"],
            }

            receipt = store.record_progress_claim(claim, raw_event_offset=41)

            self.assertEqual(receipt.claim, claim)
            self.assertEqual(receipt.sequence, 1)
            self.assertEqual(receipt.raw_event_offset, 41)
            self.assertEqual(store.load().progress_claims[0]["claim"], claim)

    def test_native_completion_cannot_be_written_to_adapter_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))

            with self.assertRaises(InvalidTransition):
                store.update_fields({"native_ticket_status": "done"})

    def test_append_raw_preserves_exact_bytes_and_returns_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            first = b'{"text":"\xe4\xb8\xad"}\n'
            second = b"\xff\x00tail"

            self.assertEqual(store.append_raw("stdout", first), 0)
            self.assertEqual(store.append_raw("stdout", second), len(first))
            self.assertEqual((store.state_dir / "raw-events.jsonl").read_bytes(), first + second)

    def test_concurrent_receipts_are_monotonic_without_lost_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            processes = [
                multiprocessing.Process(target=record_claim, args=(str(store.state_dir), number))
                for number in range(12)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)

            serialized = json.loads((store.state_dir / "work-unit.json").read_text())
            sequences = [receipt["sequence"] for receipt in serialized["progress_claims"]]
            self.assertEqual(sequences, list(range(1, 13)))


if __name__ == "__main__":
    unittest.main()
