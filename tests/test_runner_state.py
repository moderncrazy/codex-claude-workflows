from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path


RUNNER_ROOT = Path(__file__).parents[1] / "shared" / "claude-runner"
sys.path.insert(0, str(RUNNER_ROOT))

from runner.contracts import ContractError, InvalidTransition, WorkUnitState, upgrade_state_dict  # noqa: E402
from runner.state_store import StateStore  # noqa: E402


WORK_UNIT_ID = "8c606b8c-89c3-457a-a4bc-754b7513fb2c"


def sample_work_unit(root: Path) -> WorkUnitState:
    return WorkUnitState.from_dict(
        {
            "schema_version": 2,
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
                    "resume_count": 0,
                    "created_at": "2026-08-06T00:00:00Z",
                    "started_at": None,
                    "finished_at": None,
                }
            ],
            "permissions": {"initial": [], "approved": [], "pending": None, "resolved": []},
            "runtime": {"result_history": []},
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
    def test_schema_version_one_is_migrated_before_validation(self) -> None:
        legacy = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        legacy["schema_version"] = 1
        legacy["permissions"].pop("resolved")
        legacy["segments"][0].pop("resume_count")
        legacy["segments"][0]["session_id"] = "37af868d-e830-42ca-94dd-a5523d30f616"
        legacy["segments"][0]["attempt"] = 0
        legacy["runtime"].pop("result_history")

        migrated = upgrade_state_dict(legacy)

        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["segments"][0]["attempt"], 1)
        self.assertEqual(migrated["segments"][0]["resume_count"], 0)
        self.assertEqual(migrated["permissions"]["resolved"], [])
        self.assertEqual(migrated["runtime"]["result_history"], [])

    def test_legacy_timeout_is_migrated_to_running_observation_state(self) -> None:
        legacy = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        legacy["schema_version"] = 1
        legacy["status"] = "timeout_suspected"
        legacy["permissions"].pop("resolved")
        legacy["segments"][0].pop("resume_count")

        self.assertEqual(upgrade_state_dict(legacy)["status"], "running")

    def test_legacy_pending_permission_is_attributed_to_unique_segment(self) -> None:
        legacy = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        legacy["schema_version"] = 1
        legacy["status"] = "permission_required"
        legacy["permissions"].pop("resolved")
        legacy["permissions"]["pending"] = {
            "request": {"tool_name": "Bash"},
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "received_at": "2026-08-06T00:00:00Z",
        }
        legacy["segments"][0].pop("resume_count")
        legacy["segments"][0]["status"] = "permission_required"

        migrated = upgrade_state_dict(legacy)

        self.assertEqual(migrated["permissions"]["pending"]["segment_id"], "segment-1")

    def test_legacy_pending_permission_without_unique_segment_is_rejected(self) -> None:
        legacy = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        legacy["schema_version"] = 1
        legacy["status"] = "permission_required"
        legacy["permissions"].pop("resolved")
        legacy["permissions"]["pending"] = {
            "request": {"tool_name": "Bash"},
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "received_at": "2026-08-06T00:00:00Z",
        }
        legacy["segments"][0].pop("resume_count")

        with self.assertRaises(ContractError):
            upgrade_state_dict(legacy)

    def test_state_store_loads_legacy_state_as_version_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            legacy = store.load().to_dict()
            legacy["schema_version"] = 1
            legacy["permissions"].pop("resolved")
            legacy["segments"][0].pop("resume_count")
            store.state_path.write_text(json.dumps(legacy), encoding="utf-8")

            loaded = store.load()

            self.assertEqual(loaded.schema_version, 2)
            self.assertEqual(loaded.segments[0]["resume_count"], 0)

    def test_version_two_rejects_removed_lifecycle_statuses(self) -> None:
        for status in ("timeout_suspected", "cleaned"):
            with self.subTest(status=status):
                state = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
                state["status"] = status

                with self.assertRaises(ContractError):
                    WorkUnitState.from_dict(state)

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

    def test_stale_lock_file_does_not_block_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            store.lock_path.write_text("dead-owner\n", encoding="utf-8")

            state = store.update_fields({"native_ref": "recovered"})

            self.assertEqual(state.native_ref, "recovered")

    def test_nested_contract_errors_are_reported_as_contract_errors(self) -> None:
        state = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        state["executor"] = "not-an-object"

        with self.assertRaises(ContractError):
            WorkUnitState.from_dict(state)

        state = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        state["segments"][0]["invented"] = True
        with self.assertRaises(ContractError):
            WorkUnitState.from_dict(state)

        state = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        state["status"] = "invented"
        with self.assertRaises(ContractError):
            WorkUnitState.from_dict(state)

        state = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
        state["segments"][0]["status"] = "invented"
        with self.assertRaises(ContractError):
            WorkUnitState.from_dict(state)


if __name__ == "__main__":
    unittest.main()
