# Native Workflow Ownership Correction Design

**Status:** Approved

## Problem

The orchestration Skills are intended to replace only the implementation dispatch boundary, but several adapter rules currently decide native lifecycle behavior. Matt fixes are incorrectly user-gated, Tracker operations are invented, commit and verification checkpoints are presented as native behavior, sequential work is rejected for file overlap, and Runner evidence gates duplicate native verification. Superpowers also assigns documentation/configuration too broadly and ambiguously forbids dependency work.

## Ownership rule

The Native Workflow decides what happens next. The adapter decides who performs an implementation action and reliably supervises Claude Code when selected. Runner state may describe execution, preserve evidence, stop unsafe activity, and support recovery; it may not authorize or block native Review, fix, Tracker, verification, commit, or completion transitions.

## Matt workflow

The orchestration Skill may choose between an implicit task and the native Spec/Ticket path, attach executor contracts, and invoke native Matt Skills. Once `implement` starts, its native behavior remains authoritative:

- `code-review` returns Standards and Spec findings without an adapter-created user approval gate.
- When the native workflow routes an in-scope finding back to implementation, the adapter resumes the owning Claude Session or creates a bounded Repair Segment.
- Ticket claiming, closing, commenting, and frontier changes occur only when the configured native Tracker instructions require them.
- Implicit tasks never require Tracker setup.
- Because native `implement` places Review before commit while `code-review` normally consumes `<fixed-point>...HEAD`, the adapter preserves the ordering and substitutes the complete working-tree change as Review input. It creates no pre-Review commit; native `implement` commits only after Review is accepted.

## Superpowers workflow

Executor contracts and their explicit routing confirmation remain the intentional orchestration seam. SDD retains Task briefs, reports, commits, Reviews, Fix Loop, Final Review, verification, and branch finishing. File overlap is rejected only for work that will actually run concurrently; sequential Tasks may touch the same files.

Claude owns all implementation changes inside a Claude-routed SDD Task, including documentation or configuration required by that implementation. Standalone documentation, planning, and configuration work stays with Codex. Preflight forbids modifying the installed workflow dependencies, not legitimate project dependency changes authorized by the native Plan.

## Runner evidence

`record-verification` remains an optional evidence-recording operation. `finish`, Repair Segment creation, and cleanup require completed inactive execution but do not require a Runner-specific Codex verification record. Native workflows retain their own verification gates. Structured Claude results still require test evidence for a successful coding result, and Codex still independently checks claims whenever the native workflow requires it.

## Safety policies

Permission Hooks, narrow automatic approval of repository-scoped read-only tools, user escalation for material side effects, timeout observation, backend-failure reporting, no silent executor fallback, lossless raw events, Session isolation, and exact UUID cleanup remain adapter safety mechanics. They do not determine native lifecycle outcomes.

## Verification

Contract tests will reject adapter-created user fix gates, unconditional Tracker operations, overlap rejection for merely available sequential work, and broad documentation/configuration ownership. Runner tests will prove that verification can be recorded but is not required for handoff, Repair Segment creation, or cleanup. The complete deterministic suite and both package validators must pass.
