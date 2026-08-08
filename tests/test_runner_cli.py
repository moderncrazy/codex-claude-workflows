from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
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

    def test_success_lifecycle_requires_explicit_native_finish_before_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "63b4821f-15b1-474c-9664-d9d272cc05ad")
            environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="success")

            result = self.run_cli("run", "--state-dir", str(state_dir), environment=environment)
            self.assertEqual(result["status"], "implementation_complete")
            status = self.run_cli("status", "--state-dir", str(state_dir))
            self.assertEqual(status["result"]["summary"], "fixture complete")
            waited = subprocess.run(
                [
                    sys.executable,
                    str(ENTRYPOINT),
                    "wait",
                    "--state-dir",
                    str(state_dir),
                    "--after-sequence",
                    "0",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(waited.returncode, 0, waited.stderr)
            wait_lines = [json.loads(line) for line in waited.stdout.splitlines()]
            self.assertTrue(any(line.get("kind") == "process_exited" for line in wait_lines))
            self.assertEqual(wait_lines[-1]["status"], "implementation_complete")
            rejected = self.run_cli("cleanup", "--state-dir", str(state_dir), expected=2)
            self.assertEqual(rejected["error"], "finish_required")
            legacy_bypass = self.run_cli(
                "cleanup",
                "--state-dir",
                str(state_dir),
                "--native-workflow-complete",
                expected=2,
            )
            self.assertEqual(legacy_bypass["error"], "finish_required")
            missing_assertion = self.run_cli("finish", "--state-dir", str(state_dir), expected=2)
            self.assertEqual(missing_assertion["error"], "native_completion_required")
            finished = self.run_cli(
                "finish",
                "--state-dir",
                str(state_dir),
                "--native-workflow-complete",
            )
            self.assertEqual(finished["status"], "finished")
            cleaned = self.run_cli("cleanup", "--state-dir", str(state_dir))
            self.assertEqual(cleaned["status"], "cleaned")
            self.assertFalse(state_dir.exists())

    def test_finish_rejects_incomplete_or_permission_blocked_work_unit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "e3b1f7af-d473-4b5a-ac77-fd43b4f1eb31")

            incomplete = self.run_cli(
                "finish",
                "--state-dir",
                str(state_dir),
                "--native-workflow-complete",
                expected=2,
            )
            self.assertEqual(incomplete["error"], "segments_incomplete")

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "bc56161d-b464-49fb-b563-b6867705db3b")
            self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="permission"),
                expected=3,
            )

            blocked = self.run_cli(
                "finish",
                "--state-dir",
                str(state_dir),
                "--native-workflow-complete",
                expected=2,
            )
            self.assertEqual(blocked["error"], "pending_permission")

    def test_optional_verification_evidence_is_still_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "72c1c652-8835-47e1-8c91-08320f938134")
            self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
            )

            self.run_cli(
                "record-verification",
                "--state-dir",
                str(state_dir),
                "--command",
                "python3 -m unittest",
                "--exit-code",
                "0",
                "--evidence-ref",
                "native-verification.log",
            )

            state = json.loads((state_dir / "work-unit.json").read_text())
            self.assertEqual(state["evidence"]["verified"][-1]["evidence_ref"], "native-verification.log")

    @unittest.skipIf(os.name == "nt", "POSIX lease timing regression")
    def test_handoff_and_repair_reject_an_active_runner_lease(self) -> None:
        import fcntl

        for action in ("finish", "repair"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                root = self.make_repo(directory)
                state_dir = self.init_work_unit(
                    root,
                    f"38f59f50-0988-4ac8-af1f-e897109e9{1 if action == 'finish' else 2:03d}",
                )
                self.run_cli(
                    "run",
                    "--state-dir",
                    str(state_dir),
                    environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
                )
                descriptor = os.open(state_dir / "raw-events.jsonl", os.O_RDWR)
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                try:
                    arguments = [action, "--state-dir", str(state_dir), "--native-workflow-complete"]
                    if action == "repair":
                        arguments = [
                            "add-repair-segment",
                            "--state-dir",
                            str(state_dir),
                            "--scope",
                            "repair finding",
                            "--finding-id",
                            "F-1",
                        ]
                    rejected = self.run_cli(*arguments, expected=2)
                    self.assertEqual(rejected["error"], "active_process")
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)

    @unittest.skipIf(os.name == "nt", "POSIX lease timing regression")
    def test_handoff_and_repair_hold_the_inactive_lease_through_state_mutation(self) -> None:
        import fcntl

        sys.path.insert(0, str(RUNNER_ROOT))
        from runner.supervisor import active_lease_held

        for action in ("finish", "repair"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                root = self.make_repo(directory)
                state_dir = self.init_work_unit(
                    root,
                    f"ccad7b3d-e19d-43ce-b27c-c41ed894f{1 if action == 'finish' else 2:03d}",
                )
                self.run_cli(
                    "run",
                    "--state-dir",
                    str(state_dir),
                    environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
                )
                state_lock = os.open(state_dir, os.O_RDONLY)
                fcntl.flock(state_lock, fcntl.LOCK_EX)
                arguments = [action, "--state-dir", str(state_dir), "--native-workflow-complete"]
                if action == "repair":
                    arguments = [
                        "add-repair-segment",
                        "--state-dir",
                        str(state_dir),
                        "--scope",
                        "repair finding",
                        "--finding-id",
                        "F-1",
                    ]
                running = subprocess.Popen(
                    [sys.executable, str(ENTRYPOINT), *arguments],
                    cwd=REPO_ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.addCleanup(lambda: running.poll() is None and running.kill())
                lease_observed = False
                try:
                    for _ in range(100):
                        if active_lease_held(state_dir):
                            lease_observed = True
                            break
                        if running.poll() is not None:
                            break
                        time.sleep(0.01)
                finally:
                    fcntl.flock(state_lock, fcntl.LOCK_UN)
                    os.close(state_lock)
                stdout, stderr = running.communicate(timeout=5)
                self.assertTrue(lease_observed, f"{action} did not retain the inactive lease")
                self.assertEqual(running.returncode, 0, stderr + stdout)

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
            self.assertEqual(approved["status"], "interrupted")
            self.assertEqual(approved["segments"][0]["status"], "interrupted")
            self.assertEqual(approved["permissions"]["resolved"][-1]["resolution"], "approved")
            self.assertEqual(approved["permissions"]["resolved"][-1]["segment_id"], "segment-1")
            success_environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="success")
            resumed = self.run_cli("resume", "--state-dir", str(state_dir), environment=success_environment)
            self.assertEqual(resumed["status"], "implementation_complete")

    def test_permission_can_be_denied_or_dismissed_then_same_session_resumed(self) -> None:
        for index, (action, expected_resolution) in enumerate(
            (("deny-permission", "denied"), ("dismiss-permission", "dismissed")),
            start=1,
        ):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                root = self.make_repo(directory)
                state_dir = self.init_work_unit(
                    root,
                    f"3c2e38ee-aa89-463e-b48c-7f2169daa20{index}",
                )
                stopped = self.run_cli(
                    "run",
                    "--state-dir",
                    str(state_dir),
                    environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="permission"),
                    expected=3,
                )
                session_id = stopped["segments"][0]["session_id"]

                resolved = self.run_cli(
                    action,
                    "--state-dir",
                    str(state_dir),
                    "--expected-tool-name",
                    "Bash",
                    "--reason",
                    "use the declared project command instead",
                )

                self.assertEqual(resolved["status"], "interrupted")
                self.assertEqual(resolved["segments"][0]["status"], "interrupted")
                self.assertIsNone(resolved["permissions"]["pending"])
                audit = resolved["permissions"]["resolved"][-1]
                self.assertEqual(audit["resolution"], expected_resolution)
                self.assertEqual(audit["reason"], "use the declared project command instead")
                self.assertEqual(audit["segment_id"], "segment-1")

                resumed = self.run_cli(
                    "resume",
                    "--state-dir",
                    str(state_dir),
                    "--continuation-context",
                    "Do not retry the rejected command; use the declared safe alternative.",
                    environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
                )
                self.assertEqual(resumed["segments"][0]["session_id"], session_id)
                self.assertEqual(resumed["status"], "implementation_complete")

    def test_permission_denied_can_be_dismissed_then_same_session_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "4b7baf0c-fc31-46cc-8c16-73c90ace7429")
            stopped = self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="permission-denied"),
                expected=3,
            )
            session_id = stopped["segments"][0]["session_id"]
            self.assertEqual(stopped["permissions"]["pending"]["tool_input"], {"command": "git status --short"})

            dismissed = self.run_cli(
                "dismiss-permission",
                "--state-dir",
                str(state_dir),
                "--expected-tool-name",
                "Bash",
                "--reason",
                "use the approved command",
            )
            self.assertIsNone(dismissed["permissions"]["pending"])
            self.assertEqual(dismissed["permissions"]["resolved"][-1]["resolution"], "dismissed")

            resumed = self.run_cli(
                "resume",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
            )
            self.assertEqual(resumed["status"], "implementation_complete")
            self.assertEqual(resumed["segments"][0]["session_id"], session_id)
            self.assertEqual(resumed["segments"][0]["attempt"], 1)
            self.assertEqual(resumed["segments"][0]["resume_count"], 1)

    def test_permission_resolution_errors_leave_state_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "e739d07d-d590-4ef6-a2eb-a34df1c4e775")
            no_pending = self.run_cli(
                "deny-permission",
                "--state-dir",
                str(state_dir),
                "--expected-tool-name",
                "Bash",
                "--reason",
                "not required",
                expected=2,
            )
            self.assertEqual(no_pending["error"], "no_pending_permission")

            self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="permission"),
                expected=3,
            )
            state_path = state_dir / "work-unit.json"
            before = state_path.read_bytes()

            mismatch = self.run_cli(
                "dismiss-permission",
                "--state-dir",
                str(state_dir),
                "--expected-tool-name",
                "Read",
                "--reason",
                "wrong request",
                expected=2,
            )

            self.assertEqual(mismatch["error"], "permission_mismatch")
            self.assertEqual(state_path.read_bytes(), before)

    def test_backend_failure_can_explicitly_restart_an_uncreated_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "04cf4893-d07a-4ac4-8c92-c06f60d47952")
            failed = self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="missing-executable"),
                expected=127,
            )
            failed_session = failed["segments"][0]["session_id"]
            self.assertEqual(failed["status"], "backend_failure")

            restarted = self.run_cli(
                "restart-segment-session",
                "--state-dir",
                str(state_dir),
                "--segment-id",
                "segment-1",
                "--reason",
                "Claude rejected the session before creating it",
            )
            self.assertIsNone(restarted["segments"][0]["session_id"])
            state = json.loads((state_dir / "work-unit.json").read_text())
            self.assertEqual(state["runtime"]["abandoned_sessions"][-1]["session_id"], failed_session)

            completed = self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
            )
            self.assertEqual(completed["status"], "implementation_complete")
            self.assertNotEqual(completed["segments"][0]["session_id"], failed_session)
            self.assertEqual(completed["segments"][0]["attempt"], 2)
            self.assertEqual(completed["segments"][0]["resume_count"], 0)

    def test_structured_permission_can_be_approved_then_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "5ed09ec3-13fb-4f25-a8c7-b704e15ea677")
            stopped = self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="structured-permission"),
                expected=3,
            )
            self.assertEqual(stopped["permissions"]["pending"]["tool_name"], "Bash")
            bypass = self.run_cli("resume", "--state-dir", str(state_dir), expected=2)
            self.assertEqual(bypass["error"], "pending_permission")
            fresh_run_bypass = self.run_cli("run", "--state-dir", str(state_dir), expected=2)
            self.assertEqual(fresh_run_bypass["error"], "pending_permission")

            self.run_cli(
                "approve-permission",
                "--state-dir",
                str(state_dir),
                "--expected-tool-name",
                "Bash",
                "--allow-rule",
                "Bash(pytest --version)",
            )
            resumed = self.run_cli(
                "resume",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
            )
            self.assertEqual(resumed["status"], "implementation_complete")

    def test_context_continuation_is_bounded_persisted_and_sent_to_same_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "1392e7a3-ad92-49e0-8118-e894c174548d")
            environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="require-context")
            stopped = self.run_cli("run", "--state-dir", str(state_dir), environment=environment, expected=3)
            session_id = stopped["segments"][0]["session_id"]

            missing = self.run_cli("resume", "--state-dir", str(state_dir), environment=environment, expected=2)
            self.assertEqual(missing["error"], "continuation_context_required")
            too_large = self.run_cli(
                "resume",
                "--state-dir",
                str(state_dir),
                "--continuation-context",
                "x" * 65537,
                environment=environment,
                expected=2,
            )
            self.assertEqual(too_large["error"], "continuation_context_too_large")

            resumed = self.run_cli(
                "resume",
                "--state-dir",
                str(state_dir),
                "--continuation-context",
                "fixture answer",
                environment=environment,
            )
            self.assertEqual(resumed["status"], "implementation_complete")
            self.assertEqual(resumed["segments"][0]["session_id"], session_id)
            self.assertEqual(resumed["segments"][0]["attempt"], 1)
            self.assertEqual(resumed["segments"][0]["resume_count"], 1)
            state = json.loads((state_dir / "work-unit.json").read_text())
            self.assertEqual(state["runtime"]["continuation_inputs"][-1]["context"], "fixture answer")

    def test_failed_concurrent_resume_does_not_record_undispatched_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "51dc1cc0-0343-412c-a1a4-7a2fb42fe34d")
            self.run_cli(
                "run",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="needs-context"),
                expected=3,
            )
            state_path = state_dir / "work-unit.json"
            running = subprocess.Popen(
                [
                    sys.executable,
                    str(ENTRYPOINT),
                    "resume",
                    "--state-dir",
                    str(state_dir),
                    "--continuation-context",
                    "first",
                ],
                cwd=REPO_ROOT,
                env=dict(os.environ, FAKE_CLAUDE_SCENARIO="model-idle", FAKE_CLAUDE_DELAY="0.8"),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.addCleanup(lambda: running.poll() is None and running.kill())
            for _ in range(100):
                state = json.loads(state_path.read_text())
                active_run = state["runtime"].get("active_run")
                if isinstance(active_run, dict) and active_run.get("identity"):
                    break
                time.sleep(0.01)
            else:
                self.fail("first resume never started Claude")

            rejected = self.run_cli(
                "resume",
                "--state-dir",
                str(state_dir),
                "--continuation-context",
                "second",
                expected=2,
            )
            self.assertEqual(rejected["error"], "work_unit_active")
            stdout, stderr = running.communicate(timeout=5)
            self.assertEqual(running.returncode, 0, stderr + stdout)
            contexts = json.loads(state_path.read_text())["runtime"]["continuation_inputs"]
            self.assertEqual([item["context"] for item in contexts], ["first"])

    def test_active_run_lease_rejects_duplicate_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "30d51f07-81f8-45c4-844c-b88a334d2186")
            state_path = state_dir / "work-unit.json"
            environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="model-idle", FAKE_CLAUDE_DELAY="0.8")
            first = subprocess.Popen(
                [sys.executable, str(ENTRYPOINT), "run", "--state-dir", str(state_dir)],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.addCleanup(lambda: first.poll() is None and first.kill())
            for _ in range(100):
                state = json.loads(state_path.read_text())
                if state["runtime"].get("active_run", {}).get("controller_pid"):
                    break
                time.sleep(0.01)
            else:
                self.fail("first Runner never established its active lease")

            result = self.run_cli("run", "--state-dir", str(state_dir), expected=2)

            self.assertEqual(result["error"], "work_unit_active")
            stdout, stderr = first.communicate(timeout=5)
            self.assertEqual(first.returncode, 0, stderr + stdout)

    def test_interrupt_targets_the_active_runner_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "99f8fd70-dc3a-4c68-b12c-092a91b35dda")
            state_path = state_dir / "work-unit.json"
            environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="model-idle", FAKE_CLAUDE_DELAY="5")
            running = subprocess.Popen(
                [sys.executable, str(ENTRYPOINT), "run", "--state-dir", str(state_dir)],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.addCleanup(lambda: running.poll() is None and running.kill())
            for _ in range(100):
                state = json.loads(state_path.read_text())
                if state["runtime"].get("active_run", {}).get("identity"):
                    break
                time.sleep(0.01)
            else:
                self.fail("Runner never started its Claude process")

            control = self.run_cli("interrupt", "--state-dir", str(state_dir))
            self.assertEqual(control["control"], "interrupt")
            stdout, stderr = running.communicate(timeout=5)

            self.assertNotEqual(running.returncode, 0, stderr + stdout)
            self.assertEqual(json.loads(state_path.read_text())["status"], "interrupted")

            resumed = self.run_cli(
                "resume",
                "--state-dir",
                str(state_dir),
                environment=dict(os.environ, FAKE_CLAUDE_SCENARIO="success"),
            )
            self.assertEqual(resumed["status"], "implementation_complete")
            recovered_state = json.loads(state_path.read_text())
            self.assertNotIn("control_requested", recovered_state["runtime"])

    def test_stale_control_identity_fails_running_segment_and_clears_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_repo(directory)
            state_dir = self.init_work_unit(root, "a9d6a6b4-7fb7-4ccc-a4b8-479e71a60fc0")
            state_path = state_dir / "work-unit.json"
            state = json.loads(state_path.read_text())
            state["status"] = "running"
            state["segments"][0]["status"] = "running"
            state["segments"][0]["session_id"] = "c301fb82-71dd-46a4-9d18-bbce90e70bef"
            state["segments"][0]["attempt"] = 1
            state["runtime"]["active_run"] = {
                "launch_token": "stale",
                "controller_pid": 999999,
                "identity": {"pid": 999999},
                "reserved_at": "2026-08-07T00:00:00Z",
            }
            state["result"] = {"status": "DONE", "summary": "stale"}
            state_path.write_text(json.dumps(state), encoding="utf-8")

            rejected = self.run_cli(
                "interrupt",
                "--state-dir",
                str(state_dir),
                expected=2,
            )

            self.assertEqual(rejected["error"], "unsafe_process_identity")
            failed = json.loads(state_path.read_text())
            self.assertEqual(failed["status"], "backend_failure")
            self.assertEqual(failed["segments"][0]["status"], "failed")
            self.assertIsNone(failed["result"])
            self.assertIsNone(failed["runtime"]["active_run"])

    def test_finished_work_unit_rejects_reopen_and_repair(self) -> None:
        for mode in ("resume", "repair"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.make_repo(directory)
                state_dir = self.init_work_unit(root, f"2d20555b-83d8-4c18-9306-6858e0149d{1 if mode == 'resume' else 2:02d}")
                environment = dict(os.environ, FAKE_CLAUDE_SCENARIO="success")
                self.run_cli("run", "--state-dir", str(state_dir), environment=environment)
                self.run_cli(
                    "finish",
                    "--state-dir",
                    str(state_dir),
                    "--native-workflow-complete",
                )

                if mode == "resume":
                    rejected = self.run_cli(
                        "resume",
                        "--state-dir",
                        str(state_dir),
                        "--segment-id",
                        "segment-1",
                        environment=environment,
                        expected=2,
                    )
                else:
                    rejected = self.run_cli(
                        "add-repair-segment",
                        "--state-dir",
                        str(state_dir),
                        "--scope",
                        "repair finding",
                        "--finding-id",
                        "F-1",
                        expected=2,
                    )

                self.assertEqual(rejected["error"], "work_unit_finished")
                self.assertTrue(state_dir.exists())


if __name__ == "__main__":
    unittest.main()
