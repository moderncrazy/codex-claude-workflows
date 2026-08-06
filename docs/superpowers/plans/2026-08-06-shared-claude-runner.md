# Shared Claude Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, recoverable Claude Code Runner shared by both explicit orchestration Skills without changing either native workflow's planning, Review, verification, or completion semantics.

**Architecture:** A Python-standard-library Runner supervises one Work Unit at a time, persists temporary Adapter State under the active working tree's ignored `.tmp` directory, captures Claude `stream-json` losslessly, injects one progress MCP server and two permission Hooks, and exposes narrow lifecycle commands to Codex. One canonical runtime is hard-copied into each standalone Skill package; framework-specific Skills retain all semantic workflow decisions.

**Tech Stack:** Python 3 standard library, Claude Code CLI, newline-delimited JSON-RPC over MCP stdio, JSON Schema draft-07, `unittest`, Git.

## Global Constraints

- Do not modify upstream Superpowers or Matt Skills.
- Do not add Codex hooks, a Codex plugin, SessionStart injection, a global daemon, symlinks, or a global routing file.
- Use only the Python 3 standard library in the packaged Runner.
- Keep `sonnet` and `opus` as capability aliases; never inspect or enforce a concrete provider model.
- Preserve stdout and stderr bytes exactly; parse copies and never summarize unknown events.
- Treat Progress Claims as unverified; only Codex may accept tests, commits, Review findings, or completion.
- Timeout thresholds emit observations only. They never terminate Claude without an explicit Codex control command.
- The Runner is the only Adapter State writer. Native workflow state remains authoritative outside `work-unit.json`.
- Keep both installed Skill packages self-contained through exact hard copies, never symlinks.

---

## File structure

### Canonical runtime

- Create `shared/claude-runner/claude_runner.py` — executable entry point that delegates to `runner.cli.main`.
- Create `shared/claude-runner/work-unit.schema.json` — machine-readable Adapter State contract.
- Create `shared/claude-runner/runner/__init__.py` — package version and exported protocol constants.
- Create `shared/claude-runner/runner/contracts.py` — enums, dataclasses, serialization, and transition validation.
- Create `shared/claude-runner/runner/state_store.py` — cross-process lock, atomic JSON replacement, and append-only evidence writes.
- Create `shared/claude-runner/runner/progress_mcp.py` — minimal local stdio MCP server exposing only `report_progress`.
- Create `shared/claude-runner/runner/permission_hooks.py` — generated settings plus `PermissionRequest` and `PermissionDenied` hook handlers.
- Create `shared/claude-runner/runner/stream_capture.py` — exact-byte capture and structural event observations.
- Create `shared/claude-runner/runner/supervisor.py` — Claude process-group lifecycle, heartbeat, warning clocks, and explicit control.
- Create `shared/claude-runner/runner/cli.py` — `init`, `run`, `resume`, `status`, `wait`, `approve-permission`, `extend`, `interrupt`, `terminate`, `record-verification`, `finish`, and `cleanup` commands.

### Packaged hard copies

- Create `skills/superpowers-claude-workflow/scripts/claude-runner/` as an exact copy of the canonical runtime.
- Create `skills/matt-claude-workflow/scripts/claude-runner/` as an exact copy of the canonical runtime.
- Replace `scripts/sync_shared_references.py` with `scripts/sync_shared_assets.py` — sync the permission broker and the complete Runner tree, with `--check` support.
- Modify `scripts/validate_skill_packages.py` — require executable entry points, schemas, and exact packaged copies.

### Tests and fixtures

- Create `tests/fixtures/fake_claude.py` — scripted Claude CLI replacement with deterministic stream, permission, delay, invalid-protocol, and exit modes.
- Create `tests/fixtures/mcp_client.py` — tiny JSON-RPC fixture for Reporter lifecycle and tool calls.
- Create `tests/test_runner_state.py` — schema, transitions, locking, and atomicity.
- Create `tests/test_runner_progress_mcp.py` — protocol negotiation and verbatim claims.
- Create `tests/test_runner_permission_hooks.py` — forced stop payloads and captured requests.
- Create `tests/test_runner_supervisor.py` — exact capture, lifecycle, warnings, process control, and recovery.
- Create `tests/test_runner_cli.py` — command-level Work Unit lifecycle.
- Modify `tests/test_workflow_contracts.py` — new package, Skill, and native-boundary assertions.

