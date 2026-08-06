from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
RUNNER_ROOT = REPO_ROOT / "shared" / "claude-runner"
ENTRYPOINT = RUNNER_ROOT / "claude_runner.py"
FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
RESULT_SCHEMA = REPO_ROOT / "skills" / "superpowers-claude-workflow" / "references" / "claude-result.schema.json"


class RunnerCliTests(unittest.TestCase):
    def test_default_claude_executable_remains_path_resolvable(self) -> None:
        sys.path.insert(0, str(RUNNER_ROOT))
        from runner.cli import _executable_value

        self.assertEqual(_executable_value(Path("claude")), "claude")

    def make_repo(self, directory: str, *, ignored: bool = True) -> Path:
        root = Path(directory).resolve()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.com"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
        if ignored:
            (root / ".gitignore").write_text("/.tmp/\n", encoding="utf-8")
        else:
            (root / ".gitignore").write_text("", encoding="utf-8")
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        return root

    def run_cli(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
        expected: int = 0,
    ) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, str(ENTRYPOINT), *arguments],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, expected, completed.stderr + completed.stdout)
        self.assertTrue(completed.stdout.strip(), completed.stderr)
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def init_work_unit(self, root: Path, work_unit_id: str) -> Path:
        segments = [
            {
                "segment_id": "segment-1",
                "kind": "implementation",
                "scope": "Implement fixture",
                "verification_commands": ["python3 -m unittest"],
            }
        ]
        result = self.run_cli(
            "init",
            "--working-root",
            str(root),
            "--workflow",
            "superpowers",
            "--native-ref",
            "Task 1",
            "--fixed-point",
            "HEAD",
            "--capability",
            "sonnet",
            "--result-schema",
            str(RESULT_SCHEMA),
            "--claude-executable",
            str(FAKE_CLAUDE),
            "--prompt",
            "Implement fixture",
            "--allowed-tool",
            "Bash(python3 -m unittest *)",
            "--segments-json",
            json.dumps(segments),
            "--work-unit-id",
            work_unit_id,
        )
        self.assertEqual(result["status"], "initialized")
        return Path(result["state_dir"])

    def test_init_rejects_repository_without_tmp_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory, ignored=False)

            result = self.run_cli(
                "init",
                "--working-root",
                str(root),
                "--workflow",
                "matt",
                "--native-ref",
                "implicit-task",
                "--fixed-point",
                "HEAD",
                "--capability",
                "sonnet",
                "--result-schema",
                str(RESULT_SCHEMA),
                "--claude-executable",
                str(FAKE_CLAUDE),
                "--prompt",
                "Implement fixture",
                "--segments-json",
                json.dumps([{"segment_id": "s", "kind": "implementation", "scope": "x", "verification_commands": []}]),
                expected=2,
            )

            self.assertEqual(result["error"], "tmp_not_ignored")
            self.assertFalse((root / ".tmp").exists())

    def test_success_lifecycle_requires_verification_and_native_cleanup_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "63b4821f-15b1-474c-9664-d9d272cc05ad")
            environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="success")

            result = self.run_cli("run", "--state-dir", str(state_dir), environment=environment)
            self.assertEqual(result["status"], "implementation_complete")
            status = self.run_cli("status", "--state-dir", str(state_dir))
            self.assertEqual(status["result"]["summary"], "fixture complete")
            rejected = self.run_cli("cleanup", "--state-dir", str(state_dir), expected=2)
            self.assertEqual(rejected["error"], "native_completion_required")
            unfinished = self.run_cli("finish", "--state-dir", str(state_dir), expected=2)
            self.assertEqual(unfinished["error"], "verification_required")

            self.run_cli(
                "record-verification",
                "--state-dir",
                str(state_dir),
                "--command",
                "python3 -m unittest",
                "--exit-code",
                "0",
                "--evidence-ref",
                "raw-events.jsonl#2",
            )
            finished = self.run_cli("finish", "--state-dir", str(state_dir))
            self.assertEqual(finished["status"], "implementation_complete")
            cleaned = self.run_cli(
                "cleanup",
                "--state-dir",
                str(state_dir),
                "--native-workflow-complete",
            )
            self.assertEqual(cleaned["status"], "cleaned")
            self.assertFalse(state_dir.exists())

    def test_permission_can_be_narrowly_approved_then_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "7d088ab3-7654-401c-bbac-a2e6933091db")
            permission_environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="permission")

            stopped = self.run_cli("run", "--state-dir", str(state_dir), environment=permission_environment, expected=3)
            self.assertEqual(stopped["status"], "permission_required")
            approved = self.run_cli(
                "approve-permission",
                "--state-dir",
                str(state_dir),
                "--expected-tool-name",
                "Bash",
                "--allow-rule",
                "Bash(pytest --version)",
            )
            self.assertEqual(approved["status"], "running")
            success_environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="success")
            resumed = self.run_cli("resume", "--state-dir", str(state_dir), environment=success_environment)
            self.assertEqual(resumed["status"], "implementation_complete")


if __name__ == "__main__":
    unittest.main()
