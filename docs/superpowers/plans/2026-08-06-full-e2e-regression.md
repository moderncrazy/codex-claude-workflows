# Full End-to-End Workflow Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run two isolated, real Claude-backed development cycles against the same Python TTL cache requirement and collect auditable evidence for both workflow Skills.

**Architecture:** Each workflow runs in its own Git repository and Codex task. Both receive the same product requirement and acceptance cases, while their native planning, state, Review, commit, and completion models remain unchanged. The workflow repository stores only the regression design and plan; implementation artifacts stay in the isolated repositories.

**Tech Stack:** Python 3 standard library, `unittest`, Git, Claude Code CLI 2.1.222, Codex tasks, local workflow Skills at this repository's `skills/` directory.

## Global Constraints

- Use no third-party runtime or test dependency.
- Use the same TTL cache requirements and acceptance cases in both repositories.
- Use separate repositories, Claude Sessions, commits, and workflow state.
- Invoke a real Claude Code `sonnet` Session in non-interactive `acceptEdits` mode with the bundled result Schema.
- Preserve the native workflow's planning, state, Review, verification, and completion ownership.
- Do not push, merge, deploy, rewrite history, bypass permissions, or silently fall back to Codex.
- A real backend failure must stop the affected workflow and be reported; it does not count as an end-to-end PASS.
- After initial Review, resume the same Claude Session for one user-authorized in-scope fix or test-hardening request, then rerun native Review.

---

## Shared Product Contract

Create package `ttl_cache` with this public interface:

```python
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")

class TTLCache(Generic[K, V]):
    def __init__(self, clock: Callable[[], float]) -> None: ...
    def set(self, key: K, value: V, ttl: float) -> None: ...
    def get(self, key: K, default: V | None = None) -> V | None: ...
    def delete(self, key: K) -> bool: ...
    def clear(self) -> None: ...
```

Required behavior:

- `set` stores a value until `clock() >= insertion_time + ttl`.
- `ttl <= 0`, NaN, and positive or negative infinity raise `ValueError` without mutating existing state.
- `get` returns the stored value before expiry, otherwise removes the expired entry and returns `default`.
- `delete` returns `True` only when the key existed, including an expired-but-not-yet-read key; it removes that entry.
- `clear` removes every entry.
- Tests use a mutable fake monotonic clock and contain no sleeping or wall-clock dependence.
- Focused and full verification command: `python3 -m unittest discover -s tests -v`.

Expected project files in each regression repository:

- `ttl_cache/__init__.py` — exports `TTLCache`.
- `ttl_cache/cache.py` — cache implementation only.
- `tests/test_cache.py` — public behavior tests with a fake clock.
- `README.md` — concise API and verification instructions.

## Task 1: Superpowers Real Regression

**Repository:** `/Users/geekeryoung.gao/Documents/Codex/2026-08-05/superpowers-claude-workflow-regression`

**Workflow source:** `/Users/geekeryoung.gao/Documents/Codex/2026-08-05/new-chat/work/codex-claude-workflows/skills/superpowers-claude-workflow/SKILL.md`

**Files:**
- Create through native workflow: `docs/superpowers/specs/2026-08-06-ttl-cache-design.md`
- Create through native workflow: `docs/superpowers/plans/2026-08-06-ttl-cache.md`
- Create through native workflow: `.superpowers/sdd/2026-08-06-ttl-cache/progress.md`
- Create through native workflow: `.superpowers/sdd/2026-08-06-ttl-cache/task-1-brief.md`
- Create through native workflow: `.superpowers/sdd/2026-08-06-ttl-cache/task-1-report.md`
- Create through adapter: `.superpowers/sdd/2026-08-06-ttl-cache/task-1-claude-state.json`
- Create through implementer: `ttl_cache/__init__.py`
- Create through implementer: `ttl_cache/cache.py`
- Create through implementer: `tests/test_cache.py`
- Create through Codex-owned non-overlapping Task: `README.md`

- [ ] **Step 1: Establish an auditable baseline**

Initialize the empty directory as a Git repository on `main`, create a baseline `.gitignore` with exactly:

```gitignore
__pycache__/
*.py[cod]
```

Commit it. Record baseline HEAD and clean status.

- [ ] **Step 2: Run native requirements and Design**

Invoke the local `superpowers-claude-workflow`, which must invoke native `brainstorming`. Use the Shared Product Contract verbatim, approve no extra features, write the native Design, self-review it, and commit it.

- [ ] **Step 3: Write and approve the native implementation Plan**

Invoke native `writing-plans`. Use one Claude-owned implementation Task covering source and tests and one Codex-owned non-overlapping README Task. Persist these executor contracts:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: bounded standard-library implementation with an approved public API and deterministic test seam
```

```yaml
executor:
  agent: codex
  reason: user explicitly routes documentation-only changes to Codex
