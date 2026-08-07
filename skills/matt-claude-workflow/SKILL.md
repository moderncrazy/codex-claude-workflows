---
name: matt-claude-workflow
description: Run a Matt Pocock workflow with per-work-unit Codex and Claude implementer routing.
disable-model-invocation: true
---

# Matt Claude Workflow

## Overview

Keep Matt's Skills as workflow owner. Adapt only implementation while preserving Spec/Ticket state, test seams, native two-axis Codex Review, commits, and Tracker behavior.

## Required references

Before routing, read [executor-contract.md](references/executor-contract.md) and [matt-lifecycle-adapter.md](references/matt-lifecycle-adapter.md). Before Claude dispatch, read [claude-execution-protocol.md](references/claude-execution-protocol.md). Pass the bundled result Schema verbatim as machine input.

## Workflow

1. **Preflight.** Confirm native Skills, Python 3, and Claude Code. Follow native Tracker prerequisites; this wrapper neither requires nor suppresses Tracker setup. Add tracked `/.tmp/` to `.gitignore` before the fixed point when absent. Do not substitute, install, or patch Skills.
2. **Clarify.** **REQUIRED SUB-SKILL:** Use `grill-with-docs` when durable docs help; otherwise use `grill-me`. Codex owns requirements, domain decisions, and approval.
3. **Native route.** Native Matt Skills choose and own the workflow path, Tracker prerequisites, and tracer-bullet decomposition. Do not infer a path from work category, step count, anticipated tracer bullets, session count, or a wrapper-owned scale heuristic.
4. **Confirm seams.** **REQUIRED SUB-SKILL:** Use `tdd` and obtain the native confirmation.
5. **Implement.** **REQUIRED SUB-SKILL:** Use `implement` as workflow owner. Apply the adapters only at implementer dispatch.
6. **Review and complete.** Follow the lifecycle adapter's working-tree input adaptation so native `implement` keeps Review before commit; native `code-review` axes and configured Tracker instructions still decide Review disposition, fixes, verification, commits, and completion.

## Native work-unit boundary

After the native workflow identifies an implementation work unit, confirm one executor contract for it. Persist the contract in the native artifact or conversation selected by that workflow; do not create a Ticket or routing file solely for the adapter.

## Implementer adapter

- `agent: codex`: use native Codex implementation unchanged.
- `agent: claude-code`: create one Runner Work Unit for the native implementation work unit, define Execution Segments immediately before dispatch, and run this Skill's `scripts/claude-runner/claude_runner.py`.
- Never store Runner Session, permission, or Segment data in a native Tracker artifact. Runner state lives only under ignored `.tmp/codex-claude-workflows/<work-unit-id>/`.
- Keep all work-unit changes with the selected implementer. Never silently fall back to Codex.

## Completion boundary

Runner `implementation_complete` is not native completion. Native Review, verification, and commit requirements remain mandatory; configured Tracker transitions apply when selected by the native workflow. Do not add a cross-Ticket Final Review or Verify Review. After native completion, call `finish --native-workflow-complete` to enter `finished`, then clean the Runner UUID directory.

## Common mistakes

- Replacing a native planning workflow with generic issue Skills.
- Persisting Execution Segments in a Spec, Ticket, or Tracker.
- Reusing one Session across native work units.
- Letting the adapter decide Review disposition instead of routing the implementation action selected by the native workflow.
- Adding global hooks, a daemon, a plugin, or upstream Skill changes.