### Workflow documentation

- Modify both `skills/*/SKILL.md` files — invoke the packaged Runner only at the Claude implementer adapter boundary.
- Modify both `skills/*/references/claude-execution-protocol.md` files — replace direct JSON invocation and prompt-dependent permission behavior with Runner commands.
- Modify both `skills/*/references/executor-contract.md` files — define Execution Segment as ephemeral adapter state, not Plan/Ticket data.
- Modify `skills/matt-claude-workflow/references/matt-lifecycle-adapter.md` — map accepted findings to an existing Segment Session or a Codex-created Repair Segment.
- Modify `README.md` — installation, `.tmp` ignore preflight, progress semantics, recovery commands, and validation.

---

### Task 1: Define Adapter State and atomic storage

**Files:**
- Create: `shared/claude-runner/work-unit.schema.json`
- Create: `shared/claude-runner/runner/__init__.py`
- Create: `shared/claude-runner/runner/contracts.py`
- Create: `shared/claude-runner/runner/state_store.py`
- Test: `tests/test_runner_state.py`

**Interfaces:**
- Produces: `WorkUnitStatus`, `SegmentStatus`, `WorkUnitState`, `StateStore.load()`, `StateStore.create()`, `StateStore.update()`, `StateStore.append_raw()`.
- Consumes: no earlier task interfaces.

- [ ] **Step 1: Write failing state-contract tests**

```python
def test_progress_claim_is_stored_verbatim_with_runner_receipt(self):
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


def test_native_completion_cannot_be_written_to_adapter_state(self):
    with tempfile.TemporaryDirectory() as directory:
        store = StateStore.create(sample_work_unit(Path(directory)))
        with self.assertRaises(InvalidTransition):
            store.update_fields({"native_ticket_status": "done"})
```