```

Validate independence, current-session execution, file ownership, and native SDD compatibility. Record route approval.

Approved initial Permission Budget for the Claude-owned Task:

```text
Bash(python3 -m unittest discover -s tests -v)
Bash(git status --short)
Bash(git diff --check)
Bash(git add ttl_cache/__init__.py ttl_cache/cache.py tests/test_cache.py)
Bash(git commit -m "feat: implement TTL cache")
Bash(git commit -m "fix: address review feedback")
```

- [ ] **Step 4: Execute Task 1 with real Claude Code**

Invoke native `subagent-driven-development` as owner. Generate a UUID, call Claude Code with the bundled Schema and the complete native brief, and require Red then Green evidence plus the native report. Validate structured output and matching Session ID; persist deterministic Claude state without creating another ledger.

- [ ] **Step 5: Run native Task Review**

Run independent Codex Spec Review and Code Quality Review. If either reports a valid finding, record it unchanged. If both pass, record a regression-only request to strengthen one existing public-behavior test without changing the API or product scope.

- [ ] **Step 6: Resume the original Claude Session for the fix**

Use `--resume <task-session-id>` with the same Schema. Supply only the accepted Review finding or test-hardening request. Verify the returned Session ID matches, rerun focused/full tests, update the native report and adapter state, and rerun both Task Review stages.

- [ ] **Step 7: Execute the Codex-owned README Task**

Create `README.md` with the public API, TTL boundary semantics, and exact verification command. Run native Task Review for this Task and update native SDD progress.

- [ ] **Step 8: Complete native whole-branch checks**

Run whole-branch Final Review, `python3 -m unittest discover -s tests -v`, and native `finishing-a-development-branch`. Select the local keep/finish option that does not push or merge. Record final HEAD, status, reports, Session ID, and Review dispositions.

## Task 2: Matt Real Regression

**Repository:** `/Users/geekeryoung.gao/Documents/Codex/2026-08-05/matt-claude-workflow-regression`

**Workflow source:** `/Users/geekeryoung.gao/Documents/Codex/2026-08-05/new-chat/work/codex-claude-workflows/skills/matt-claude-workflow/SKILL.md`

**Files:**
- Create through native clarification: `docs/domain.md`
- Create through implementer: `ttl_cache/__init__.py`
- Create through implementer: `ttl_cache/cache.py`
- Create through implementer: `tests/test_cache.py`
- Create through implementer: `README.md`

- [ ] **Step 1: Establish an auditable baseline**

Initialize the empty directory as a Git repository on `main`, create a baseline `.gitignore` with exactly:

```gitignore
__pycache__/
*.py[cod]
```

Commit it. Record the fixed-point SHA and clean status.

- [ ] **Step 2: Run native clarification and seam confirmation**

Invoke the local `matt-claude-workflow`. Use `grill-with-docs` to capture the shared vocabulary and expiry boundary, then use native `tdd` to approve the public `TTLCache` API and mutable fake-clock seam. Choose the implicit-task path and create no Ticket or routing file.

- [ ] **Step 3: Confirm the implicit executor contract**

Present and approve this in-conversation contract together with the Shared Product Contract, fixed point, allowed files, forbidden scope, Red-Green evidence, and verification command:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: one cohesive standard-library implementation with approved public seams
```

Approved initial Permission Budget:

```text
Read(/Users/geekeryoung.gao/Documents/Codex/2026-08-05/new-chat/work/codex-claude-workflows/docs/superpowers/specs/2026-08-06-full-e2e-regression-design.md)
Read(/Users/geekeryoung.gao/Documents/Codex/2026-08-05/new-chat/work/codex-claude-workflows/docs/superpowers/plans/2026-08-06-full-e2e-regression.md)
Bash(python3 -m unittest discover -s tests -v)
Bash(git status --short)
Bash(git diff --check)
```

- [ ] **Step 4: Execute native Implement with real Claude Code**

Invoke native `implement` as owner. Generate a fresh UUID distinct from Task 1, call Claude Code with the bundled Schema, validate structured output and Session ID, and require Red then Green evidence without creating a commit. Do not create a Ticket or second ledger.

- [ ] **Step 5: Run native two-axis working-tree Review**

Use native `code-review`'s Standards and Spec axes with `git status --short`, `git diff --stat <baseline>`, `git diff <baseline>`, and the contents of files listed by `git ls-files --others --exclude-standard`. Confirm the complete working-tree change is non-empty. Preserve both findings separately. If neither axis reports a valid finding, record a regression-only request to strengthen one existing public-behavior test without changing the API or product scope.

- [ ] **Step 6: Resume the original Claude Session for the fix**

Use `--resume <implicit-task-session-id>` with the same Schema. Supply only the accepted finding or test-hardening request. Verify the returned Session ID and rerun tests without committing.

- [ ] **Step 7: Re-review and complete the implicit task**

Rerun the two-axis working-tree Review against the original baseline, run `python3 -m unittest discover -s tests -v`, then create the native post-Review commit and record its SHA, both Review axes, test evidence, Session ID, and clean status. Do not run a cross-Ticket Final Review or create Tracker state.

## Task 3: Compare Evidence and Report

**Files:**
- Read: both regression repositories and their native workflow artifacts
- Modify only if a verified workflow defect exists: relevant Skill/reference/test files in this repository

- [ ] **Step 1: Verify isolation and equivalent requirements**

Compare public interfaces and acceptance tests. Confirm no Session ID, commit, state file, implementation file, or workflow ledger is shared between repositories.

- [ ] **Step 2: Verify required evidence**

For each workflow, verify real Claude invocation, matching initial/resumed Session ID, Red-Green evidence, initial Review, same-Session fix, re-review, final tests, commit/state requirements, and prohibited-action compliance.

- [ ] **Step 3: Classify the outcome**

Report PASS only if both workflows complete. Classify verified defects by severity and separate workflow defects from Claude backend/environment failures. Do not modify a Skill merely because execution is slow or a test fixture assumption was wrong.

- [ ] **Step 4: Recheck the workflow repository**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected: four contract tests pass, whitespace check is clean, and only intentional regression-document commits differ from the previously published workflow version.
