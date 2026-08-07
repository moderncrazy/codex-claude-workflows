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

## Native Tracker boundary

Follow the selected native workflow and its configured Tracker instructions unchanged. This adapter neither requires nor suppresses Tracker setup, chooses a Ticket path, decomposes tracer bullets, nor invents Tracker operations. Read or change Tracker state only when the native workflow requires that operation.

Do not add a cross-Ticket Final Review or Verify Review.
