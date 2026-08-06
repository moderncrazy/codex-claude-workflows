---
name: superpowers-claude-workflow
description: Run a Superpowers feature workflow with per-Task Codex and Claude implementer routing.
disable-model-invocation: true
---

# Superpowers Claude Workflow

## Overview

Keep Superpowers as workflow owner. Adapt only its SDD implementer dispatch while preserving native design, state, reviews, verification, and branch completion. Leave direct calls to original Superpowers Skills unchanged.

## Required references

Before writing the Plan, read [executor-contract.md](references/executor-contract.md). Before invoking or resuming Claude Code, read [claude-execution-protocol.md](references/claude-execution-protocol.md). Pass the bundled result Schema verbatim as machine input; keep it out of agent guidance.

## Workflow

1. **Preflight.** Confirm the required native Superpowers Skills exist. Check `claude` only when a Task may select it. Stop on missing or incompatible dependencies; do not install or patch them.
2. **Design.** **REQUIRED SUB-SKILL:** Use `superpowers:brainstorming`. Let Codex own exploration, decisions, the Design, self-review, and user approval. Record only the overall implementation-routing policy in the Design.
3. **Plan.** **REQUIRED SUB-SKILL:** Use `superpowers:writing-plans`. Let Codex write the Plan. Add one valid executor contract to every Plan Task.
4. **Gate.** Confirm that Tasks are sufficiently independent, executable in the current session, compatible with native SDD task/report state, and free of overlapping ownership. Validate every executor contract. If any condition fails, stop; do not switch to `superpowers:executing-plans` or inline coding.
5. **Confirm.** Show Task, agent, capability model, and reason. Persist user overrides into the Plan, revalidate, and obtain approval.
6. **Execute.** **REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development` as workflow owner. Follow its workspace, brief, report, progress, dependency, Review, Fix Loop, and completion rules. At each implementer dispatch, apply the adapter below.
7. **Finish.** Keep the native whole-branch Codex Final Review. **REQUIRED SUB-SKILL:** Use `superpowers:finishing-a-development-branch`. Do not add another final verification layer.

## Implementer adapter

- For `agent: codex`, dispatch the native Codex implementer.
- For `agent: claude-code`, invoke the execution protocol with the native task brief, scope, acceptance criteria, tests, worktree, and native `task-N-report.md` path.
- Keep every Task's source, tests, documentation, and configuration with its selected implementer. Do not edit a Claude-owned Task opportunistically.
- Store the Claude Session ID and result in `.superpowers/sdd/<plan>/`. Require the native Task report. Do not create another ledger.

## Review and fixes

- Keep native Codex Spec Review, Code Quality Review, and whole-branch Final Review.
- Resume the original Claude Session for Fix Loop rounds 1–3.
- Start a fresh Session for rounds 4–5. Upgrade `sonnet` to `opus`; keep a fresh `opus` when already upgraded.
- Re-run native reviews after fixes. Never treat Claude self-checks or `DONE` as Review.

## Common mistakes

- Starting at SDD instead of requirements.
- Routing Review or branch finishing to Claude.
- Creating custom state, hooks, plugins, or global routing files.
- Treating a new Session as a resumed Session.
- Silently using Codex after a Claude failure.
