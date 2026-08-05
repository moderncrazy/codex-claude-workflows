import json
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


class ClaudeExecutionProtocolTests(unittest.TestCase):
    def test_noninteractive_runs_preapprove_only_exact_user_approved_commands(self):
        for skill in ("superpowers-claude-workflow", "matt-claude-workflow"):
            protocol = (
                ROOT
                / "skills"
                / skill
                / "references"
                / "claude-execution-protocol.md"
            ).read_text()
            self.assertIn("## Initial command permissions", protocol)
            self.assertIn("exact commands already approved", protocol)
            self.assertIn("`--allowedTools`", protocol)
            self.assertIn("`This command requires approval`", protocol)
            self.assertIn("return `PERMISSION_REQUIRED` immediately", protocol)


class SuperpowersStateTests(unittest.TestCase):
    def test_claude_state_uses_a_deterministic_native_workspace_filename(self):
        protocol = (
            ROOT
            / "skills/superpowers-claude-workflow/references/claude-execution-protocol.md"
        ).read_text()
        self.assertIn("task-N-claude-state.json", protocol)


if __name__ == "__main__":
    unittest.main()
