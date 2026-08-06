# Matt lifecycle adapter

Use this adapter only to reconcile native `implement` with commit-based native `code-review`. The Native Workflow decides Review disposition, fixes, Tracker operations, verification, commits, and completion.

## Common implementation path

1. Capture the current commit as the Review fixed point.
2. Run the selected implementer and the tests required by native `implement`.
3. Create one local **compatibility checkpoint** commit so native `code-review` receives a non-empty `<fixed-point>...HEAD` range. This ordering reconciles the current Skills; it is adapter compatibility behavior, not Matt lifecycle authority. Include its SHA in `commits`. Do not push, merge, amend, rebase, reset, or tag.
4. Run native `code-review` against the fixed point and present its Standards and Spec axes without merging or reranking them.
5. Follow the Native Workflow's disposition. When the Native Workflow continues implementation for an in-scope finding, resume the owning Execution Segment Session. For a cross-Segment finding, add one bounded Repair Segment. Actual fixes receive their required tests and a local commit; when the Native Workflow invokes `code-review` again, keep the original fixed point.
6. Complete according to native `implement` and `code-review`. The compatibility checkpoint and commits for actual fixes satisfy the local commit requirement; create no empty post-Review commit.

## Ticket path

Read `docs/agents/issue-tracker.md`. Apply a claim, status change, comment, close operation, blocker query, or frontier action only when that operation is explicitly defined by the configured Tracker and selected by the Native Workflow. Keep the configured Tracker as the only Ticket ledger.

Do not add a cross-Ticket Final Review or Verify Review. Runner `implementation_complete` never changes Ticket state. Clean its Work Unit only after native Ticket completion.

## Implicit-task lifecycle

Use the common implementation path without reading or changing a Tracker. Do not create or update a Ticket.
