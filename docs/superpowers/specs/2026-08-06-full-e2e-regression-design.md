# Full End-to-End Regression Design

## Purpose

Verify that `superpowers-claude-workflow` and `matt-claude-workflow` can each complete a real development cycle with Claude Code as the selected implementer while their native Codex workflows retain planning, state, review, verification, and completion ownership.

The two regressions use the same product requirement in separate repositories so that the workflow is the primary experimental variable.

## Shared Product Requirement

Each repository implements a small Python TTL cache with no third-party runtime or test dependencies.

The public API stores a value with a positive TTL, returns an unexpired value, reports a miss after expiry, deletes entries explicitly, and clears all entries. Time must be supplied through an injectable monotonic clock so tests are deterministic. Invalid TTL values must fail without mutating cache state.

Both repositories use the same acceptance cases, Python version assumptions, package layout, and `unittest`-based verification commands. Implementations and Claude Sessions must not be copied or reused between repositories.

## Superpowers Regression

The Superpowers workflow owns requirements, Design, Plan, executor contracts, SDD state, Task Review, whole-branch Final Review, verification, and branch finishing.

Claude Code `sonnet` implements the bounded cache source and tests. Codex may own documentation or simple configuration in a separate non-overlapping Task, reflecting the user's routing preference. Native `.superpowers/sdd/<plan>/` artifacts remain authoritative; the adapter adds only the deterministic per-Task Claude state file required by the protocol.

After the first native Task Review, Codex records one small in-scope Review finding. The original Claude Session performs the requested fix, tests are rerun, and native Review runs again. Completion requires the whole-branch Final Review and native branch-finishing checks.

## Matt Regression

The Matt workflow uses its implicit-task path because the regression is one cohesive session and no real Tracker is configured. Codex owns clarification, domain decisions, public test-seam confirmation, fixed-point capture, Review, verification, and completion.

Claude Code `sonnet` performs the Red-Green implementation and creates the orchestrator-requested local review checkpoint commit. Native `code-review` evaluates the non-empty fixed-point-to-HEAD diff on both Standards and Spec axes.

After the first Review, Codex records one small in-scope finding. The same Claude Session performs the requested fix and creates a separate local fix commit. Native `code-review` reruns against the original fixed point. The implicit task completes without a Ticket, Tracker mutation, cross-Ticket Final Review, or second ledger.

## Mandatory Evidence

Each regression must preserve:

- the Claude capability alias and a valid, matching Session ID;
- the initial structured Claude result and the resumed-session result;
- Red then Green test evidence;
- native workflow state and reports;
- the Review findings and post-fix Review disposition;
- local checkpoint and fix commit SHAs where the native workflow requires them;
- final focused and full-suite test output;
- clean, auditable repository status at completion.

Claude Code must run in non-interactive `acceptEdits` mode with the bundled JSON Schema. It may not push, merge, deploy, rewrite history, bypass permissions, or silently fall back to Codex. Authentication, quota, service, permission, invalid-result, timeout, or resume failures must be reported with preserved state.

## Pass Criteria

Both workflows must complete an actual implementation, test, Review, same-Session fix, re-review, and final verification cycle. Review and workflow decisions remain with Codex. The shared requirements and acceptance cases must pass in both isolated repositories, and the workflow repository must remain free of unrelated changes.

A backend failure is a valid protocol observation but not a passing end-to-end regression. The overall result is PASS only when both real Claude-backed development cycles finish successfully.
