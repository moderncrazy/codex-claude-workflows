from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


RUNNER_ROOT = Path(__file__).parents[1] / "shared" / "claude-runner"
sys.path.insert(0, str(RUNNER_ROOT))
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from mcp_client import McpClient  # noqa: E402
from runner import PROGRESS_TOOL_NAME  # noqa: E402
from runner.progress_mcp import serve_progress_mcp  # noqa: E402
from runner.state_store import StateStore  # noqa: E402
from tests.test_runner_state import sample_work_unit  # noqa: E402


class ProgressMcpTests(unittest.TestCase):
    def start_server(self, state_dir: Path) -> tuple[subprocess.Popen[str], McpClient]:
        command = [
            sys.executable,
            "-c",
            "from pathlib import Path; from runner.progress_mcp import serve_progress_mcp; "
            "raise SystemExit(serve_progress_mcp(Path(__import__('sys').argv[1])))",
            str(state_dir),
        ]
        process = subprocess.Popen(
            command,
            cwd=RUNNER_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.addCleanup(self.stop_server, process)
        return process, McpClient(process)

    @staticmethod
    def stop_server(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def test_protocol_lists_only_reporter_and_preserves_claim_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            _, client = self.start_server(store.state_dir)

            initialized = client.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "fixture", "version": "1"},
                },
            )
            self.assertEqual(initialized["result"]["serverInfo"]["name"], "codex-claude-runner")
            client.notify("notifications/initialized")
            self.assertEqual(client.request("ping")["result"], {})
            tools = client.request("tools/list")["result"]["tools"]
            self.assertEqual(PROGRESS_TOOL_NAME, "report_progress")
            self.assertEqual([tool["name"] for tool in tools], [PROGRESS_TOOL_NAME])

            claim = {
                "kind": "verification_claim",
                "message": "1 passed; do not reinterpret",
                "next_action": "await Codex verification",
                "evidence_refs": ["toolu_test"],
            }
            response = client.call_tool(PROGRESS_TOOL_NAME, claim)

            self.assertFalse(response["result"].get("isError", False))
            self.assertIn("receipt 1", response["result"]["content"][0]["text"])
            self.assertEqual(store.load().progress_claims[-1]["claim"], claim)

    def test_invalid_claim_and_unknown_method_return_json_rpc_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            _, client = self.start_server(store.state_dir)

            invalid = client.call_tool(
                PROGRESS_TOOL_NAME,
                {"kind": "invented", "message": "x", "next_action": "", "evidence_refs": []},
            )
            unknown = client.request("resources/list")

            self.assertEqual(invalid["error"]["code"], -32602)
            self.assertEqual(unknown["error"]["code"], -32601)
            self.assertEqual(store.load().progress_claims, [])

    def test_malformed_json_diagnostic_never_pollutes_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore.create(sample_work_unit(Path(directory)))
            process, client = self.start_server(store.state_dir)
            assert process.stdin is not None
            process.stdin.write("not-json\n")
            process.stdin.flush()

            response = client.request("ping")

            self.assertEqual(response["result"], {})
            assert process.stderr is not None
            diagnostic = process.stderr.readline()
            self.assertIn("invalid JSON", diagnostic)


if __name__ == "__main__":
    unittest.main()
