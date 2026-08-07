---
name: superpowers-claude-workflow
description: Run a Superpowers feature workflow with per-Task Codex and Claude implementer routing.
disable-model-invocation: true
---

# Superpowers Claude Workflow

## Overview

Keep Superpowers as workflow owner. Adapt only the SDD implementer boundary; leave direct calls to original Superpowers Skills unchanged.

## Required references

Before the Plan, read [executor-contract.md](references/executor-contract.md). Before Claude dispatch, read [claude-execution-protocol.md](references/claude-execution-protocol.md). Pass the bundled result Schema verbatim as machine input.

## Workflow

1. **Preflight.** Confirm native Skills, Python 3, and Claude Code. In the active worktree, add tracked `/.tmp/` to `.gitignore` before recording the fixed point when absent. Keep installed workflow dependencies unchanged; project dependency work remains governed by the approved native Plan.
2. **Design.** **REQUIRED SUB-SKILL:** Use `superpowers:brainstorming`. Codex owns requirements, decisions, Design, self-review, and approval.
3. **Plan.** **REQUIRED SUB-SKILL:** Use `superpowers:writing-plans`. Add one executor contract to each native Plan Task. Do not add Runner Work Units or Execution Segments to the Plan.
4. **Gate and confirm.** Require SDD-compatible independent Tasks, validate contracts, show Task/agent/capability/reason, persist overrides, and obtain approval.
5. **Execute.** **REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development`. Preserve its workspace, brief, report, progress, Review, Fix Loop, and completion rules. Apply the adapter only when dispatching each implementer.
6. **Finish.** Keep native Task Review and whole-branch Final Review. **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`. Add no extra universal review layer.

## Implementer adapter

- `agent: codex`: use the native Codex implementer unchanged.
- `agent: claude-code`: create one Runner Work Unit for the native Task, define Execution Segments immediately before dispatch, and run this Skill's `scripts/claude-runner/claude_runner.py`.
- Keep native `.superpowers` artifacts authoritative. Runner state lives only under ignored `.tmp/codex-claude-workflows/<work-unit-id>/`.
- Keep every change required inside a Claude-routed coding Task with Claude. Standalone documentation, planning, and configuration work remains with Codex. Never silently fall back to Codex for a Claude-routed coding Task.

## Review and fixes

- Codex performs native Spec Review, Code Quality Review, Final Review, and verification.
- Route a finding owned by one Segment back to that Segment Session. Create a Codex-defined Repair Segment for cross-Segment findings.
- Preserve native Fix Loop rounds 1–5: resume for rounds 1–3; use a fresh Session for rounds 4–5 and upgrade `sonnet` to `opus`.
- Runner `implementation_complete` is not native completion. After native Review, verification, and branch finishing, call `finish --native-workflow-complete` to enter `finished`, then clean its UUID directory.

## Common mistakes

- Starting at SDD instead of requirements.
- Persisting Execution Segments in the native Plan.
- Routing Review or branch finishing to Claude.
- Treating a Progress Claim as verified evidence.
- Adding global hooks, a daemon, a plugin, or upstream Skill changes.
