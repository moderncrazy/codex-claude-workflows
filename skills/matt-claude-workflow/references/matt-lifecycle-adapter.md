# Matt lifecycle adapter

Use this adapter only to reconcile native `implement` review-before-commit ordering with the commit-range input expected by native `code-review`. Preserve the native Standards and Spec axes, but adapt their input to the current working tree. The Native Workflow decides Review disposition, fixes, Tracker operations, verification, commits, and completion.

## Common implementation path

1. Capture the current commit as the Review fixed point.
2. Run the selected implementer and the tests required by native `implement`.
3. Run a **working-tree Review** with native `code-review`'s Standards and Spec axes. Replace only its commit-range input with `git status --short`, `git diff --stat <fixed-point>`, and `git diff <fixed-point>`. Use `git ls-files --others --exclude-standard` to identify untracked implementation files and include their contents in both Review inputs. A non-empty working-tree change is sufficient; do not commit before Review merely to make `<fixed-point>...HEAD` non-empty.
4. Present the native Standards and Spec reports without merging or reranking them.
5. Follow the Native Workflow's disposition. When it continues implementation for an in-scope finding, resume the owning Execution Segment Session; for a cross-Segment finding, add one bounded Repair Segment. Run the tests required for each fix, keep the original fixed point, and repeat the working-tree Review over the complete current change. Do not commit review fixes separately.
6. After native Review is accepted, commit the accepted working-tree changes to the current branch as required by native `implement`, and record the resulting SHA as native completion evidence. If any implementation file changes after the accepted Review, repeat Review before committing. Do not push, merge, amend, rebase, reset, or tag.
7. Complete according to native `implement` and `code-review`; create no empty post-Review commit.

## Ticket path

Read `docs/agents/issue-tracker.md`. Apply a claim, status change, comment, close operation, blocker query, or frontier action only when that operation is explicitly defined by the configured Tracker and selected by the Native Workflow. Keep the configured Tracker as the only Ticket ledger.

Do not add a cross-Ticket Final Review or Verify Review. Runner `implementation_complete` never changes Ticket state. Clean its Work Unit only after native Ticket completion.

## Implicit-task lifecycle

Use the common implementation path without reading or changing a Tracker. Do not create or update a Ticket.
