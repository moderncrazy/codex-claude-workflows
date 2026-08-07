# Matt Native Routing Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove wrapper-owned Matt routing, tracer-bullet, and Tracker policy while retaining per-work-unit implementer routing.

**Architecture:** Native Matt Skills remain the sole workflow policy layer. `matt-claude-workflow` reacts only after the native flow identifies an implementation work unit, then attaches an executor contract and adapts Claude dispatch and working-tree Review input.

**Tech Stack:** Markdown Agent Skills, Python `unittest`, repository Skill-package validator.

## Global Constraints

- Do not modify installed native Matt Skills.
- Do not classify work from category, step count, anticipated tracer bullets, session count, or wrapper-owned scale heuristics.
- Do not require or suppress Tracker setup in the wrapper.
- Preserve native Review, commits, Tracker operations, tracer-bullet decomposition, and completion.

---

### Task 1: Delegate Native Routing and Tracker Policy

**Files:**
- Modify: `tests/test_workflow_contracts.py`
- Modify: `skills/matt-claude-workflow/SKILL.md`
- Modify: `skills/matt-claude-workflow/references/matt-lifecycle-adapter.md`

**Interfaces:**
- Consumes: the native Matt workflow path and implementation work units selected outside this wrapper.
- Produces: an executor contract and implementer dispatch for each native implementation work unit, without a wrapper-owned route or Tracker prerequisite.

- [ ] **Step 1: Replace the old implicit-Tracker contract test with a native-policy delegation test**

```python
def test_wrapper_delegates_routing_tracer_and_tracker_policy_to_native_matt(self):
    skill = (ROOT / "skills/matt-claude-workflow/SKILL.md").read_text().lower()
    lifecycle = (
        ROOT / "skills/matt-claude-workflow/references/matt-lifecycle-adapter.md"
    ).read_text().lower()
    text = skill + lifecycle

    self.assertIn("native matt skills choose", text)
    self.assertIn("tracker prerequisites", text)
    self.assertIn("tracer-bullet decomposition", text)
    self.assertIn("after the native workflow identifies", text)
    for wrapper_policy in (
        "choose scale",
        "tracker setup only for the spec/ticket path",
        "cross-session work or multiple tracer bullets",
        "without reading or changing a tracker",
    ):
        self.assertNotIn(wrapper_policy, text)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_workflow_contracts.MattLifecycleTests.test_wrapper_delegates_routing_tracer_and_tracker_policy_to_native_matt -v`

Expected: FAIL because the current wrapper contains `Choose scale`, the Spec/Ticket-only Tracker rule, and the implicit no-Tracker override.

- [ ] **Step 3: Make `SKILL.md` a reactive implementer adapter**

Replace wrapper-owned preflight and scale rules with explicit delegation:

```markdown
1. **Preflight.** Confirm native Skills, Python 3, and Claude Code. Follow native Tracker prerequisites; this wrapper neither requires nor suppresses Tracker setup.
3. **Native route.** Native Matt Skills choose and own the workflow path, Tracker prerequisites, and tracer-bullet decomposition. Do not infer a path from work category, step count, anticipated tracer bullets, session count, or a wrapper-owned scale heuristic.
## Native work-unit boundary

After the native workflow identifies an implementation work unit, confirm one executor contract for it. Persist the contract in the native artifact or conversation selected by that workflow; do not create a Ticket or routing file solely for the adapter.
```

Keep implementer dispatch, working-tree Review adaptation, and Runner completion unchanged. Remove the wrapper-owned `Native paths` section and replace Ticket-only completion language with “when selected by the native workflow.”

- [ ] **Step 4: Remove path policy from the lifecycle adapter**

Replace the `Ticket path` and `Implicit-task lifecycle` sections with:

```markdown
## Native Tracker boundary

Follow the selected native workflow and its configured Tracker instructions unchanged. This adapter neither requires nor suppresses Tracker setup, chooses a Ticket path, decomposes tracer bullets, nor invents Tracker operations. Read or change Tracker state only when the native workflow requires that operation.
```

- [ ] **Step 5: Run focused and full contract tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_workflow_contracts -v`

Expected: PASS.

- [ ] **Step 6: Commit the behavior change**

```bash
git add tests/test_workflow_contracts.py skills/matt-claude-workflow/SKILL.md skills/matt-claude-workflow/references/matt-lifecycle-adapter.md
git commit -m "fix: defer Matt routing policy to native skills"
```

### Task 2: Pressure-Test and Deploy the Skill

**Files:**
- Verify: `skills/matt-claude-workflow/SKILL.md`
- Verify: `skills/matt-claude-workflow/references/matt-lifecycle-adapter.md`
- Deploy after verification: `/Users/geekeryoung.gao/.agents/skills/matt-claude-workflow/`

**Interfaces:**
- Consumes: the updated repository Skill package.
- Produces: a validated installed Skill whose wrapper does not classify test-infrastructure work or decide Tracker policy.

- [ ] **Step 1: Run a pressure scenario against the updated Skill**

Give a fresh reviewer this scenario and the updated Skill:

```text
The repository lacks docs/agents/issue-tracker.md. The user asks to update test infrastructure and explicitly invokes matt-claude-workflow. Decide only what the wrapper itself requires before implementation. Identify which decisions must be delegated to native Matt Skills.
```

Expected: the reviewer says the wrapper cannot classify the task as implicit or Spec/Ticket, cannot require or waive Tracker setup, and must let native Matt Skills choose before applying the executor adapter.

- [ ] **Step 2: Run the complete repository verification**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v && python3 scripts/sync_shared_assets.py --check && python3 scripts/validate_skill_packages.py && git diff --check`

Expected: all tests pass, Skill packages are valid, shared assets are synchronized, and the diff has no whitespace errors.

- [ ] **Step 3: Sync the verified package to the installed Skill**

Copy only the verified `skills/matt-claude-workflow` package contents to `/Users/geekeryoung.gao/.agents/skills/matt-claude-workflow`, preserving the package layout and without modifying native Matt Skills.

- [ ] **Step 4: Verify the installed package matches the repository source**

Run a recursive comparison between `skills/matt-claude-workflow` and `/Users/geekeryoung.gao/.agents/skills/matt-claude-workflow`.

Expected: no differences.

- [ ] **Step 5: Commit any verification-only repository changes if present**

No commit is needed when pressure testing and deployment create no repository changes. If verification exposes a Skill wording defect, return to Task 1 with a failing contract test before changing the Skill.
