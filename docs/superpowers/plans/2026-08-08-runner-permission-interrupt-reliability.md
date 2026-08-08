# Runner Permission and Interrupt Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real Claude Code `PermissionDenied` events resolvable by the existing permission broker and bound public interrupt completion with staged signal escalation.

**Architecture:** Keep one canonical Runner under `shared/claude-runner`. Promote `PermissionDenied` into the existing pending-permission record without interpreting model text, and generalize the Supervisor's control deadline into an action/stage machine. Synchronize the verified canonical tree into both standalone skill packages only after canonical tests pass.

**Tech Stack:** Python 3 standard library, `unittest`, POSIX process groups/signals with the existing Windows fallback, Claude Code print mode and Hooks.

## Global Constraints

- Preserve native Matt and Superpowers routing, review, Tracker, and commit behavior.
- Preserve the existing Work Unit status enum; do not add `interrupting`.
- Preserve exact raw Hook requests; do not parse model natural language.
- Keep `PermissionRequest` behavior and `terminate` semantics backward compatible.
- Reuse `termination_grace_seconds` for both interrupt escalation stages; default 15 seconds each.
- Modify `shared/claude-runner` first; packaged files must be exact hard copies produced by `scripts/sync_shared_assets.py`.
- Add no persistent real-regression artifacts to the repository.

---

### Task 1: Promote `PermissionDenied` into the broker

**Files:**
- Modify: `tests/test_runner_permission_hooks.py`
- Modify: `tests/fixtures/fake_claude.py`
- Modify: `tests/test_runner_supervisor.py`
- Modify: `tests/test_runner_cli.py`
- Modify: `shared/claude-runner/runner/permission_hooks.py`

**Interfaces:**
- Consumes: `StateStore.update`, Hook stdin/stdout JSON, and the existing pending-permission object.
- Produces: `handle_permission_denied(...) -> int` that records one exact pending request for one running Segment before stopping Claude.

- [ ] **Step 1: Write Hook-level failing tests**

In `tests/test_runner_permission_hooks.py`, invoke `handle_permission_denied` against `self.running_store(...)` with:

```python
request = {
    "session_id": "2b30da4c-4a0b-4d77-a5d9-75c785218daf",
    "cwd": "/repo",
    "hook_event_name": "PermissionDenied",
    "tool_name": "Bash",
    "tool_input": {"command": "git status --short"},
}
```

Assert the existing stop response, then assert the pending object preserves `segment-1`, the exact request, tool name, and tool input. Add cases proving a second denial cannot overwrite pending state and a denial without exactly one running Segment fails closed.

- [ ] **Step 2: Add the fake-Claude, Supervisor, and CLI failing tests**

Add `permission-denied` to `tests/fixtures/fake_claude.py`. It invokes the `PermissionDenied` command from `--settings` with the Bash request and exits 3.

Add `test_permission_denied_hook_stop_is_brokered` to `tests/test_runner_supervisor.py`; assert a nonzero run, Work Unit and Segment `permission_required`, and the exact pending command.

Add `test_permission_denied_can_be_dismissed_then_same_session_resumed` to `tests/test_runner_cli.py`. Run the denied fixture, capture Session ID, call `dismiss-permission --expected-tool-name Bash --reason "use the approved command"`, resume with the success fixture, and assert pending cleared, audit resolution `dismissed`, Session unchanged, `attempt == 1`, and `resume_count == 1`.

- [ ] **Step 3: Verify RED across all three boundaries**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_runner_permission_hooks \
  tests.test_runner_supervisor.SupervisorTests.test_permission_denied_hook_stop_is_brokered \
  tests.test_runner_cli.RunnerCliTests.test_permission_denied_can_be_dismissed_then_same_session_resumed -v
```

Expected: Hook state remains `None`, the Supervisor reports backend failure instead of pending permission, and the CLI cannot dismiss the absent request.

- [ ] **Step 4: Implement one common pending mutation**

In `shared/claude-runner/runner/permission_hooks.py`, extract the current `PermissionRequest` state mutation into `_record_pending_permission(state, request)`. It must reject an existing pending request, require exactly one running Segment, and write:

```python
{
    "segment_id": candidates[0]["segment_id"],
    "request": request,
    "tool_name": request.get("tool_name"),
    "tool_input": request.get("tool_input"),
    "received_at": utc_now(),
}
```

Use it from both handlers. `handle_permission_denied` must retain `runtime.last_permission_denied`, and output `PERMISSION_DENIED_RESPONSE` only after the atomic update succeeds.

- [ ] **Step 5: Verify GREEN across all three boundaries**

Run the Step 3 command. Expected: all new tests pass.

- [ ] **Step 6: Run Task 1 regression tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_permission_hooks tests.test_runner_supervisor tests.test_runner_cli -v
```

Expected: all selected tests pass without warnings or leaked children.

- [ ] **Step 7: Inspect the Task 1 diff**

```bash
git diff --check
git diff -- shared/claude-runner/runner/permission_hooks.py tests/test_runner_permission_hooks.py tests/fixtures/fake_claude.py tests/test_runner_supervisor.py tests/test_runner_cli.py
```

