from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
FAKE_CLAUDE = Path(__file__).parent / "fixtures/fake_claude.py"


class NativeShapedWorkflowTests(unittest.TestCase):
    def make_repo(self, directory: str) -> Path:
        root = Path(directory).resolve()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.com"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
        (root / ".gitignore").write_text("/.tmp/\n", encoding="utf-8")
        (root / "native-state.txt").write_text("owned by native workflow\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "native baseline"], check=True)
        return root

    def call(
        self,
        entrypoint: Path,
        *arguments: str,
        scenario: str | None = None,
        expected: int = 0,
    ) -> dict[str, object]:
        environment = dict(os.environ)
        if scenario:
            environment["FAKE_CLAUDE_SCENARIO"] = scenario
        completed = subprocess.run(
            [sys.executable, str(entrypoint), *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, expected, completed.stderr + completed.stdout)
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def init(
        self,
        skill: str,
        root: Path,
        workflow: str,
        native_ref: str,
        work_unit_id: str,
        segment_count: int,
    ) -> tuple[Path, Path]:
        skill_root = ROOT / "skills" / skill
        entrypoint = skill_root / "scripts/claude-runner/claude_runner.py"
        schema = skill_root / "references/claude-result.schema.json"
        segments = [
            {
                "segment_id": f"segment-{index}",
                "kind": "implementation",
                "scope": f"Checkpoint {index}",
                "verification_commands": [f"verify checkpoint {index}"],
            }
            for index in range(1, segment_count + 1)
        ]
        result = self.call(
            entrypoint,
            "init",
            "--working-root",
            str(root),
            "--workflow",
            workflow,
            "--native-ref",
            native_ref,
            "--fixed-point",
            "HEAD",
            "--capability",
            "sonnet",
            "--result-schema",
            str(schema),
            "--claude-executable",
            str(FAKE_CLAUDE),
            "--prompt",
            "Implement the same tiny requirement",
            "--allowed-tool",
            "Bash(python3 -m unittest *)",
            "--segments-json",
            json.dumps(segments),
            "--work-unit-id",
            work_unit_id,
        )
        return entrypoint, Path(result["state_dir"])

    def verify_finish_cleanup(self, entrypoint: Path, state_dir: Path, root: Path) -> None:
        finished = self.call(
            entrypoint,
            "finish",
            "--state-dir",
            str(state_dir),
            "--native-workflow-complete",
        )
        self.assertEqual(finished["status"], "finished")
        sibling = state_dir.parent / "must-survive"
        sibling.mkdir()
        self.call(entrypoint, "cleanup", "--state-dir", str(state_dir))
        self.assertFalse(state_dir.exists())
        self.assertTrue(sibling.exists())
        self.assertEqual((root / "native-state.txt").read_text(), "owned by native workflow\n")

    def test_superpowers_path_preserves_native_state_across_permission_and_segments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            entrypoint, state_dir = self.init(
                "superpowers-claude-workflow",
                root,
                "superpowers",
                "Plan Task 1",
                "b815deda-05ee-4cc8-9305-f35cab882305",
                2,
            )

            stopped = self.call(entrypoint, "run", "--state-dir", str(state_dir), scenario="permission", expected=3)
            self.assertEqual(stopped["status"], "permission_required")
            self.call(
                entrypoint,
                "approve-permission",
                "--state-dir",
                str(state_dir),
                "--expected-tool-name",
                "Bash",
                "--allow-rule",
                "Bash(pytest --version)",
            )
            first = self.call(entrypoint, "resume", "--state-dir", str(state_dir), scenario="success")
            self.assertEqual(first["status"], "running")
            second = self.call(entrypoint, "run", "--state-dir", str(state_dir), scenario="success")
            self.assertEqual(second["status"], "implementation_complete")
            self.assertEqual([segment["attempt"] for segment in second["segments"]], [1, 1])
            self.assertEqual([segment["resume_count"] for segment in second["segments"]], [1, 0])
            self.assertNotEqual(second["segments"][0]["session_id"], second["segments"][1]["session_id"])
            self.verify_finish_cleanup(entrypoint, state_dir, root)

    def test_matt_review_finding_uses_repair_segment_without_tracker_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            entrypoint, state_dir = self.init(
                "matt-claude-workflow",
                root,
                "matt",
                "implicit-task",
                "cdd7076f-4b9f-493e-81c1-bd94390299f6",
                1,
            )

            initial = self.call(entrypoint, "run", "--state-dir", str(state_dir), scenario="success")
            self.assertEqual(initial["status"], "implementation_complete")
            resumed = self.call(
                entrypoint,
                "resume",
                "--state-dir",
                str(state_dir),
                "--segment-id",
                "segment-1",
                scenario="success",
            )
            self.assertEqual(resumed["status"], "implementation_complete")
            repair = self.call(
                entrypoint,
                "add-repair-segment",
                "--state-dir",
                str(state_dir),
                "--scope",
                "Fix cross-segment review finding",
                "--finding-id",
                "SPEC-3",
                "--verification-command",
                "python3 -m unittest",
                "--capability",
                "opus",
            )
            self.assertEqual(repair["status"], "running")
            self.assertEqual(repair["segments"][-1]["finding_ids"], ["SPEC-3"])
            completed = self.call(entrypoint, "run", "--state-dir", str(state_dir), scenario="success")
            self.assertEqual(completed["status"], "implementation_complete")
            persisted = json.loads((state_dir / "work-unit.json").read_text())
            self.assertEqual(persisted["runtime"]["last_invocation_capability"], "opus")
            self.verify_finish_cleanup(entrypoint, state_dir, root)

    def test_corrupt_state_is_preserved_and_cleanup_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            entrypoint, state_dir = self.init(
                "superpowers-claude-workflow",
                root,
                "superpowers",
                "Plan Task 2",
                "d205e467-f1db-4637-a3df-eb19d25587fd",
                1,
            )
            state_path = state_dir / "work-unit.json"
            state_path.write_text("{broken", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(entrypoint), "cleanup", "--state-dir", str(state_dir), "--native-workflow-complete"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue(state_dir.exists())
            self.assertEqual(state_path.read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
