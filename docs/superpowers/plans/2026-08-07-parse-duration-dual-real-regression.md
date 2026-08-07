# Parse Duration Dual Real-Workflow Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the current working-tree versions of both Claude workflow Skills through separate, real Claude Code implementations of the same `parse_duration` feature and preserve auditable lifecycle evidence.

**Architecture:** Use two independent nested Git repositories under one ignored regression run directory. Codex drives each native workflow and all reviews; the packaged Runner dispatches one real `sonnet` Work Unit per repository. Evidence outside the nested repositories records hashes, Session continuity, reviews, verification, and final status without becoming native workflow state.

**Tech Stack:** Python 3.14 standard library, `unittest`, Git, Claude Code 2.1.222, the current repository's `skills/superpowers-claude-workflow` and `skills/matt-claude-workflow` packages.

## Global Constraints

- Run root: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0`.
- Superpowers repository: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers`; Matt repository: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/matt`; external evidence: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence`.
- Use the current working-tree Skill sources in `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/skills`; do not invoke installed wrapper copies.
- Use real Claude Code with capability alias `sonnet`; never substitute `tests/fixtures/fake_claude.py` or silently fall back to Codex implementation.
- Use distinct Work Unit IDs: Superpowers `66479147-2be2-467b-a872-96da112f17ba`; Matt `f444e6a1-b4d0-463c-9dbb-2b020025854f`.
- Use no third-party dependency, network command, package installation, push, merge, deployment, amend, rebase, reset, tag, or evidence cleanup.
- Both repositories implement `parse_duration(text: str) -> int`, accepting a positive whole number plus lowercase `ms`, `s`, or `m`, with optional surrounding whitespace and no internal whitespace.
- `ms`, `s`, and `m` use multipliers 1, 1,000, and 60,000. Zero, negatives, decimals, missing number/unit, uppercase/unknown units, internal whitespace, and trailing characters raise `ValueError`; non-string inputs raise `TypeError`.
- Required files in each repository: `duration_parser/__init__.py`, `duration_parser/parser.py`, `tests/test_parser.py`, and `README.md`.
- Focused and full verification command: `python3 -m unittest discover -s tests -v`.
- Preserve Runner state and raw evidence after completion.

---

### Task 1: Establish isolated baselines and evidence manifest

**Files:**
- Create: `.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/.gitignore`
- Create: `.tmp/real-regressions/20260807-parse-duration-ba770d0/matt/.gitignore`
- Create: `.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/manifest.md`

**Interfaces:**
- Consumes: approved design commit `ba770d0` and the current modified Skill files.
- Produces: two clean baseline repositories, their baseline SHAs, and hashes proving which Skill source was exercised.

- [ ] **Step 1: Create the three directories and baseline files**

Each `.gitignore` contains exactly:

```gitignore
/.tmp/
__pycache__/
*.py[cod]
```

Initialize both directories as Git repositories on `main`, configure the local fixture name `Regression` and email `regression@example.com`, then stage `.gitignore`. Commit the Superpowers repository as `chore: establish superpowers regression baseline` and the Matt repository as `chore: establish matt regression baseline`.

- [ ] **Step 2: Record immutable source and baseline evidence**

Write `manifest.md` with the absolute run paths, UTC start time, `claude --version`, `python3 --version`, `git --version`, both baseline SHAs, the two fixed Work Unit IDs, and SHA-256 hashes for:

```text
skills/superpowers-claude-workflow/SKILL.md
skills/superpowers-claude-workflow/references/claude-execution-protocol.md
skills/superpowers-claude-workflow/scripts/claude-runner/claude_runner.py
skills/matt-claude-workflow/SKILL.md
skills/matt-claude-workflow/references/claude-execution-protocol.md
skills/matt-claude-workflow/references/matt-lifecycle-adapter.md
skills/matt-claude-workflow/scripts/claude-runner/claude_runner.py
```

- [ ] **Step 3: Verify isolation**

Run `git status --short` and `git rev-parse HEAD` in each nested repository. Expected: both statuses are empty and the baseline SHAs differ because the repositories have independent histories.

### Task 2: Run the current Superpowers wrapper through native planning

**Files:**
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/docs/superpowers/specs/2026-08-07-parse-duration-design.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/docs/superpowers/plans/2026-08-07-parse-duration.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/.superpowers/sdd/2026-08-07-parse-duration/progress.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/.superpowers/sdd/2026-08-07-parse-duration/task-1-brief.md`

**Interfaces:**
- Consumes: the shared contract and Superpowers baseline SHA.
- Produces: approved native Design and Plan, one valid executor contract, and one authoritative SDD task brief.

- [ ] **Step 1: Run native Design ownership**

Read and apply the current wrapper plus native `superpowers:brainstorming`. Write a concise native Design containing the exact public signature, grammar, exception behavior, file layout, and verification command from Global Constraints. Self-review it for placeholders, ambiguity, and missing cases; commit only the Design as `docs: design duration parser`.

- [ ] **Step 2: Write the native single-Task Plan**

Read and apply native `superpowers:writing-plans`. Define one Task owning source, tests, and README with this exact executor contract:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: bounded standard-library parser with an approved public API and deterministic unittest contract
```