Expected: only the pending-permission correction and its tests are present.

- [ ] **Step 8: Commit Task 1**

```bash
git add shared/claude-runner/runner/permission_hooks.py tests/test_runner_permission_hooks.py tests/fixtures/fake_claude.py tests/test_runner_supervisor.py tests/test_runner_cli.py
git commit -m "fix: broker real Claude permission denials"
```

---

### Task 2: Bound interrupt completion

**Files:**
- Modify: `tests/fixtures/fake_claude.py`
- Modify: `tests/test_runner_supervisor.py`
- Modify: `tests/test_runner_cli.py`
- Modify: `shared/claude-runner/runner/supervisor.py`

**Interfaces:**
- Consumes: public `interrupt`, validated child process groups, and `termination_grace_seconds`.
- Produces: stages `interrupt`, `terminate`, and `kill`, persisted under `runtime.control_requested`.

- [ ] **Step 1: Add an unresponsive fake Claude**

Add scenario `ignore-interrupt-and-term` to `tests/fixtures/fake_claude.py`. Ignore both `SIGINT` and `SIGTERM`, emit one tool event, then sleep for `FAKE_CLAUDE_DELAY`.

- [ ] **Step 2: Write failing Supervisor and public CLI tests**

Add `test_interrupt_escalates_twice_for_unresponsive_process` using `termination_grace_seconds=0.05`. Request `supervisor.interrupt()` after `tool_started`, require completion well before the fixture sleep, require Work Unit and Segment `interrupted`, and assert:

```python
[item["stage"] for item in state.runtime["control_requested"]["stages"]]
== ["interrupt", "terminate", "kill"]
```

Add `test_interrupt_escalates_and_preserves_same_session_resume` to `tests/test_runner_cli.py`. Initialize with `--termination-grace-seconds 0.05`, run the unresponsive fixture in a subprocess, wait for active identity, invoke public `interrupt`, and require completion within two seconds. Assert `interrupted`, ordered three-stage evidence, and successful same-Session resume.

- [ ] **Step 3: Verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_runner_supervisor.SupervisorTests.test_interrupt_escalates_twice_for_unresponsive_process \
  tests.test_runner_cli.RunnerCliTests.test_interrupt_escalates_and_preserves_same_session_resume -v
```

Expected: current Runner waits for the fixture sleep or fails the bounded-time assertion because it sends only `SIGINT`.

- [ ] **Step 4: Implement the control stage machine**

In `shared/claude-runner/runner/supervisor.py`, keep `control_applied` as the owning action; replace the terminate-only deadline with `control_stage` and `control_deadline`. Implement interrupt as `SIGINT -> grace -> SIGTERM -> grace -> SIGKILL`, and retain terminate as `SIGTERM -> grace -> SIGKILL`. Persist `action`, `requested_at`, current `stage`, `stage_started_at`, and an ordered `stages` audit list. Do not add a lifecycle status or background reaper.

- [ ] **Step 5: Verify GREEN across both boundaries**

Run the Step 3 command. Expected: both tests pass after approximately two short grace periods.

- [ ] **Step 6: Verify existing control behavior**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runner_supervisor tests.test_runner_cli -v
```

Expected: the new tests and existing interrupt, terminate, lease, and stale-identity tests all pass.

- [ ] **Step 7: Inspect the Task 2 diff**

```bash
git diff --check
git diff -- shared/claude-runner/runner/supervisor.py tests/fixtures/fake_claude.py tests/test_runner_supervisor.py tests/test_runner_cli.py
```

Expected: only staged interrupt escalation, its persisted evidence, and tests are present.

- [ ] **Step 8: Commit Task 2**

```bash
git add shared/claude-runner/runner/supervisor.py tests/fixtures/fake_claude.py tests/test_runner_supervisor.py tests/test_runner_cli.py
git commit -m "fix: bound runner interrupt escalation"
```

---

### Task 3: Package and independently verify

**Files:**
- Modify mechanically: `skills/superpowers-claude-workflow/scripts/claude-runner/`
- Modify mechanically: `skills/matt-claude-workflow/scripts/claude-runner/`

**Interfaces:**
- Consumes: verified canonical shared Runner.
- Produces: two standalone skill packages with byte-identical Runner assets and real-backend evidence.

- [ ] **Step 1: Run the full suite before packaging**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Expected: zero failures and errors.

- [ ] **Step 2: Synchronize and check hard copies**

```bash
python3 scripts/sync_shared_assets.py
python3 scripts/sync_shared_assets.py --check
```

Expected: no stale, missing, mode, symlink, or extra issue.

- [ ] **Step 3: Validate packages and whitespace**

```bash
python3 scripts/validate_skill_packages.py
git diff --check
```

Expected: `Skill packages are valid.` and no whitespace errors.

- [ ] **Step 4: Real Claude permission regression**

