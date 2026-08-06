# Native Workflow Ownership Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove adapter-created lifecycle decisions while preserving executor routing and supervised Claude implementation.

**Architecture:** Native Skills remain the state machine for Review, fixes, Tracker, commits, verification, and completion. The orchestration Skills add executor metadata and replace only implementer dispatch; Runner records execution facts and enforces safety without introducing native lifecycle gates.

**Tech Stack:** Markdown Agent Skills, Python 3 standard library, `unittest`.

## Global Constraints

- Do not modify installed upstream Superpowers or Matt Skills.
- Preserve explicit per-work-unit Codex/Claude routing with `sonnet` and `opus` capability aliases.
- Preserve non-interactive Claude execution, lossless events, permission Hooks, timeout observations, backend-failure reporting, and exact UUID cleanup.
- Keep direct invocation of the original Skills unchanged.

---

### Task 1: Lock Native Workflow Ownership in Contract Tests

**Files:**
- Modify: `tests/test_workflow_contracts.py`
- Test: `tests/test_workflow_contracts.py`

**Interfaces:**
- Consumes: orchestration Skill and reference Markdown files.
- Produces: executable assertions defining the adapter/native boundary.

- [ ] **Step 1: Add failing assertions**

Add tests that reject `user-directed fixes`, `Do not start fixes automatically`, `When the user requests fixes`, `Apply only user-requested fixes`, unconditional Ticket claim/close requirements, and overlap rejection for merely available sequential work. Assert that implicit Matt tasks need no Tracker, that native workflow disposition controls fixes, and that standalone documentation/configuration remains with Codex.

- [ ] **Step 2: Run the focused contract tests and verify RED**

Run: `python3 -m unittest tests.test_workflow_contracts -v`

Expected: failures cite the existing invasive phrases and missing ownership language.

- [ ] **Step 3: Commit the red contract tests with the implementation task**

Keep the failing tests uncommitted until Task 2 makes them green so the branch remains bisectable.

---

### Task 2: Minimize Skill and Reference Behavior

**Files:**
- Modify: `skills/matt-claude-workflow/SKILL.md`
- Modify: `skills/matt-claude-workflow/references/matt-lifecycle-adapter.md`
- Modify: `skills/matt-claude-workflow/references/executor-contract.md`
- Modify: `skills/matt-claude-workflow/references/claude-execution-protocol.md`
- Modify: `skills/superpowers-claude-workflow/SKILL.md`
- Modify: `skills/superpowers-claude-workflow/references/executor-contract.md`
- Modify: `README.md`
- Modify: `CONTEXT.md`
- Modify: `docs/superpowers/specs/2026-08-06-shared-claude-runner-design.md`
- Modify: `docs/superpowers/plans/2026-08-06-shared-claude-runner.md`

**Interfaces:**
- Consumes: native Matt `implement`, `code-review`, `to-spec`, `to-tickets`; native Superpowers SDD.
- Produces: positive ownership rules that route implementation without choosing native lifecycle transitions.

- [ ] **Step 1: Replace Matt user-gated fix language**

State that native Review disposition decides whether implementation continues; route such continuation to the selected implementer without adding a new approval gate.

- [ ] **Step 2: Make Tracker behavior conditional**

Require only operations explicitly defined by the configured Tracker and only on the Ticket path. Remove invented universal claim, close, comment, and unclaimed-frontier rules.

- [ ] **Step 3: Label the Matt checkpoint as compatibility behavior**

Explain the committed-diff requirement without calling it native lifecycle. Avoid mandatory extra fix commits when no new implementation change exists.

- [ ] **Step 4: Permit sequential overlap**

Reject overlap only when the controller actually schedules work concurrently.

- [ ] **Step 5: Correct Superpowers execution scope**

Keep Claude ownership inside a Claude-routed coding Task; keep standalone documentation/configuration with Codex; scope dependency restrictions to workflow infrastructure.

- [ ] **Step 6: Remove stale policy copies**

Update README, context, accepted design, and implementation-plan language so future edits cannot restore the false native behavior.

- [ ] **Step 7: Run focused contract tests and verify GREEN**

Run: `python3 -m unittest tests.test_workflow_contracts -v`

Expected: all workflow contract tests pass.

- [ ] **Step 8: Commit**

```bash
git add tests/test_workflow_contracts.py skills README.md CONTEXT.md docs/superpowers/specs/2026-08-06-shared-claude-runner-design.md docs/superpowers/plans/2026-08-06-shared-claude-runner.md
git commit -m "fix: preserve native workflow lifecycle"
```

---

### Task 3: Make Runner Verification Evidence Non-Authoritative

**Files:**
- Modify: `tests/test_runner_cli.py`
- Modify: `tests/test_runner_end_to_end.py`
- Modify: `shared/claude-runner/runner/cli.py`
- Modify: `skills/superpowers-claude-workflow/references/claude-execution-protocol.md`
- Modify: `skills/matt-claude-workflow/references/claude-execution-protocol.md`
- Synchronize: both packaged `scripts/claude-runner/` copies.

**Interfaces:**
- Consumes: completed inactive Work Unit and optional verified evidence.
- Produces: handoff, Repair Segment, and cleanup transitions that do not claim native verification authority.

- [ ] **Step 1: Add failing Runner tests**

Prove that `finish`, `add-repair-segment`, and `cleanup --native-workflow-complete` succeed without a prior `record-verification` when execution is complete and inactive. Retain tests that `record-verification` stores evidence correctly.

- [ ] **Step 2: Run focused Runner tests and verify RED**

Run: `python3 -m unittest tests.test_runner_cli tests.test_runner_end_to_end -v`

Expected: existing `verification_required` gates fail the new expectations.

- [ ] **Step 3: Remove only lifecycle-authority checks**

Delete verification prerequisites from handoff, Repair Segment creation, and cleanup. Preserve Segment completion, safe path, inactive process, and native completion assertion checks.

- [ ] **Step 4: Synchronize hard copies**

Run: `python3 scripts/sync_shared_assets.py`

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python3 -m unittest tests.test_runner_cli tests.test_runner_end_to_end -v`

Expected: all focused Runner tests pass.

- [ ] **Step 6: Commit**

```bash
git add shared/claude-runner skills tests/test_runner_cli.py tests/test_runner_end_to_end.py README.md
git commit -m "fix: keep Runner evidence non-authoritative"
```

---

### Task 4: Full Verification and Live Matt Completion

**Files:**
- Verify: all repository tests and both Skill packages.
- Resume: the existing Matt live-regression Work Unit and fixture repository.

**Interfaces:**
- Consumes: corrected adapter contracts and existing Matt Review finding.
- Produces: deterministic regression evidence and a completed native Matt Review cycle.

- [ ] **Step 1: Run deterministic verification**

Run: `python3 -m unittest discover -s tests -v`

Run: `python3 scripts/sync_shared_assets.py --check`

Run: `python3 scripts/validate_skill_packages.py`

Expected: every command exits zero.

- [ ] **Step 2: Resume the native Matt finding**

Route the in-scope signature annotation finding back to the original Claude Session without asking for a new adapter approval. Run the native verification and two-axis Review against the original fixed point.

- [ ] **Step 3: Complete and clean adapter state**

Finish the implicit Matt task through native behavior, then remove exactly its Runner UUID directory.

- [ ] **Step 4: Review final repository diff and status**

Run: `git diff --check`

Run: `git status --short`

Expected: no uncommitted changes after final commits.
