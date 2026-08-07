import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_schema(skill_name: str) -> dict:
    path = ROOT / "skills" / skill_name / "references" / "claude-result.schema.json"
    return json.loads(path.read_text())


def condition_for(schema: dict, status: str) -> dict:
    for rule in schema.get("allOf", []):
        if rule.get("if", {}).get("properties", {}).get("status", {}).get("const") == status:
            return rule["then"]
    raise AssertionError(f"missing conditional rule for {status}")


class SharedResultSchemaTests(unittest.TestCase):
    def test_schema_uses_claude_supported_draft_and_strict_array_types(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            schema = load_schema(skill)
            self.assertEqual(
                schema["$schema"],
                "http://json-schema.org/draft-07/schema#",
            )

            permission = condition_for(schema, "PERMISSION_REQUIRED")["properties"]
            concerns = condition_for(schema, "DONE_WITH_CONCERNS")["properties"]
            context = condition_for(schema, "NEEDS_CONTEXT")["properties"]
            done = condition_for(schema, "DONE")["properties"]

            self.assertEqual(permission["permission_requests"]["type"], "array")
            self.assertEqual(concerns["concerns"]["type"], "array")
            self.assertEqual(context["context_requests"]["type"], "array")
            for field in (
                "concerns",
                "context_requests",
                "permission_requests",
                "tests",
            ):
                self.assertEqual(done[field]["type"], "array")
            self.assertEqual(done["tests"]["not"]["type"], "array")

    def test_statuses_require_their_recovery_payloads(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            schema = load_schema(skill)
            self.assertIn("context_requests", schema["required"])
            self.assertEqual(
                condition_for(schema, "PERMISSION_REQUIRED")["properties"]["permission_requests"]["minItems"],
                1,
            )
            self.assertEqual(
                condition_for(schema, "DONE_WITH_CONCERNS")["properties"]["concerns"]["minItems"],
                1,
            )
            self.assertEqual(
                condition_for(schema, "NEEDS_CONTEXT")["properties"]["context_requests"]["minItems"],
                1,
            )

    def test_done_rejects_incomplete_test_evidence(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            done = condition_for(load_schema(skill), "DONE")["properties"]
            self.assertEqual(done["tests"]["minItems"], 1)
            rejected = done["tests"]["not"]["contains"]["properties"]["status"]["enum"]
            self.assertEqual(rejected, ["failed", "not_run"])


class MattLifecycleTests(unittest.TestCase):
    def test_native_workflow_owns_review_fixes_and_tracker_transitions(self):
        skill = (ROOT / "skills/matt-claude-workflow/SKILL.md").read_text()
        lifecycle = ROOT / "skills/matt-claude-workflow/references/matt-lifecycle-adapter.md"
        self.assertTrue(lifecycle.exists())
        self.assertIn("matt-lifecycle-adapter.md", skill)

        text = lifecycle.read_text().lower()
        self.assertIn("native workflow", text)
        self.assertIn("working-tree review", text)
        self.assertIn("git diff <fixed-point>", text)
        self.assertIn("git ls-files --others --exclude-standard", text)
        self.assertIn("review is accepted", text)
        self.assertNotIn("compatibility checkpoint", text)
        self.assertNotIn("checkpoint commit", text)
        self.assertIn("only when", text)
        self.assertIn("configured tracker", text)
        self.assertIn("do not push, merge, amend, rebase, reset, or tag", text)
        self.assertIn("do not add a cross-ticket final review or verify review", text)
        self.assertLess(text.index("working-tree review"), text.index("review is accepted"))
        self.assertLess(text.index("review is accepted"), text.index("commit the accepted"))
        for invasive_policy in (
            "user-directed fixes",
            "do not start fixes automatically",
            "when the user requests fixes",
            "apply only user-requested fixes",
            "claim the ticket",
            "resolve or close the ticket",
            "recompute the native frontier",
        ):
            self.assertNotIn(invasive_policy, (skill + text).lower())

    def test_wrapper_delegates_routing_tracer_and_tracker_policy_to_native_matt(self):
        matt_skill = ROOT / "skills/matt-claude-workflow"
        policy_paths = [matt_skill / "SKILL.md", *sorted((matt_skill / "references").glob("*.md"))]
        policy_text = {path.name: path.read_text().lower() for path in policy_paths}
        text = "\n".join(policy_text.values())

        self.assertIn("native matt skills choose", text)
        self.assertIn("tracker prerequisites", text)
        self.assertIn("tracer-bullet decomposition", text)
        self.assertIn("after the native workflow identifies", text)
        for wrapper_policy in (
            "choose scale",
            "tracker setup only for the spec/ticket path",
            "cross-session work or multiple tracer bullets",
            "without reading or changing a tracker",
            "single-session native matt implement call",
            "one ticket or implicit task owns one temporary work unit",
            "ticket or implicit-task implementer",
            "tracker/implicit-task completion",
        ):
            self.assertNotIn(wrapper_policy, text)

        for reference in ("executor-contract.md", "claude-execution-protocol.md"):
            self.assertIn("native implementation work unit", policy_text[reference])

    def test_matt_review_continuation_routes_without_new_adapter_gate(self):
        protocol = (
            ROOT
            / "skills/matt-claude-workflow/references/claude-execution-protocol.md"
        ).read_text().lower()
        self.assertIn("native workflow routes a finding back to implementation", protocol)
        self.assertNotIn("accepted finding", protocol)

    def test_skill_names_the_native_review_as_one_two_axis_review(self):
        skill = (ROOT / "skills/matt-claude-workflow/SKILL.md").read_text()
        self.assertIn("native two-axis Codex Review", skill)
        self.assertNotIn("dual Codex Review", skill)


class AgentWritingStandardsTests(unittest.TestCase):
    def test_orchestration_skills_are_explicitly_user_invoked(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            text = (ROOT / "skills" / skill / "SKILL.md").read_text()
            self.assertIn("disable-model-invocation: true", text.split("---", 2)[1])
            self.assertNotIn("Use when the user explicitly invokes", text)

    def test_schema_is_passed_verbatim_without_becoming_required_context(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            text = (ROOT / "skills" / skill / "SKILL.md").read_text()
            self.assertIn("Pass the bundled result Schema verbatim", text)
            self.assertNotIn("and its [result Schema]", text)

    def test_cross_runtime_skill_packages_validate(self):
        result = subprocess.run(
            ["python3", "scripts/validate_skill_packages.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ClaudeExecutionProtocolTests(unittest.TestCase):
    def load_permission_broker(self, skill: str) -> str:
        return (
            ROOT / "skills" / skill / "references/claude-permission-broker.md"
        ).read_text()

    def test_noninteractive_runs_preapprove_task_scoped_command_families(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            protocol = (
                ROOT
                / "skills"
                / skill
                / "references"
                / "claude-execution-protocol.md"
            ).read_text()
            self.assertIn("## Initial command permissions", protocol)
            self.assertIn("task-scoped command-family", protocol)
            self.assertIn("`Bash(.venv/bin/pytest *)`", protocol)
            self.assertIn("version or help probes", protocol)
            self.assertIn("`Bash(git status *)`", protocol)
            self.assertIn("`Bash(git diff *)`", protocol)
            self.assertIn("`--allowedTools`", protocol)
            self.assertIn("`PermissionRequest`", protocol)
            self.assertIn("stop Claude outside the prompt", protocol)

    def test_broad_or_dangerous_command_families_remain_forbidden(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            protocol = (
                ROOT
                / "skills"
                / skill
                / "references"
                / "claude-execution-protocol.md"
            ).read_text()
            self.assertIn("package installation", protocol)
            self.assertIn("network commands", protocol)
            self.assertIn("bare `Bash`", protocol)
            self.assertIn("shell/interpreter wildcard", protocol)
            self.assertIn("push", protocol)
            self.assertIn("history rewriting", protocol)

        matt_protocol = (
            ROOT
            / "skills"
            / "matt-claude-workflow"
            / "references"
            / "claude-execution-protocol.md"
        ).read_text().lower()
        self.assertIn("never pre-approve commit", matt_protocol)

    def test_codex_brokers_new_tool_permissions_without_interrupting_the_user(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            protocol = (
                ROOT
                / "skills"
                / skill
                / "references"
                / "claude-execution-protocol.md"
            ).read_text()
            broker = self.load_permission_broker(skill)
            self.assertIn("claude-permission-broker.md", protocol)
            self.assertNotIn("## Codex permission broker", protocol)
            self.assertIn("`Read`, `Glob`, and `Grep`", broker)
            self.assertIn("read-only CLI", broker)
            self.assertIn("read-only MCP", broker)
            self.assertIn("resume the same Session automatically", broker)
            self.assertIn("Continue without user interaction", broker)
            self.assertIn("unavailable to Claude Code", broker)
            self.assertNotIn("Obtain user approval or stop", protocol)

    def test_permission_requests_can_be_approved_denied_or_dismissed(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            protocol = (
                ROOT
                / "skills"
                / skill
                / "references"
                / "claude-execution-protocol.md"
            ).read_text()
            self.assertIn("`approve-permission`", protocol)
            self.assertIn("`deny-permission`", protocol)
            self.assertIn("`dismiss-permission`", protocol)
            self.assertIn("explicitly `resume`", protocol)

    def test_codex_escalates_only_side_effectful_or_ambiguous_permissions(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            broker = self.load_permission_broker(skill)
            self.assertIn("outside the repository/worktree", broker)
            self.assertIn("external write", broker)
            self.assertIn("installation", broker)
            self.assertIn("cannot classify", broker)
            self.assertIn("ask the user", broker.lower())

        readme = (ROOT / "README.md").read_text()
        self.assertIn("Codex permission broker", readme)
        self.assertIn("without interrupting the user", readme)

    def test_permission_broker_has_one_authoritative_source_and_hard_copies(self):
        canonical = (ROOT / "shared/claude-permission-broker.md").read_text()
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            self.assertEqual(self.load_permission_broker(skill), canonical)

        result = subprocess.run(
            ["python3", "scripts/sync_shared_assets.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class PackagedRunnerTests(unittest.TestCase):
    def test_runner_assets_are_exact_hard_copies_without_symlinks(self):
        canonical = ROOT / "shared/claude-runner"
        expected = {
            path.relative_to(canonical): (path.read_bytes(), path.stat().st_mode & 0o111)
            for path in canonical.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            skill_root = ROOT / "skills" / skill
            packaged = skill_root / "scripts/claude-runner"
            actual = {
                path.relative_to(packaged): (path.read_bytes(), path.stat().st_mode & 0o111)
                for path in packaged.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            }
            self.assertEqual(actual, expected)
            self.assertFalse(any(path.is_symlink() for path in skill_root.rglob("*")))

    def test_packaged_entrypoints_are_self_contained(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            entrypoint = ROOT / "skills" / skill / "scripts/claude-runner/claude_runner.py"
            result = subprocess.run(
                ["python3", str(entrypoint), "--help"],
                cwd=Path("/tmp"),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class RunnerWorkflowBoundaryTests(unittest.TestCase):
    def test_skills_route_only_the_implementation_boundary_through_packaged_runner(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            skill_dir = ROOT / "skills" / skill
            combined = "\n".join(path.read_text() for path in skill_dir.rglob("*.md"))
            self.assertIn("scripts/claude-runner/claude_runner.py", combined)
            self.assertIn("/.tmp/", combined)
            self.assertIn("Execution Segment", combined)
            self.assertIn("implementation_complete", combined)
            self.assertIn("not native completion", combined.lower())
            for forbidden in (
                "--output-format json",
                "--strict-mcp-config",
                "--include-partial-messages",
                "bypassPermissions",
                "task-N-claude-state.json",
            ):
                self.assertNotIn(forbidden, combined)

    def test_superpowers_and_matt_keep_distinct_native_completion_contracts(self):
        superpowers = (ROOT / "skills/superpowers-claude-workflow/SKILL.md").read_text().lower()
        matt = (ROOT / "skills/matt-claude-workflow/SKILL.md").read_text().lower()
        self.assertIn("final review", superpowers)
        self.assertIn("verification-before-completion", superpowers)
        self.assertIn("finishing-a-development-branch", superpowers)
        self.assertIn("native two-axis codex review", matt)
        self.assertIn("tracker", matt)
        self.assertIn("do not add a cross-ticket final review or verify review", matt)

    def test_runner_finishes_only_after_native_completion(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            combined = "\n".join(
                path.read_text().lower()
                for path in (ROOT / "skills" / skill).rglob("*.md")
            )
            self.assertIn("finish --native-workflow-complete", combined)
            self.assertIn("`finished`", combined)
            self.assertIn("cleanup", combined)
            self.assertLess(
                combined.index("implementation_complete"),
                combined.index("finish --native-workflow-complete"),
            )

    def test_sequential_native_work_may_overlap_files(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            contract = (
                ROOT / "skills" / skill / "references/executor-contract.md"
            ).read_text().lower()
            self.assertIn("actually run concurrently", contract)
            self.assertIn("sequential", contract)
            self.assertNotIn("concurrently available", contract)

    def test_standalone_docs_and_configuration_remain_with_codex(self):
        skill = (ROOT / "skills/superpowers-claude-workflow/SKILL.md").read_text().lower()
        self.assertIn("standalone documentation", skill)
        self.assertIn("configuration work remains with codex", skill)
        self.assertIn("every change required inside a claude-routed coding task", skill)
        self.assertIn("project dependency work remains governed by the approved native plan", skill)
        self.assertNotIn("ordinary edits", skill)
        self.assertNotIn(
            "keep source, tests, documentation, and configuration with the selected implementer",
            skill,
        )

    def test_runner_evidence_does_not_gate_native_lifecycle(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            protocol = (
                ROOT
                / "skills"
                / skill
                / "references/claude-execution-protocol.md"
            ).read_text().lower()
            self.assertIn("optional adapter evidence", protocol)
            self.assertIn("native workflow decides when verification is required", protocol)


if __name__ == "__main__":
    unittest.main()