The Task brief instructs Claude to write `tests/test_parser.py` first, run the suite and observe a failure caused by the missing implementation, add the minimum implementation, rerun to Green, run `git diff --check`, and commit the four product files as `feat: add duration parser`.

- [ ] **Step 3: Approve routing and initialize native SDD state**

Validate the executor contract, show the Task/agent/model/reason route, then record approval. Initialize native progress and brief files; commit the Plan and initial SDD state as `docs: plan duration parser implementation`. Record the resulting Task fixed-point SHA in the external manifest.

### Task 3: Execute and review the Superpowers Task

**Files:**
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/duration_parser/__init__.py`
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/duration_parser/parser.py`
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/tests/test_parser.py`
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/README.md`
- Create through Runner: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/.tmp/codex-claude-workflows/66479147-2be2-467b-a872-96da112f17ba/`
- Create through native SDD: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/superpowers/.superpowers/sdd/2026-08-07-parse-duration/task-1-report.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/superpowers-review-1.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/superpowers-review-2.md`

**Interfaces:**
- Consumes: the approved native Task brief and Task fixed point.
- Produces: a committed implementation, one real Claude Session, a same-Session repair, two-stage Task Review, and a clean post-repair Task state.

- [ ] **Step 1: Initialize and run the real Work Unit**

Use the current Superpowers packaged Runner and bundled result Schema. Define one implementation Segment whose prompt contains the complete Task brief and TDD evidence requirement. Allow only these Bash families in addition to normal file editing:

```text
Bash(python3 -m unittest discover -s tests -v)
Bash(git status --short)
Bash(git diff --check)
Bash(git diff *)
Bash(git add duration_parser/__init__.py duration_parser/parser.py tests/test_parser.py README.md)
Bash(git commit -m "feat: add duration parser")
```

Call Runner `init` with workflow `superpowers`, Work Unit ID `66479147-2be2-467b-a872-96da112f17ba`, capability `sonnet`, the exact Task fixed point, and one Segment; then call `run`. If a permission is requested, apply the current permission broker and approve only a task-scoped, non-prohibited rule before resuming.

- [ ] **Step 2: Validate the initial handoff**

Require `implementation_complete`, a valid structured result, one recorded Session ID, raw events showing the expected Red failure and Green pass, the exact implementation commit, and no files outside the approved Task. Write the native Task report from verified evidence rather than trusting Progress Claims.

- [ ] **Step 3: Run native Spec and Code Quality Review**

Apply native SDD's two separate Task Review stages against the approved brief and Task fixed point. Record findings without merging or reranking. Explicitly inspect full-string parsing so an input such as `"1s\njunk"` cannot be partially accepted.

- [ ] **Step 4: Resume the same Session for one accepted repair**

If Review has a valid in-scope finding, route it unchanged. Otherwise request one contract-preserving hardening change: add a public test proving `parse_duration("1s\njunk")` raises `ValueError`, changing production code only if the test exposes a defect. Resume the original Segment Session, require matching Session ID, rerun the suite, run `git diff --check`, and commit the repair as `test: harden trailing input validation`.

- [ ] **Step 5: Re-review and close the Task**

Rerun both Task Review stages over the complete Task commits. Record both dispositions in `superpowers-review-2.md`, update the Task report and native progress, and require both stages to accept the Task before proceeding.

### Task 4: Finish the Superpowers workflow

**Files:**
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/superpowers-final-review.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/superpowers-verification.txt`

**Interfaces:**
- Consumes: accepted Task Review and completed native SDD state.
- Produces: whole-branch review, fresh verification, local branch-finishing evidence, final SHA, and status.

- [ ] **Step 1: Run whole-branch Final Review**

Review the complete baseline-to-HEAD change for Spec compliance and code quality. Record all findings and require an accepted disposition before finishing.

- [ ] **Step 2: Run fresh verification**

Run `python3 -m unittest discover -s tests -v`, `git diff --check`, and `git status --short`. Save exact outputs and exit codes. Record verification in Runner state, then call Runner `finish`; do not clean its state directory.

- [ ] **Step 3: Apply native branch finishing locally**

Use `superpowers:finishing-a-development-branch`, choose the local keep option, and perform no push or merge. Record final SHA, status, commit graph, Work Unit ID, Session ID, and prohibited-action confirmation.

### Task 5: Run the current Matt wrapper through implicit-task implementation

**Files:**
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/matt/duration_parser/__init__.py`
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/matt/duration_parser/parser.py`
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/matt/tests/test_parser.py`
- Create through Claude: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/matt/README.md`
- Create through Runner: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/matt/.tmp/codex-claude-workflows/f444e6a1-b4d0-463c-9dbb-2b020025854f/`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/matt-implicit-task.md`

**Interfaces:**
- Consumes: the shared contract and Matt baseline SHA.
- Produces: a complete uncommitted working tree, Red-Green evidence, and one real Claude Session under the native implicit-task lifecycle.

- [ ] **Step 1: Confirm native clarification and TDD seam**

Apply the current Matt wrapper, native `grill-me`, `tdd`, and `implement` instructions. Record the exact API, grammar, exception cases, allowed files, original baseline fixed point, test command, and this approved implicit executor contract in external evidence only:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: one cohesive standard-library parser with approved public seams
```

