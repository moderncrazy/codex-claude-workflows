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
    def test_commit_review_and_tracker_lifecycle_is_explicit(self):
        skill = (ROOT / "skills/matt-claude-workflow/SKILL.md").read_text()
        lifecycle = ROOT / "skills/matt-claude-workflow/references/matt-lifecycle-adapter.md"
        self.assertTrue(lifecycle.exists())
        self.assertIn("matt-lifecycle-adapter.md", skill)

        text = lifecycle.read_text().lower()
        checkpoint = text.index("review checkpoint commit")
        review = text.index("native `code-review`", checkpoint)
        resolve = text.index("resolve or close the ticket", review)
        frontier = text.index("recompute the native frontier", resolve)
        self.assertLess(checkpoint, review)
        self.assertLess(review, resolve)
        self.assertLess(resolve, frontier)
        self.assertIn("claim the ticket", text)
        self.assertIn("do not push, merge, amend, rebase, reset, or tag", text)
        self.assertIn("do not add a cross-ticket final review or verify review", text)

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
            self.assertIn("`This command requires approval`", protocol)
            self.assertIn("return `PERMISSION_REQUIRED` immediately", protocol)

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
            ["python3", "scripts/sync_shared_references.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class SuperpowersStateTests(unittest.TestCase):
    def test_claude_state_uses_a_deterministic_native_workspace_filename(self):
        protocol = (
            ROOT
            / "skills/superpowers-claude-workflow/references/claude-execution-protocol.md"
        ).read_text()
        self.assertIn("task-N-claude-state.json", protocol)


if __name__ == "__main__":
    unittest.main()