Define `sample_work_unit()` in the test with a fixed UUID, one pending Segment, a temporary absolute working root, capability `sonnet`, and status `initialized`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests/test_runner_state.py -v`

Expected: FAIL because `runner.contracts` and `runner.state_store` do not exist.

- [ ] **Step 3: Add the strict state schema**

Define top-level required fields in `work-unit.schema.json`:

```json
{
  "schema_version": 1,
  "work_unit_id": "UUID",
  "workflow": "superpowers | matt",
  "native_ref": "string",
  "working_root": "absolute path",
  "fixed_point": "git revision",
  "executor": {"agent": "claude-code", "capability": "sonnet | opus"},
  "status": "initialized | running | permission_required | timeout_suspected | interrupted | backend_failure | implementation_complete | cleaned",
  "segments": [],
  "permissions": {"initial": [], "approved": [], "pending": null},
  "runtime": {},
  "progress_claims": [],
  "evidence": {"declared": [], "verified": []},
  "commits": [],
  "result": null
}
```

Set `additionalProperties: false` on every owned object. Do not add Review verdict, Tracker status, or native completion fields.

- [ ] **Step 4: Implement contracts and explicit transitions**

```python
class WorkUnitStatus(str, Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    PERMISSION_REQUIRED = "permission_required"
    TIMEOUT_SUSPECTED = "timeout_suspected"
    INTERRUPTED = "interrupted"
    BACKEND_FAILURE = "backend_failure"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    CLEANED = "cleaned"


ALLOWED_TRANSITIONS = {
    WorkUnitStatus.INITIALIZED: {WorkUnitStatus.RUNNING, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.RUNNING: {
        WorkUnitStatus.PERMISSION_REQUIRED,
        WorkUnitStatus.TIMEOUT_SUSPECTED,
        WorkUnitStatus.INTERRUPTED,
        WorkUnitStatus.BACKEND_FAILURE,
        WorkUnitStatus.IMPLEMENTATION_COMPLETE,
    },
    WorkUnitStatus.PERMISSION_REQUIRED: {WorkUnitStatus.RUNNING, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.TIMEOUT_SUSPECTED: {WorkUnitStatus.RUNNING, WorkUnitStatus.INTERRUPTED, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.INTERRUPTED: {WorkUnitStatus.RUNNING, WorkUnitStatus.BACKEND_FAILURE},
    WorkUnitStatus.IMPLEMENTATION_COMPLETE: {WorkUnitStatus.CLEANED},
}
```

Represent every Segment with `segment_id`, `kind`, `scope`, `verification_commands`, `status`, `session_id`, `attempt`, and timestamps. Reject a new Segment Session until the previous Segment is marked complete with recorded verification evidence.

- [ ] **Step 5: Implement locking, atomic replacement, and exact append**

Implement these exact interfaces: `StateStore.create(state: WorkUnitState) -> StateStore`, `load() -> WorkUnitState`, `update(mutation: Callable[[WorkUnitState], None]) -> WorkUnitState`, `update_fields(fields: Mapping[str, object]) -> WorkUnitState`, `append_raw(target: Literal["stdout", "stderr"], data: bytes) -> int`, and `record_progress_claim(claim: dict[str, object], raw_event_offset: int | None) -> ProgressReceipt`.

Use an exclusive lock file beside `work-unit.json`, write JSON to a same-directory temporary file, flush and `os.fsync`, then `os.replace`. `append_raw` must return the byte offset before the append and must never decode then re-encode the evidence file.

- [ ] **Step 6: Add concurrency and crash-safety tests**

Run multiple processes that increment the receipt sequence through `StateStore`; assert no lost updates, valid JSON after every observed replacement, monotonic sequences, and unchanged raw bytes containing non-ASCII UTF-8.

- [ ] **Step 7: Run tests and commit**

Run: `python3 -m unittest tests/test_runner_state.py -v`

Expected: PASS.

```bash
git add shared/claude-runner/work-unit.schema.json shared/claude-runner/runner tests/test_runner_state.py
git commit -m "feat: add atomic Claude work unit state"
```

---

### Task 2: Add the verbatim Progress Claim MCP server

**Files:**
- Create: `shared/claude-runner/runner/progress_mcp.py`
- Create: `tests/fixtures/mcp_client.py`
- Create: `tests/test_runner_progress_mcp.py`
- Modify: `shared/claude-runner/runner/contracts.py`

**Interfaces:**
- Consumes: `StateStore.record_progress_claim()` from Task 1.
- Produces: `serve_progress_mcp(state_dir: Path) -> int` and the tool name `codex_claude_runner.report_progress`.

- [ ] **Step 1: Write failing JSON-RPC tests**

Cover `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, malformed JSON, unknown methods, invalid claim kinds, and exact preservation of `message`, `next_action`, and `evidence_refs`.

```python
response = client.call_tool(
    "codex_claude_runner.report_progress",
    {
        "kind": "verification_claim",
        "message": "1 passed; do not reinterpret",
        "next_action": "await Codex verification",
        "evidence_refs": ["toolu_test"],
    },
)
self.assertFalse(response["result"].get("isError", False))
self.assertEqual(store.load().progress_claims[-1]["claim"]["message"], "1 passed; do not reinterpret")
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests/test_runner_progress_mcp.py -v`

Expected: FAIL because `progress_mcp` does not exist.

- [ ] **Step 3: Implement a minimal stdio MCP server**

Read one UTF-8 JSON-RPC object per newline and write exactly one compact JSON response line for requests. Never log to stdout. Support the current Claude Code legacy initialization flow and return a method-not-supported JSON-RPC error for unsupported future discovery requests so the client can negotiate or fail explicitly rather than hang.

Expose exactly one tool with this input schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["kind", "message", "next_action", "evidence_refs"],
  "properties": {
    "kind": {
      "enum": [
        "segment_started",
        "before_long_operation",
        "verification_claim",
        "segment_completed",
        "blocked",
        "permission_claim",
        "completion_claim"
      ]
    },
    "message": {"type": "string", "minLength": 1},
    "next_action": {"type": "string"},
    "evidence_refs": {"type": "array", "items": {"type": "string"}}
  }
}
```

- [ ] **Step 4: Preserve claims and add trusted receipt metadata**

Validate only the declared schema. Store the exact parsed claim object unchanged; add `work_unit_id`, Runner-assigned sequence, UTC receipt time, and the latest raw-event offset outside `claim`. Return a short acknowledgment containing the receipt sequence, never a summary.

- [ ] **Step 5: Test stdout purity and concurrent writes**

Assert every stdout line is valid JSON-RPC, diagnostic output goes only to stderr, and simultaneous Reporter and Supervisor updates preserve both changes.

- [ ] **Step 6: Run tests and commit**

Run: `python3 -m unittest tests/test_runner_progress_mcp.py tests/test_runner_state.py -v`

Expected: PASS.

```bash
git add shared/claude-runner/runner tests/fixtures/mcp_client.py tests/test_runner_progress_mcp.py
git commit -m "feat: add Claude progress claim reporter"
```

---

### Task 3: Enforce permission stops outside the model prompt

**Files:**
- Create: `shared/claude-runner/runner/permission_hooks.py`
- Create: `tests/test_runner_permission_hooks.py`
- Modify: `shared/claude-runner/runner/contracts.py`
- Modify: `shared/claude-runner/runner/state_store.py`

**Interfaces:**
- Consumes: atomic state updates from Task 1.
- Produces: `build_hook_settings(state_dir: Path, python: Path, entrypoint: Path) -> dict`, `handle_permission_request()`, and `handle_permission_denied()`.

- [ ] **Step 1: Write failing Hook tests**

```python
request = {
    "session_id": "2b30da4c-4a0b-4d77-a5d9-75c785218daf",
    "cwd": "/repo",
    "hook_event_name": "PermissionRequest",
    "tool_name": "mcp__codegraph__explore",
    "tool_input": {"query": "find callers"},
}
result = run_hook("permission-request", request)
self.assertEqual(result["decision"]["behavior"], "deny")
self.assertTrue(result["decision"]["interrupt"])
self.assertEqual(store.load().permissions.pending["tool_input"], {"query": "find callers"})
```

Also assert `PermissionDenied` returns `{"continue": false, "stopReason": "Claude Code permission was denied; execution is stopped for Codex review", "suppressOutput": true}`, malformed input fails closed, and no Hook path edits user or project Claude settings.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests/test_runner_permission_hooks.py -v`

Expected: FAIL because the Hook module does not exist.

- [ ] **Step 3: Generate per-run settings**

Generate settings inside the Work Unit directory with Hook commands that invoke the packaged `claude_runner.py hook permission-request --state-dir <absolute-path>` and `permission-denied`. Quote `sys.executable`, entrypoint, and state directory safely for the host platform. Do not add `PreToolUse`, project settings, or global settings.

- [ ] **Step 4: Implement fail-closed Hook handlers**

Read exactly one JSON object from stdin. Record the unmodified Hook input and receipt metadata before writing the Claude control response. `PermissionRequest` outputs only:

```json
{
  "decision": {
    "behavior": "deny",
    "message": "Permission captured for the Codex Permission Broker",
    "interrupt": true
  },
  "suppressOutput": true
}
```

`PermissionDenied` outputs only:

```json
{
  "continue": false,
  "stopReason": "Claude Code permission was denied; execution is stopped for Codex review",
  "suppressOutput": true
}
```

If state cannot be recorded, return `continue: false`; never allow Claude to continue after an unrecorded permission event.

- [ ] **Step 5: Test exact permission recovery state**

Record the pending request once, reject a second different request while one is pending, and require `approve-permission` to append a narrow rule and clear the exact pending request before the Segment can resume.

- [ ] **Step 6: Run tests and commit**

Run: `python3 -m unittest tests/test_runner_permission_hooks.py tests/test_runner_state.py -v`

Expected: PASS.

```bash
git add shared/claude-runner/runner tests/test_runner_permission_hooks.py
git commit -m "feat: enforce Claude permission interruption"
```

---

### Task 4: Capture stream events and supervise Claude safely

**Files:**
- Create: `shared/claude-runner/runner/stream_capture.py`
- Create: `shared/claude-runner/runner/supervisor.py`
- Create: `tests/fixtures/fake_claude.py`
- Create: `tests/test_runner_supervisor.py`
- Modify: `shared/claude-runner/runner/contracts.py`
- Modify: `shared/claude-runner/runner/state_store.py`

**Interfaces:**
- Consumes: state, Reporter config, and Hook settings from Tasks 1–3.
- Produces: `ClaudeInvocation`, `Supervisor.run() -> int`, `Supervisor.interrupt()`, `Supervisor.terminate()`, and minimal Runner JSONL events.

- [ ] **Step 1: Write a deterministic fake Claude executable**

Support fixture modes selected through `FAKE_CLAUDE_SCENARIO`:

```text
success               valid system, assistant/tool, and final result events
unknown-tool          valid event containing an unrecognized MCP tool payload
permission            invokes the generated PermissionRequest Hook
model-idle            pauses between complete events
tool-idle             emits tool_use and delays its matching result
invalid-json          writes one malformed stdout line
stderr-bytes          writes non-ASCII and invalid UTF-8 bytes to stderr
wrong-session         returns a different Session ID
signal-child          spawns a child so process-group interruption can be tested
```

- [ ] **Step 2: Write failing Supervisor tests**

Assert:

- `raw-events.jsonl` and `raw-stderr.log` equal fixture bytes exactly;
- unknown tool payloads are not copied into Codex-facing Runner events;
- `model_idle`, unmatched tool duration, and total duration emit `TIMEOUT_SUSPECTED` without signaling the process;
- a later event clears only the active observation, not its history;
- explicit interrupt reaches the process group;
- wrong Session, invalid JSON, and missing final result become `backend_failure`;
- a permission Hook stop becomes `permission_required`, not `DONE`.

- [ ] **Step 3: Run the focused test and verify RED**

Run: `python3 -m unittest tests/test_runner_supervisor.py -v`

Expected: FAIL because Supervisor modules do not exist.

- [ ] **Step 4: Build the exact Claude argument vector**

```python
from collections.abc import Sequence


@dataclass(frozen=True)
class ClaudeInvocation:
    executable: Path
    working_root: Path
    session_id: UUID
    resume: bool
    capability: Literal["sonnet", "opus"]
    allowed_tools: Sequence[str]
    reporter_config_json: str
    hook_settings_json: str
    result_schema: Path
    prompt: str

    def argv(self) -> list[str]:
        mode = ["--resume", str(self.session_id)] if self.resume else ["--session-id", str(self.session_id)]
        allowed = [argument for rule in self.allowed_tools for argument in ("--allowedTools", rule)]
        return [
            str(self.executable), "-p", *mode,
            "--model", self.capability,
            "--permission-mode", "acceptEdits",
            *allowed,
            "--output-format", "stream-json",
            "--mcp-config", self.reporter_config_json,
            "--settings", self.hook_settings_json,
            "--json-schema", self.result_schema.read_text(),
            self.prompt,
        ]
```

The argument vector must contain `-p`, exactly one of `--session-id` or `--resume`, `--model`, `--permission-mode acceptEdits`, repeated narrow `--allowedTools`, `--output-format stream-json`, `--mcp-config`, `--settings`, and `--json-schema`. Assert forbidden flags are absent.

- [ ] **Step 5: Implement byte capture before structural parsing**

Use binary pipes. For each complete stdout line, append the original bytes and offset first, then decode strict UTF-8 and parse JSON from a copy. Track only event index, Session ID, final result, and generic `tool_use_id` starts/results. Never parse arbitrary command text, tool semantics, or concrete model usage.

- [ ] **Step 6: Implement heartbeats and warning clocks**

Emit compact Runner events like:

```json
{"type":"runner_event","kind":"heartbeat","process_alive":true,"elapsed_seconds":90,"last_raw_event_at":"2026-08-06T08:00:00Z","last_progress_claim_at":"2026-08-06T07:59:30Z"}
{"type":"runner_event","kind":"timeout_suspected","clock":"tool","tool_use_id":"toolu_123","elapsed_seconds":1800,"raw_event_offset":81}
```

Use conservative defaults of 600 seconds for model-idle observation, 1800 seconds for a tool observation, and 14400 seconds for Work Unit duration; allow Codex to override them when initializing the Work Unit. Crossing a threshold changes Adapter State and emits an observation but sends no signal.

- [ ] **Step 7: Implement explicit process-group control**

Start Claude in a new process group. `interrupt` sends the platform's graceful interrupt; `terminate` sends termination and, after a 15-second grace period, kills only the recorded live group. Control must target the active Runner-owned process, not an arbitrary stored PID. If identity cannot be established, record `backend_failure` and do not signal.

- [ ] **Step 8: Run tests and commit**

Run: `python3 -m unittest tests/test_runner_supervisor.py tests/test_runner_permission_hooks.py -v`

Expected: PASS.

```bash
git add shared/claude-runner/runner tests/fixtures/fake_claude.py tests/test_runner_supervisor.py
git commit -m "feat: supervise Claude stream execution"
```

---

### Task 5: Expose the Work Unit lifecycle CLI

**Files:**
- Create: `shared/claude-runner/claude_runner.py`
- Create: `shared/claude-runner/runner/cli.py`
- Create: `tests/test_runner_cli.py`
- Modify: `shared/claude-runner/runner/supervisor.py`
- Modify: `shared/claude-runner/runner/state_store.py`

**Interfaces:**
- Consumes: all canonical runtime interfaces from Tasks 1–4.
- Produces: stable CLI commands used by both Skills and by the Reporter/Hook subprocesses.

- [ ] **Step 1: Write failing command lifecycle tests**

Exercise this complete sequence with the fake Claude fixture:

```text
init → run → status → permission_required → approve-permission → resume
→ timeout_suspected → extend → run → implementation_complete
→ finish → cleanup
```

Assert `cleanup` fails before `finish`, `finish` does not claim native completion, and every command emits one compact JSON object suitable for Codex parsing.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests/test_runner_cli.py -v`

Expected: FAIL because the CLI does not exist.

- [ ] **Step 3: Implement `init` with root and ignore validation**

`init` accepts an absolute working root, workflow, native reference, fixed point, capability, result schema, initial allowed-tool rules, observation thresholds, and a JSON array of Codex-defined Segments. It must:

1. confirm `git -C <root> rev-parse --show-toplevel` equals the supplied root;
2. confirm `git check-ignore -q .tmp/codex-claude-workflows/probe` succeeds;
3. create only `.tmp/codex-claude-workflows/<uuid>` with user-only directory permissions;
4. create `work-unit.json` atomically and raw files with user-only permissions;
5. keep Reporter and Hook JSON in memory so the three named files remain the only persistent Work Unit files.

It must not edit `.gitignore`; the orchestration Skill's Codex preflight owns that tracked configuration change.

- [ ] **Step 4: Implement lifecycle and control subcommands**

Use these exact command responsibilities:

```text
run/resume              supervise one Segment attempt
status                  read Adapter State without mutation
wait                    print new Runner events until terminal/interrupted
approve-permission      add one Codex-supplied narrow rule and clear the matching request
extend                  update one warning threshold or acknowledge one observation
interrupt/terminate     explicit process-group control
record-verification     optionally append Codex-verified command/status/evidence reference
finish                  mark implementation handoff complete after all Segments
cleanup                 remove exactly the owned UUID directory after native completion is asserted by Codex
report-progress         serve the Reporter MCP subprocess
hook                    run one permission Hook subprocess
```

- [ ] **Step 5: Implement resumable Segment and Repair Segment rules**

`resume` must require the recorded Session ID for the active Segment. A new Session requires a distinct next Segment already defined by Codex. Add `add-repair-segment` as a Codex-only command accepting scope, finding identifiers, verification commands, and capability; it must not decide finding ownership itself.

- [ ] **Step 6: Implement exact cleanup ownership**

Before removal, resolve real paths and assert the target matches:

```text
<validated-working-root>/.tmp/codex-claude-workflows/<state.work_unit_id>
```

Reject symlinks, parent traversal, an ID mismatch, an active process, or missing Codex assertion `--native-workflow-complete`. Remove no parent directory.

- [ ] **Step 7: Run tests and commit**

Run: `python3 -m unittest tests/test_runner_cli.py tests/test_runner_supervisor.py -v`

Expected: PASS.

```bash
git add shared/claude-runner tests/test_runner_cli.py
git commit -m "feat: add Claude Runner lifecycle CLI"
```

---

### Task 6: Package exact standalone Runner copies

**Files:**
- Create: `scripts/sync_shared_assets.py`
- Delete: `scripts/sync_shared_references.py`
- Create: `skills/superpowers-claude-workflow/scripts/claude-runner/`
- Create: `skills/matt-claude-workflow/scripts/claude-runner/`
- Modify: `scripts/validate_skill_packages.py`
- Modify: `tests/test_workflow_contracts.py`

**Interfaces:**
- Consumes: complete canonical runtime from Tasks 1–5.
- Produces: independently runnable hard copies in both Skill packages.

- [ ] **Step 1: Replace the existing copy-consistency test with a general asset test**

Assert the canonical permission broker equals both reference copies and recursively compare the canonical Runner tree against both packaged trees by relative path and bytes. Assert no symlink exists anywhere in either Skill package.

- [ ] **Step 2: Run the contract test and verify RED**

Run: `python3 -m unittest tests/test_workflow_contracts.py -v`

Expected: FAIL because `sync_shared_assets.py` and packaged runtimes do not exist.

- [ ] **Step 3: Implement deterministic asset synchronization**

`sync_shared_assets.py` must:

- copy `shared/claude-permission-broker.md` to both reference targets;
- mirror the canonical Runner tree to both Skill `scripts/claude-runner` targets;
- remove stale files only inside those two owned Runner target directories;
- preserve executable mode on `claude_runner.py`;
- make `--check` read-only and report every missing, stale, extra, mode-mismatched, or symlinked path.

- [ ] **Step 4: Extend package validation**

Require `scripts/claude-runner/claude_runner.py`, `work-unit.schema.json`, every runner module, and the existing result schema. Run each packaged entry point with `--help` and fail if it imports outside the package or needs a third-party module.

- [ ] **Step 5: Generate hard copies and rerun tests**

Run:

```bash
python3 scripts/sync_shared_assets.py
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
python3 -m unittest tests/test_workflow_contracts.py -v
```

Expected: all commands PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts shared/claude-runner skills/superpowers-claude-workflow/scripts skills/matt-claude-workflow/scripts tests/test_workflow_contracts.py
git commit -m "build: package shared Claude Runner"
```

---

### Task 7: Route both orchestration Skills through the Runner

**Files:**
- Modify: `skills/superpowers-claude-workflow/SKILL.md`
- Modify: `skills/superpowers-claude-workflow/references/claude-execution-protocol.md`
- Modify: `skills/superpowers-claude-workflow/references/executor-contract.md`
- Modify: `skills/matt-claude-workflow/SKILL.md`
- Modify: `skills/matt-claude-workflow/references/claude-execution-protocol.md`
- Modify: `skills/matt-claude-workflow/references/executor-contract.md`
- Modify: `skills/matt-claude-workflow/references/matt-lifecycle-adapter.md`
- Modify: `tests/test_workflow_contracts.py`

**Interfaces:**
- Consumes: packaged CLI from Task 6.
- Produces: framework-specific adapter instructions with no direct Claude invocation.

- [ ] **Step 1: Write failing Skill boundary tests**

Assert both Skills:

- invoke their own packaged `scripts/claude-runner/claude_runner.py`;
- require Codex to add `/.tmp/` to `.gitignore` before the fixed point when absent;
- define Execution Segments only during dispatch, never in the native Plan/Spec/Ticket;
- state that Runner `implementation_complete` is not native completion;
- preserve all existing native Review and finishing requirements;
- contain no direct `--output-format json` Claude recipe or prompt-dependent denial instruction;
- never use `--strict-mcp-config`, partial messages, bypass permissions, or a global settings path.

- [ ] **Step 2: Run the contract test and verify RED**

Run: `python3 -m unittest tests/test_workflow_contracts.py -v`

Expected: FAIL on the old direct invocation and old state assertions.

- [ ] **Step 3: Update the Superpowers adapter**

Keep brainstorming, Design, writing-plans, SDD, per-Task Review, Final Review, verification, and branch finishing unchanged. Replace `task-N-claude-state.json` and direct CLI language with one Runner Work Unit per Claude-owned native Task. Tell Codex to define one or more Execution Segments at dispatch and to clean the UUID directory only after native finishing.

For Review fixes, map a finding to the relevant Segment Session; create a Repair Segment for cross-Segment findings. Preserve the existing Superpowers round 1–5 and capability-upgrade rules inside that routing decision.

- [ ] **Step 4: Update the Matt adapter**

Keep Spec, Ticket/implicit-task, fixed point, TDD seams, the compatibility checkpoint required by commit-range `code-review`, and the two-axis `code-review`. Let the Native Workflow decide Review disposition, fixes, and any operations defined by the configured Tracker. Store no Runner state in the Tracker.

When the Native Workflow routes a single-Segment finding back to implementation, resume that Session. For cross-Segment findings, let Codex add a Repair Segment; do not add Final Review or Verify Review.

- [ ] **Step 5: Replace prompt-dependent permissions with Runner semantics**

Document that Hook capture is authoritative for permission stops. Retain the Permission Broker's classification rules, but apply approved rules through `approve-permission` and `resume`. A malformed Hook, Reporter, stream, or Session is a backend failure and never a Codex implementation fallback.

- [ ] **Step 6: Run contract tests and sync copies**

Run:

```bash
python3 scripts/sync_shared_assets.py
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
python3 -m unittest tests/test_workflow_contracts.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skills tests/test_workflow_contracts.py
git commit -m "feat: route workflows through Claude Runner"
```

---

### Task 8: Complete deterministic end-to-end regression coverage

**Files:**
- Modify: `tests/fixtures/fake_claude.py`
- Modify: `tests/test_runner_cli.py`
- Modify: `tests/test_runner_supervisor.py`
- Create: `tests/test_runner_end_to_end.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: full packaged Runner and both Skill contracts.
- Produces: evidence that the new adapter handles success, permissions, warnings, recovery, and cleanup without a live model.

- [ ] **Step 1: Write two native-shaped fake workflows**

Create one fixture Work Unit shaped like a Superpowers Plan Task and one shaped like a Matt Ticket. Give both the same small implementation brief and two Segments so behavioral differences come only from native lifecycle metadata.

- [ ] **Step 2: Exercise the complete Superpowers-shaped path**

Verify init, Segment 1, a safe permission interruption and resume, Segment 2 with a fresh Session, declared tests, Codex-recorded verification, implementation handoff, preserved native Review marker, native-completion assertion, and exact UUID cleanup.

- [ ] **Step 3: Exercise the complete Matt-shaped path**

Verify fixed-point preservation, Segment implementation, local checkpoint commit evidence, an accepted Review finding routed to a Repair Segment, second verification, implementation handoff, preserved Tracker ownership, and exact UUID cleanup.

- [ ] **Step 4: Exercise every backend failure**

Cover missing executable, wrong Session, resume failure, malformed stream, Hook write failure, Reporter failure, state corruption, unsafe process identity, authentication/quota-style nonzero results, and an attempted Codex fallback. Assert state remains and cleanup is rejected.

- [ ] **Step 5: Update README**

Document:

- hard-copy installation unchanged;
- Python 3 and Claude CLI preflight;
- one-time tracked `/.tmp/` ignore entry;
- Progress Claim versus Runtime Fact versus Execution Evidence;
- default compact output and on-demand raw evidence;
- timeout suspicion and Codex control;
- permission broker behavior;
- recovery and cleanup commands;
- no global hooks, daemon, plugin, or upstream Skill changes.

- [ ] **Step 6: Run the deterministic suite twice**

Run:

```bash
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s tests -v
git diff --check
```

Expected: both complete test runs PASS, package validation PASS, copy check PASS, and `git diff --check` produces no output.

- [ ] **Step 7: Commit**

```bash
git add README.md tests
git commit -m "test: cover Claude Runner workflows"
```

---

### Task 9: Run authorized live regressions and finalize documentation

**Files:**
- Create: `docs/superpowers/plans/2026-08-06-shared-runner-live-regression.md`
- Modify: `README.md` only if the live run reveals a reproducible setup requirement.

**Interfaces:**
- Consumes: complete deterministic implementation from Tasks 1–8.
- Produces: real Claude Code evidence for one Superpowers and one Matt workflow without changing their native lifecycle contracts.

- [ ] **Step 1: Obtain explicit live-run authorization**

Present the identical small implementation requirement, requested Capability Model, expected two Claude runs, repository/worktree locations, and allowed command families. Do not run a live model without cost and permission confirmation.

- [ ] **Step 2: Run the Superpowers workflow**

Use the explicit `superpowers-claude-workflow` Skill, preserve native SDD state and Reviews, and record only outcome, elapsed time, Progress Claim count, permission interruptions, Session count, tests, commits, and native completion evidence in the regression document.

- [ ] **Step 3: Run the equivalent Matt workflow**

Use the explicit `matt-claude-workflow` Skill with the same implementation requirement and capability. Preserve its fixed point, two-axis Review, user-controlled fixes, commit, and Tracker or implicit-task semantics.

- [ ] **Step 4: Compare behavior, not implementation text**

Assert both runs used the Runner, exposed progress, preserved raw evidence until native completion, required no avoidable user permission prompt, and cleaned only their own UUID directories. Do not require Claude to produce byte-identical code.

- [ ] **Step 5: Run final repository verification**

Run:

```bash
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
python3 -m json.tool shared/claude-runner/work-unit.schema.json
python3 -m json.tool skills/superpowers-claude-workflow/references/claude-result.schema.json
python3 -m json.tool skills/matt-claude-workflow/references/claude-result.schema.json
python3 -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected: validation and tests PASS; diff check is empty; status lists only intentional implementation and evidence-document changes.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-08-06-shared-runner-live-regression.md README.md
git commit -m "docs: record shared Runner regression"
```
