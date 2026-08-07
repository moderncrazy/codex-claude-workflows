# Runner P0 State, Permission Resolution, and Finish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Runner state consistent, add auditable deny/dismiss permission resolution, and require an explicit native-completion transition to `finished` before cleanup.

**Architecture:** Upgrade persisted Work Units to schema version 2 at the `StateStore` seam, then make the Supervisor own atomic invocation start/end state and make the CLI own explicit permission and native-finish transitions. Keep the canonical implementation under `shared/claude-runner/`, synchronize exact copies into both workflow skills only after the shared tests pass, and preserve native Superpowers and Matt lifecycle ownership.

**Tech Stack:** Python 3 standard library, `unittest`, JSON Schema draft 7, Claude Code stream-json test fixture, Git.

## Global Constraints

- Implement only state consistency, `deny-permission`, `dismiss-permission`, and `finished`; do not add capability permissions or other deferred feedback items.
- Keep native Superpowers and Matt review, verification, commit, tracker, and branch-finishing order unchanged.
- Treat `timeout_suspected` as a runtime observation while the Work Unit stays `running`.
- Keep schema-version-1 Work Units loadable through deterministic migration.
- Use `apply_patch` for source and documentation edits.
- Modify the canonical shared Runner first; update packaged Runner copies only through `python3 scripts/sync_shared_assets.py`.

---

### Task 1: Schema-Version-2 Contract and Migration

**Files:**
- Modify: `shared/claude-runner/runner/contracts.py`
- Modify: `shared/claude-runner/runner/state_store.py`
- Modify: `shared/claude-runner/work-unit.schema.json`
- Modify: `tests/test_runner_state.py`

**Interfaces:**
- Produces: `upgrade_state_dict(value: Mapping[str, Any]) -> dict[str, Any]` in `runner.contracts`.
- Produces: schema-version-2 `WorkUnitState.from_dict` validation.
- Produces: Segment `resume_count: int` and permissions `resolved: list[dict[str, object]]`.
- Consumes: existing `StateStore.load()` and `StateStore.update()` callers without changing their signatures.

- [ ] **Step 1: Convert the shared state fixture to schema version 2**

Change `sample_work_unit` in `tests/test_runner_state.py` to use:

```python
"schema_version": 2,
"segments": [{
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
}],
"permissions": {"initial": [], "approved": [], "pending": None, "resolved": []},
```

- [ ] **Step 2: Add failing migration and contract tests**

Add tests that write raw schema-version-1 JSON to a created state directory and assert `StateStore.load()` returns version 2:

```python
def test_schema_version_one_is_migrated_before_validation(self) -> None:
    legacy = sample_work_unit(Path(tempfile.gettempdir())).to_dict()
    legacy["schema_version"] = 1
    legacy["permissions"].pop("resolved")
    legacy["segments"][0].pop("resume_count")
    legacy["segments"][0]["session_id"] = "37af868d-e830-42ca-94dd-a5523d30f616"
    legacy["segments"][0]["attempt"] = 0

    migrated = upgrade_state_dict(legacy)

    self.assertEqual(migrated["schema_version"], 2)
    self.assertEqual(migrated["segments"][0]["attempt"], 1)
    self.assertEqual(migrated["segments"][0]["resume_count"], 0)
    self.assertEqual(migrated["permissions"]["resolved"], [])
```

Add focused cases for:

```python
legacy["status"] = "timeout_suspected"
self.assertEqual(upgrade_state_dict(legacy)["status"], "running")

legacy["permissions"]["pending"] = {
    "request": {"tool_name": "Bash"},
    "tool_name": "Bash",
    "tool_input": {"command": "pytest"},
    "received_at": "2026-08-06T00:00:00Z",
}
legacy["segments"][0]["status"] = "permission_required"
self.assertEqual(upgrade_state_dict(legacy)["permissions"]["pending"]["segment_id"], "segment-1")
```

Also assert ambiguous pending migration raises `ContractError` and version 2 rejects the removed `timeout_suspected` and `cleaned` statuses.

