# Matt Native Routing Boundary

## Problem

`matt-claude-workflow` currently owns scale and Tracker rules that belong to the native Matt Skills. This lets the wrapper classify work such as test infrastructure as Spec/Ticket work and block on `docs/agents/issue-tracker.md`, even though no native Skill selected that path. It also makes the wrapper sensitive to future changes in Matt's routing policy.

## Design

Keep the wrapper as a thin implementer adapter:

- Native Matt Skills choose the workflow path, including whether work is implicit or uses Spec/Tickets.
- Native Matt Skills own Tracker prerequisites and tracer-bullet decomposition.
- The wrapper must not infer a path from work category, step count, anticipated tracer bullets, session count, or its own scale heuristic.
- After the native workflow identifies one implementation work unit, the wrapper adds only the executor contract and routes that work unit to Codex or Claude Code.
- Native Review, commits, Tracker operations, and completion remain unchanged.

The wrapper may describe how its executor contract attaches to an implicit task or Ticket, but those descriptions are reactive adapter behavior, not routing criteria.

## Compatibility

The current native Matt Skills may still require `docs/agents/issue-tracker.md`, including during `code-review`. The wrapper neither suppresses nor broadens that requirement. A missing-Tracker stop is valid only when produced by the selected native flow, not by a wrapper-owned classification.

Future native routing changes require no wrapper update unless the implementation dispatch seam itself changes.

## Verification

- Contract tests reject wrapper-owned scale, tracer-count, work-category, and Tracker-path rules.
- Contract tests require explicit delegation of path and Tracker decisions to native Matt Skills.
- Existing tests continue to prove the wrapper changes only implementer dispatch and preserves native Review and completion.
- A pressure scenario confirms that a test-infrastructure task is not independently classified by the wrapper.

## Out of Scope

- Modifying installed native Matt Skills.
- Changing native Tracker setup, Spec/Ticket structure, tracer-bullet rules, Review, or commit behavior.
- Removing Tracker requirements that originate in the native workflow.
