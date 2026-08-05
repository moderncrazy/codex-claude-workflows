---
name: matt-claude-workflow
description: Use when the user explicitly invokes $matt-claude-workflow for a Matt Pocock workflow that needs per-work-unit implementer routing.
---

# Matt Claude Workflow

## Overview

Keep Matt's Skills as workflow owner. Adapt only implementation while preserving Spec/Ticket state, test seams, dual Codex Review, commits, and tracker behavior. Leave original Skills unchanged.

## Required references

Before routing work, read [executor-contract.md](references/executor-contract.md). Before invoking or resuming Claude Code, read [claude-execution-protocol.md](references/claude-execution-protocol.md) and its [result Schema](references/claude-result.schema.json).

## Workflow

1. **Preflight.** Confirm the native Skills and tracker setup required by the selected path. Check `claude` only when a work unit may select it. Stop on missing dependencies; do not substitute, install, or patch Skills.
2. **Clarify.** **REQUIRED SUB-SKILL:** Use `grill-with-docs` when durable glossary/ADR documentation is useful; otherwise use `grill-me`. Let Codex own requirements, domain decisions, unresolved questions, and approval.
3. **Choose scale.** Use the implicit-task path for one cohesive session. Use the Spec/Ticket path for cross-session work or multiple tracer bullets.
4. **Confirm seams.** **REQUIRED SUB-SKILL:** Use `tdd` to select the highest useful public test seams. Obtain the confirmation required by the native flow.
5. **Implement.** **REQUIRED SUB-SKILL:** Use `implement` as workflow owner. Apply the implementer adapter below.
6. **Review and commit.** **REQUIRED SUB-SKILL:** Use `code-review` with the captured fixed point and its Standards/Spec Codex reviewers. Preserve report-only semantics. Follow `implement` for verification, commit, and tracker updates.

## Implicit-task path

Present one in-conversation executor contract with scope, acceptance criteria, fixed point, and confirmed seams. Obtain approval. Do not create a Ticket or routing file. If the work reveals independent slices, durable blockers, or cross-session coordination, stop and use the Spec/Ticket path.

## Spec/Ticket path

1. **REQUIRED SUB-SKILL:** Use `to-spec`. Add the overall routing policy without assigning each Ticket there.
2. **REQUIRED SUB-SKILL:** Use `to-tickets`. Add one executor contract per Ticket and preserve native blocking edges.
3. Show Ticket, agent, capability model, and reason. Persist overrides, revalidate, and obtain user approval before implementation.
4. Process only unblocked Tickets. Reuse native Spec, Ticket, tracker, and commit state; do not create another ledger.

## Implementer adapter

- For `agent: codex`, use the native Codex implementation path.
- For `agent: claude-code`, invoke the protocol with the Ticket/implicit brief, Spec, confirmed seams, scope, tests, repository, and fixed point.
- Create a fresh Claude Session for each Ticket. Keep its ID in the Ticket's existing progress/comment channel. Never reuse a Session across Tickets.
- Keep all source, test, documentation, and configuration changes for a work unit with its selected implementer.

## Review and fixes

- Report both native Review axes without automatically starting a fix loop.
- Ask the user how to handle findings. Resume the same work-unit Session only when the user requests fixes, then re-run verification and native Review.
- Do not add a cross-Ticket Final Review or Verify Review.

## Common mistakes

- Replacing `to-spec`/`to-tickets` with generic PRD/issue Skills.
- Creating a pseudo-Ticket for an implicit task.
- Reusing Claude Sessions across Tickets.
- Auto-fixing Review findings or silently falling back to Codex.