- [ ] **Step 3: Run the state tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_state -v
```

Expected: failures because schema version 2, `resume_count`, `resolved`, and `upgrade_state_dict` are not implemented.

- [ ] **Step 4: Implement deterministic migration and the v2 contract**

In `contracts.py`, define the v2 statuses and transition graph:

```python
class WorkUnitStatus(str, Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    PERMISSION_REQUIRED = "permission_required"
    INTERRUPTED = "interrupted"
    BACKEND_FAILURE = "backend_failure"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    FINISHED = "finished"
```

Permit these required transitions:

```python
WorkUnitStatus.PERMISSION_REQUIRED: {
    WorkUnitStatus.INTERRUPTED,
    WorkUnitStatus.BACKEND_FAILURE,
},
WorkUnitStatus.IMPLEMENTATION_COMPLETE: {
    WorkUnitStatus.RUNNING,
    WorkUnitStatus.FINISHED,
},
WorkUnitStatus.FINISHED: set(),
```

Add `resume_count` to `SEGMENT_FIELDS` and require permissions to contain exactly `initial`, `approved`, `pending`, and `resolved`. Validate both counters as non-negative integers and validate `resolved` as an array.

Implement migration as a pure copy-and-transform function:

```python
def upgrade_state_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(dict(value))
    if data.get("schema_version") == 2:
        return data
    if data.get("schema_version") != 1:
        raise ContractError("unsupported schema_version")
    data["schema_version"] = 2
    data["permissions"]["resolved"] = []
    for segment in data["segments"]:
        segment["resume_count"] = 0
        if segment.get("session_id") is not None and segment.get("attempt") == 0:
            segment["attempt"] = 1
    if data.get("status") == "timeout_suspected":
        data["status"] = "running"
    elif data.get("status") == "cleaned":
        data["status"] = "finished"
    pending = data["permissions"].get("pending")
    if pending is not None and "segment_id" not in pending:
        candidates = [
            segment["segment_id"]
            for segment in data["segments"]
            if segment["status"] == "permission_required"
        ]
        if len(candidates) != 1:
            raise ContractError("legacy pending permission does not identify one Segment")
        pending["segment_id"] = candidates[0]
    data["runtime"].setdefault("result_history", [])
    return data
```

Call `upgrade_state_dict` before `WorkUnitState.from_dict` validation in `StateStore.load()`. New state creation must already pass version-2 data.

- [ ] **Step 5: Update the canonical JSON Schema**

Set `schema_version` to `2`; replace the Work Unit status enum; require Segment `resume_count`; and require permission `resolved`:

```json
"status": {
  "enum": [
    "initialized", "running", "permission_required", "interrupted",
    "backend_failure", "implementation_complete", "finished"
  ]
}
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_state -v
python3 -m json.tool shared/claude-runner/work-unit.schema.json
```

Expected: all state tests pass and JSON formatting validation exits 0.

- [ ] **Step 7: Commit the schema and migration**

```bash
git add shared/claude-runner/runner/contracts.py shared/claude-runner/runner/state_store.py shared/claude-runner/work-unit.schema.json tests/test_runner_state.py
git commit -m "feat: migrate runner state to schema v2"
```

---

### Task 2: Atomic Invocation State, Current Result, and Counters

**Files:**
- Modify: `shared/claude-runner/runner/cli.py`
- Modify: `shared/claude-runner/runner/supervisor.py`
- Modify: `tests/test_runner_supervisor.py`
- Modify: `tests/test_runner_cli.py`
- Modify: `tests/test_runner_end_to_end.py`

**Interfaces:**
- Consumes: version-2 Work Unit and Segment fields from Task 1.
- Produces: `ClaudeInvocation.is_resume: bool` through the existing `resume` field.
- Produces: top-level `result` scoped to the current invocation and `runtime.result_history` entries.
- Produces: exact Segment end states for success, permission, interruption, and backend failure.

- [ ] **Step 1: Add failing Supervisor lifecycle tests**

Extend `tests/test_runner_supervisor.py` with assertions such as:

```python
def test_backend_failure_clears_prior_result_and_fails_segment(self) -> None:
    with tempfile.TemporaryDirectory() as directory:
        store, supervisor, _ = self.make_supervisor(Path(directory), "invalid-json")
        store.update(lambda state: state.data.__setitem__("result", {"status": "DONE", "summary": "stale"}))

        self.assertNotEqual(supervisor.run(), 0)

        state = store.load()
        self.assertIsNone(state.result)
        self.assertEqual(state.status, "backend_failure")
        self.assertEqual(state.segments[0]["status"], "failed")
```

Add outcome assertions:

```python
self.assertEqual(permission_state.segments[0]["status"], "permission_required")
self.assertEqual(interrupted_state.segments[0]["status"], "interrupted")
self.assertEqual(success_state.segments[0]["status"], "complete")
```

Add a timeout assertion that every observed state remains `running` until another lifecycle outcome occurs.

- [ ] **Step 2: Add failing attempt/resume tests**

Update the existing permission-resume end-to-end expectation from `[2, 1]` to:

```python
self.assertEqual([segment["attempt"] for segment in second["segments"]], [1, 1])
self.assertEqual([segment["resume_count"] for segment in second["segments"]], [1, 0])
```

Add a restart assertion:

```python
self.assertEqual(completed["segments"][0]["attempt"], 2)
self.assertEqual(completed["segments"][0]["resume_count"], 0)
```

- [ ] **Step 3: Run lifecycle tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_supervisor tests.test_runner_end_to_end -v
```

Expected: failures show stale `result`, Segment `running` after failures, timeout status mutation, and incorrect attempt counting.

- [ ] **Step 4: Initialize version-2 state in the CLI**

In `_init`, create:

```python
"schema_version": 2,
"permissions": {
    "initial": list(args.allowed_tool),
    "approved": [],
    "pending": None,
    "resolved": [],
},
"runtime": {"configuration": configuration, "result_history": []},
```

Add `resume_count: 0` to `_segments` and `_add_repair`.

- [ ] **Step 5: Make invocation reservation clear the current result**

In `Supervisor._reserve_launch`, before recording the new active run:

```python
state.data["result"] = None
```

Keep stale active-run diagnostics, but only after the active lease proves no other live Runner owns the Work Unit.

- [ ] **Step 6: Count attempts and resumes separately**

In `_set_running`, replace unconditional attempt increment with:

```python
if self.invocation.resume:
    segment["resume_count"] += 1
else:
    segment["attempt"] += 1
segment["status"] = "running"
segment["started_at"] = segment["started_at"] or utc_now()
segment["finished_at"] = None
```

- [ ] **Step 7: Centralize invocation cleanup and Segment outcomes**

Add a private helper that clears runtime process identity and updates the target Segment by Session ID:

```python
def _finish_invocation_state(self, state: object, segment_status: str) -> dict[str, object]:
    state.runtime["pid"] = None
    state.runtime["process_group_id"] = None
    state.runtime["active_run"] = None
    segment = next(
        item for item in state.segments
        if item["session_id"] == self.invocation.session_id
    )
    segment["status"] = segment_status
    if segment_status in {"complete", "failed"}:
        segment["finished_at"] = utc_now()
    return segment
```

Use it from `_permission_required`, `_interrupted`, `_backend_failure`, `_complete`, and `_continuation_required`. Backend failure must set Segment `failed`; permission must set `permission_required`; interruption must set `interrupted`.

Remove Work Unit transitions to and from `timeout_suspected`; retain only event emission and `runtime.timeout_observations`.

- [ ] **Step 8: Record accepted structured result history**

When storing any validated structured result, append:

```python
state.runtime.setdefault("result_history", []).append({
    "segment_id": segment["segment_id"],
    "session_id": self.invocation.session_id,
    "launch_token": self.launch_token,
    "result": result,
    "recorded_at": utc_now(),
})
```

The current `result` is set only for the current invocation. Failures without a validated structured result leave it null.

- [ ] **Step 9: Run focused lifecycle tests and verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_supervisor tests.test_runner_cli tests.test_runner_end_to_end -v
```

Expected: all three modules pass.

- [ ] **Step 10: Commit atomic invocation state**

```bash
git add shared/claude-runner/runner/cli.py shared/claude-runner/runner/supervisor.py tests/test_runner_supervisor.py tests/test_runner_cli.py tests/test_runner_end_to_end.py
git commit -m "fix: make runner invocation state consistent"
```

---

### Task 3: Approve, Deny, and Dismiss Permission Resolution

**Files:**
- Modify: `shared/claude-runner/runner/cli.py`
- Modify: `shared/claude-runner/runner/permission_hooks.py`
- Modify: `tests/test_runner_cli.py`
- Modify: `tests/test_runner_permission_hooks.py`

**Interfaces:**
- Consumes: permissions `resolved` and pending `segment_id` from Task 1.
- Produces: CLI commands `deny-permission` and `dismiss-permission`.
- Produces: a common `_resolve_permission` mutation for approved, denied, and dismissed outcomes.

- [ ] **Step 1: Add failing Hook attribution tests**

Prepare the fixture Segment as running with a Session ID, invoke `handle_permission_request`, and assert:

```python
self.assertEqual(store.load().permissions["pending"]["segment_id"], "segment-1")
```

Add a failure case where no unique running Segment exists; the Hook must fail closed and must not create an unattributed pending request.

- [ ] **Step 2: Add failing CLI permission-resolution tests**

Add table-driven CLI cases for `deny-permission` and `dismiss-permission`:

```python
resolved = self.run_cli(
    action,
    "--state-dir", str(state_dir),
    "--expected-tool-name", "Bash",
    "--reason", "use the declared project command instead",
)
self.assertEqual(resolved["status"], "interrupted")
self.assertIsNone(resolved["permissions"]["pending"])
self.assertEqual(resolved["permissions"]["resolved"][-1]["resolution"], expected_resolution)
self.assertEqual(resolved["segments"][0]["status"], "interrupted")
```

Update approval expectations to `interrupted` and assert its audit record. Verify all three resolutions can be followed by `resume` on the same Session. Verify absent pending and tool mismatch leave serialized state unchanged.

- [ ] **Step 3: Run permission tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_permission_hooks tests.test_runner_cli -v
```

Expected: failures because pending requests lack Segment attribution, deny/dismiss commands do not exist, and approval still transitions to `running`.

- [ ] **Step 4: Attribute Hook permissions to one running Segment**

In `handle_permission_request`, select exactly one Segment with status `running` and include its ID:

```python
candidates = [segment for segment in state.segments if segment["status"] == "running"]
if len(candidates) != 1:
    raise InvalidTransition("permission request does not identify one running Segment")
state.permissions["pending"] = {
    "segment_id": candidates[0]["segment_id"],
    "request": request,
    "tool_name": request.get("tool_name"),
    "tool_input": request.get("tool_input"),
    "received_at": utc_now(),
}
```

In `_continuation_required`, set the same field from the Segment selected by the invocation Session ID.

- [ ] **Step 5: Add CLI parsers for deny and dismiss**

Register both commands with:

```python
for name in ("deny-permission", "dismiss-permission"):
    command = commands.add_parser(name)
    command.add_argument("--state-dir", required=True, type=Path)
    command.add_argument("--expected-tool-name", required=True)
    command.add_argument("--reason", required=True)
```

- [ ] **Step 6: Implement one atomic resolution helper**

Implement a helper shaped as:

```python
def _resolve_permission(
    store: StateStore,
    *,
    expected_tool_name: str,
    resolution: str,
    reason: str | None,
    allow_rule: str | None,
) -> None:
```

Inside one `store.update` call:

1. require pending;
2. match the exact tool name;
3. locate `pending["segment_id"]`;
4. append the allow rule only for approval;
5. append an audit record containing resolution, reason, original request, Segment ID, and timestamp;
6. clear pending;
7. set the Segment to `interrupted`;
8. transition Work Unit `permission_required` to `interrupted`.

Use the helper from approval, denial, and dismissal. A mismatch must raise before any mutation.

- [ ] **Step 7: Run permission tests and verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_permission_hooks tests.test_runner_cli -v
```

Expected: all permission tests pass.

- [ ] **Step 8: Commit permission resolution**

```bash
git add shared/claude-runner/runner/cli.py shared/claude-runner/runner/permission_hooks.py tests/test_runner_cli.py tests/test_runner_permission_hooks.py
git commit -m "feat: resolve runner permissions without approval"
```

---

### Task 4: Explicit Finished State, Safe Cleanup, Documentation, and Packaging

**Files:**
- Modify: `shared/claude-runner/runner/cli.py`
- Modify: `tests/test_runner_cli.py`
- Modify: `tests/test_runner_end_to_end.py`
- Modify: `tests/test_workflow_contracts.py`
- Modify: `README.md`
- Modify: `shared/claude-permission-broker.md`
- Modify: `skills/superpowers-claude-workflow/SKILL.md`
- Modify: `skills/superpowers-claude-workflow/references/claude-execution-protocol.md`
- Modify: `skills/matt-claude-workflow/SKILL.md`
- Modify: `skills/matt-claude-workflow/references/claude-execution-protocol.md`
- Generated by sync: `skills/superpowers-claude-workflow/references/claude-permission-broker.md`
- Generated by sync: `skills/matt-claude-workflow/references/claude-permission-broker.md`
- Generated by sync: `skills/superpowers-claude-workflow/scripts/claude-runner/**`
- Generated by sync: `skills/matt-claude-workflow/scripts/claude-runner/**`

**Interfaces:**
- Consumes: `WorkUnitStatus.FINISHED` from Task 1.
- Produces: `finish --native-workflow-complete` transition and cleanup's strict `finished` precondition.
- Preserves: native workflow ownership and existing safe cleanup target validation.

- [ ] **Step 1: Add failing finish and cleanup tests**

Update lifecycle tests to require:

```python
missing = self.run_cli("finish", "--state-dir", str(state_dir), expected=2)
self.assertEqual(missing["error"], "native_completion_required")

finished = self.run_cli(
    "finish", "--state-dir", str(state_dir), "--native-workflow-complete"
)
self.assertEqual(finished["status"], "finished")

cleaned = self.run_cli("cleanup", "--state-dir", str(state_dir))
self.assertEqual(cleaned["status"], "cleaned")
```

Also assert cleanup directly from `implementation_complete` returns `finish_required`, finish is rejected with pending permission or incomplete Segments, and adding or reopening a Segment after `finished` is rejected.

- [ ] **Step 2: Run finish tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_cli tests.test_runner_end_to_end -v
```

Expected: failures because finish does not require the assertion or transition state, and cleanup still treats its own assertion as sufficient.

- [ ] **Step 3: Implement the explicit finish transition**

Add the finish parser flag:

```python
finish.add_argument("--native-workflow-complete", action="store_true")
```

In `_finish`, reject a missing assertion before mutation. Under `inactive_lease_guard`, require `implementation_complete`, all Segments complete, and no pending permission, then:

```python
state.transition_to(WorkUnitStatus.FINISHED)
state.runtime["finished_at"] = utc_now()
```

Remove `implementation_handoff_at` as an authorization mechanism.

- [ ] **Step 4: Require finished before cleanup**

Keep all path, UUID, symlink, repository-root, and inactive-lease checks. Replace cleanup's lifecycle precondition with:

```python
if state.status != "finished":
    raise CliError("finish_required", "finish must record native completion before cleanup")
```

The parser may continue accepting the old cleanup assertion flag for one compatibility window, but `_cleanup` must ignore it and it must never bypass `finished`.

- [ ] **Step 5: Prevent post-finish reopening**

Ensure `_run`, completed-Segment reopen, `_add_repair`, and `restart-segment-session` reject `finished` with `work_unit_finished`. This keeps `finished` terminal and forces Codex to finish only after all native repair loops.

- [ ] **Step 6: Update workflow documentation and contract tests**

Document the exact flow in both workflow packages:

```text
implementation_complete
→ native Review, verification, commits/tracker/branch finishing
→ finish --native-workflow-complete
→ finished
→ cleanup
```

Document `approve-permission`, `deny-permission`, and `dismiss-permission`, including the required explicit resume. Preserve the statement that Runner state never gates or replaces native Review.

Update `tests/test_workflow_contracts.py` assertions so both skills require the new finish flow and permission-resolution commands.

- [ ] **Step 7: Synchronize the canonical Runner into both skills**

Run:

```bash
python3 scripts/sync_shared_assets.py
```

This is the only step that modifies the packaged `scripts/claude-runner/` trees.

- [ ] **Step 8: Run the complete verification suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
python3 -m json.tool shared/claude-runner/work-unit.schema.json
git diff --check
```

Expected:

- all unit and end-to-end tests pass;
- shared and packaged Runner trees are byte-identical;
- both skill packages validate;
- JSON schema parses;
- no whitespace errors are reported.

- [ ] **Step 9: Commit finish, documentation, and packaged assets**

```bash
git add README.md shared/claude-runner shared/claude-permission-broker.md skills/superpowers-claude-workflow skills/matt-claude-workflow tests/test_runner_cli.py tests/test_runner_end_to_end.py tests/test_workflow_contracts.py
git commit -m "feat: finish runner work units explicitly"
```

---

## Final Self-Review

- [ ] Confirm the implementation diff contains no capability-policy, command-normalization, observability, verification-profile, owned-file, or threat-profile work.
- [ ] Confirm `implementation_complete` still precedes native Superpowers and Matt review/verification completion.
- [ ] Confirm Matt remains review-before-commit.
- [ ] Confirm schema-version-1 migration never edits native workflow files.
- [ ] Confirm no successful or failed invocation can leave its Segment `running`.
- [ ] Confirm no cleanup path can bypass `finished`.