- [ ] **Step 2: Initialize and run the real Work Unit without commit permission**

Use the current Matt packaged Runner and bundled result Schema. Define one implementation Segment and allow only:

```text
Bash(python3 -m unittest discover -s tests -v)
Bash(git status --short)
Bash(git diff --check)
Bash(git diff *)
```

Call Runner `init` with workflow `matt`, Work Unit ID `f444e6a1-b4d0-463c-9dbb-2b020025854f`, capability `sonnet`, the Matt baseline SHA, and one Segment; then call `run`. The prompt explicitly requires TDD and an uncommitted handoff. Never approve any commit command through the Runner.

- [ ] **Step 3: Validate the uncommitted handoff**

Require `implementation_complete`, a valid structured result, one Session ID, raw Red then Green test evidence, all four product files in the working tree, no implementation commit after the baseline, and no out-of-scope file.

### Task 6: Exercise Matt working-tree Review and post-review commit

**Files:**
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/matt-standards-review-1.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/matt-spec-review-1.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/matt-standards-review-2.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/matt-spec-review-2.md`
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/matt-verification.txt`

**Interfaces:**
- Consumes: the original Matt fixed point and complete uncommitted implementation.
- Produces: separate two-axis reviews, same-Session repair, accepted re-review, one post-review commit, and clean completion evidence.

- [ ] **Step 1: Build both complete working-tree Review inputs**

Capture `git status --short`, `git diff --stat HEAD`, `git diff HEAD`, and `git ls-files --others --exclude-standard`. Append the full content of each untracked product file to both Review inputs. Confirm the change is non-empty and `git rev-parse HEAD` still equals the original fixed point recorded in the manifest.

- [ ] **Step 2: Run native Standards and Spec axes separately**

Apply the installed current native `code-review` criteria while replacing only its commit-range input with the complete working-tree input mandated by the modified lifecycle adapter. Preserve the two reports and dispositions independently. Explicitly inspect full-string parsing of `"1s\njunk"`.

- [ ] **Step 3: Resume the same Session with no commit**

Route a valid in-scope finding unchanged. If neither axis finds one, request the same trailing-input hardening test used in the Superpowers regression. Resume the original Segment Session and require its Session ID to match. Rerun the full suite and `git diff --check`; verify HEAD is still the fixed point.

- [ ] **Step 4: Rebuild inputs and rerun both Review axes**

Repeat the four Git inspections against the original fixed point, again including every untracked file's current content in both inputs. Write separate round-two reports. Require both axes to accept the change and verify that no implementation file changes afterward.

- [ ] **Step 5: Verify, then create the single native post-Review commit**

Run `python3 -m unittest discover -s tests -v` and `git diff --check`. Stage exactly the four product files and commit them once as `feat: add reviewed duration parser`. Confirm there was no pre-Review implementation commit and exactly one commit follows the baseline. Record verification in Runner state, call Runner `finish`, and leave Runner evidence intact.

### Task 7: Compare evidence and report the regression result

**Files:**
- Create: `/Users/geekeryoung.gao/Project/Hi-Young/codex-claude-workflows/.tmp/real-regressions/20260807-parse-duration-ba770d0/evidence/final-report.md`

**Interfaces:**
- Consumes: both completed repositories, native artifacts, Runner states, review reports, and verification outputs.
- Produces: one evidence-backed PASS/FAIL result and any precisely scoped workflow defect.

- [ ] **Step 1: Verify equivalence and isolation**

Compare public APIs and acceptance tests semantically. Confirm different repository roots, baselines, final SHAs, Work Unit IDs, Session IDs, Runner state directories, and Git histories; confirm no implementation files were copied between repositories.

- [ ] **Step 2: Audit every mandatory lifecycle fact**

For each workflow, verify real Claude executable use, `sonnet`, initial and resumed matching Session ID, Red/Green evidence, first Review, repair, accepted re-review, final tests, clean diff check, commit rules, and prohibited-action compliance. For Matt, additionally prove `HEAD` stayed at the baseline through both Review rounds and moved only after acceptance.

- [ ] **Step 3: Recheck the workflow source repository**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
git diff --check
git status --short
```

Compare status with the known pre-regression modifications so no unexpected workflow-source change is attributed to the run.

- [ ] **Step 4: Write the final result**

Write `final-report.md` with exact commands, exit codes, SHAs, Session IDs, review dispositions, evidence paths, and a requirement-by-requirement PASS/FAIL table. Overall PASS requires both native workflows to pass; a backend failure or partial lifecycle is reported as FAIL without fake fallback.
