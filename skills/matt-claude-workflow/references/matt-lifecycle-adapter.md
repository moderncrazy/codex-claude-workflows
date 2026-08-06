# Matt lifecycle adapter

Use this sequence to reconcile native `implement` with commit-based native `code-review` while preserving the configured Tracker as the only Ticket state.

## Ticket lifecycle

1. Read `docs/agents/issue-tracker.md`. Confirm it defines how to claim, resolve/close, comment, and query blockers. Stop at preflight when any operation is undefined; do not invent a second ledger.
2. Confirm every blocker is resolved, then claim the Ticket through the configured Tracker before work. Capture the current commit as the Review fixed point.
3. Run the selected implementer and required tests. Keep requirements, Ticket fields, Tracker state, and remote state under Codex control.
4. After successful verification, have the selected implementer create one local review checkpoint commit on the current task branch. Include its SHA in `commits`. Do not push, merge, amend, rebase, reset, or tag.
5. Run native `code-review` against the fixed point. Its `<fixed-point>...HEAD` diff must be non-empty and contain the complete work unit.
6. Present both Review axes without merging or reranking them. Do not start fixes automatically.
7. When the user requests fixes, resume the owning Execution Segment Session. For a cross-Segment finding, have Codex add one bounded Repair Segment. Run verification, create an additional local fix commit, and rerun native `code-review` against the original fixed point.
8. After the user accepts Review and verification evidence, resolve or close the Ticket through the configured Tracker. Record the implementation commit(s), test evidence, and Review disposition using its native comment/answer mechanism.
9. Recompute the native frontier and begin only an unblocked, unclaimed Ticket.

The accepted review checkpoint and any fix commits satisfy native `implement`'s commit requirement. Do not create an empty post-Review commit.

Do not add a cross-Ticket Final Review or Verify Review. Each Ticket ends with its native two-axis Review, accepted verification evidence, local commit(s), and configured Tracker transition.

Runner `implementation_complete` is not native completion and never resolves a Ticket. Clean its Work Unit only after step 8.

## Implicit-task lifecycle

Capture a fixed point, implement and verify, create the local review checkpoint commit, and run native `code-review`. Apply only user-requested fixes: resume the owning Session for a single-Segment finding or add a Repair Segment for a cross-Segment finding. Do not create or update a Ticket.