Create a system-temporary ignored Git fixture. Initialize it with a newly synchronized packaged entrypoint and a narrow allowlist. Ask real Claude to use one harmless command that is deliberately not allowlisted. Require `status=permission_required`, a pending raw Hook with `hook_event_name=PermissionDenied`, and the running Segment ID. Dismiss the exact request, resume with bounded continuation context, and require unchanged Session ID, `attempt == 1`, and `resume_count == 1`.

- [ ] **Step 5: Real Claude bounded-interrupt regression**

Create a separate temporary Work Unit with a short grace setting and a long safe operation. Wait for its validated process identity, invoke public `interrupt`, and require terminal `interrupted` within two grace periods plus five seconds. Require cleared active identity, then resume the same Session successfully.

- [ ] **Step 6: Remove temporary evidence**

Use Runner `cleanup` only from allowed terminal states, remove the exact temporary regression root, and confirm no regression/evidence artifacts entered the source repository.

- [ ] **Step 7: Run final fresh verification**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
git diff --check
git status --short
```

Expected: full suite passes, packages are synchronized and valid, and status contains only intended changes.

- [ ] **Step 8: Commit synchronized packages**

```bash
git add skills/superpowers-claude-workflow/scripts/claude-runner skills/matt-claude-workflow/scripts/claude-runner
git commit -m "chore: sync reliable runner controls"
```

Finally review the full implementation commit range against the design and confirm no native Matt or Superpowers workflow logic changed.

---

### Task 4: Route structured stream permission denials

**Files:**
- Modify: `tests/test_runner_stream_capture.py`
- Modify: `tests/fixtures/fake_claude.py`
- Modify: `tests/test_runner_supervisor.py`
- Modify: `tests/test_runner_cli.py`
- Modify: `shared/claude-runner/runner/stream_capture.py`
- Modify: `shared/claude-runner/runner/permission_hooks.py`
- Modify: `shared/claude-runner/runner/supervisor.py`

**Interfaces:**
- Consumes: structured `tool_use` and `system.permission_denied` stream events, plus the existing pending-permission mutation and bounded interrupt state machine.
- Produces: exact `tool_use_id` correlation and one pending broker request without relying on a Hook callback or natural-language parsing.

- [ ] **Step 1: Write all failing tests before production changes**

Add a stream-capture test with a Bash `tool_use` whose ID is `toolu_denied` and input is `{"command": "git add .permission-probe"}`, followed by the exact real event shape:

```python
{
    "type": "system",
    "subtype": "permission_denied",
    "tool_name": "Bash",
    "tool_use_id": "toolu_denied",
    "decision_reason_type": "other",
    "decision_reason": "This command requires approval",
    "message": "This command requires approval",
    "session_id": SESSION_ID,
}
```

Assert correlation preserves the verbatim denial event, tool name, and full
tool input. Add unknown-ID and tool-name-mismatch cases that raise
`StreamProtocolError`.

Add fake-Claude scenario `stream-permission-denied` that emits the complete
tool call and denial event without invoking Hooks, then remains alive long
enough for the Supervisor to stop it. Add Supervisor and public CLI tests
requiring exact pending state, bounded stop, `permission_required`, dismissal,
and same-Session resume.

- [ ] **Step 2: Verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_runner_stream_capture \
  tests.test_runner_supervisor.SupervisorTests.test_stream_permission_denial_is_brokered_and_stopped \
  tests.test_runner_cli.RunnerCliTests.test_stream_permission_denial_can_be_dismissed_then_same_session_resumed -v
```

Expected: current parser does not correlate the denial, so no pending request
is created and the invocation does not reach the required lifecycle.

- [ ] **Step 3: Implement the minimal structured-event path**

Store tool name/input by tool-use ID inside `StreamObservation`. On the exact
system subtype, require a matching saved call and expose one internal denial
record. Refactor the pending mutation in `permission_hooks.py` into a reusable
function that accepts the verbatim request plus explicit tool name/input.

In Supervisor, atomically persist the first correlated denial, initiate the
existing bounded interrupt stages, and make pending-permission finalization
take precedence over the internal control marker. Clear internal control state
when entering `permission_required`. Do not surface tool input in ordinary
semantic runner events.

- [ ] **Step 4: Verify GREEN and regressions**

Run the Step 2 command, then:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_runner_permission_hooks \
  tests.test_runner_stream_capture \
  tests.test_runner_supervisor \
  tests.test_runner_cli -v
```

Expected: all selected tests pass, including Hook compatibility, interrupt
escalation, dismissal, and same-Session recovery.

- [ ] **Step 5: Inspect and commit**

```bash
git diff --check
git add shared/claude-runner/runner/stream_capture.py shared/claude-runner/runner/permission_hooks.py shared/claude-runner/runner/supervisor.py tests/test_runner_stream_capture.py tests/fixtures/fake_claude.py tests/test_runner_supervisor.py tests/test_runner_cli.py
git commit -m "fix: broker structured Claude permission denials"
```

After task review passes, return to Task 3, resynchronize both packaged Runner
trees, and repeat the real Claude permission and interrupt regressions.
