# Parse Duration Dual Real-Workflow Regression Design

## Purpose

Verify the current working-tree versions of `superpowers-claude-workflow` and
`matt-claude-workflow` by running the same small feature through two isolated,
real Claude Code development cycles. The regression tests workflow ownership,
review repair, session continuity, and commit ordering rather than only Runner
mechanics.

## Shared Product Requirement

Each regression repository provides this public API:

```python
def parse_duration(text: str) -> int:
    """Return a positive duration in milliseconds."""
```

Accepted input consists of optional surrounding whitespace, a positive whole
number, and one lowercase unit with no internal whitespace:

- `ms` returns the number unchanged.
- `s` multiplies the number by 1,000.
- `m` multiplies the number by 60,000.

The function raises `ValueError` for zero, negative values, decimals, missing
numbers, missing units, uppercase units, unknown units, internal whitespace,
or trailing characters. Non-string inputs raise `TypeError`. The implementation
uses only the Python standard library.

Each repository contains:

- `duration_parser/__init__.py`, exporting `parse_duration`;
- `duration_parser/parser.py`, containing the implementation;
- `tests/test_parser.py`, using `unittest` with no third-party dependencies;
- `README.md`, documenting the API and verification command;
- a tracked `.gitignore` containing `/.tmp/` before the implementation fixed
  point.

The focused and full verification command is:

```bash
python3 -m unittest discover -s tests -v
```

## Isolation and Skill Source

Choose one timestamp-and-random-suffix run directory below
`/.tmp/real-regressions/`, then create two independent Git repositories inside
it, one named `superpowers` and one named `matt`. They have distinct baselines,
commits, Claude Work Units, and Claude Session IDs. No implementation or native
workflow state is copied between them.

Both regressions execute the Skill packages directly from this repository's
current working tree. They must not use an older installed copy from
`~/.agents/skills`. Runner state and raw evidence remain in each regression
repository until the final report is accepted.

## Superpowers Regression

The current `superpowers-claude-workflow` owns preflight, native Design, native
Plan, executor contract validation, SDD, Task Review, whole-branch Final
Review, verification, and local branch finishing.

Use one implementation Task routed to `claude-code` with capability alias
`sonnet`. Claude writes the package, tests, and README using test-first
development. Codex retains all review and workflow decisions. Native
`.superpowers` artifacts remain authoritative; Runner state remains under the
ignored Work Unit directory.

After the first Spec and Code Quality Review, route one accepted, in-scope
finding to the same Claude Session. If Review finds no natural defect, use a
test-hardening request that adds a missing assertion for one already-required
invalid-input category without changing the API or product contract. Rerun the
Task Review after the repair, then run whole-branch Final Review and final
verification. Keep the completed branch local; do not push or merge.

## Matt Regression

The current `matt-claude-workflow` uses the native implicit-task path. Codex
owns clarification, the public seam, the fixed point, native `implement`, the
separate Standards and Spec Review dispositions, verification, and completion.
No Ticket or Tracker state is created.

Use one implementation Work Unit routed to `claude-code` with capability alias
`sonnet`. Claude writes the package, tests, and README using Red-Green evidence
and leaves the working tree uncommitted. Codex supplies the complete working
tree to both native Review axes using:

```bash
git status --short
git diff --stat <fixed-point>
git diff <fixed-point>
git ls-files --others --exclude-standard
```

The contents of every untracked implementation file are included in both
Review inputs. No compatibility or checkpoint commit is created before
Review.

Route one accepted, in-scope finding to the same Claude Session. If neither
axis finds a natural defect, use the same kind of contract-preserving test
hardening request as the Superpowers regression. Keep the repair uncommitted,
rerun tests, and rerun both Review axes against the original fixed point and
the complete current working tree. Only after both axes accept the change does
native `implement` create one local commit containing the reviewed result.

## Evidence and Pass Criteria

Each regression preserves:

- the exact current Skill source path and its relevant file hashes;
- the baseline SHA and final SHA;
- the Claude capability alias, Work Unit ID, and matching initial/resumed
  Session ID;
- raw Runner stdout/stderr event evidence and structured results;
- explicit Red and Green test evidence;
- native Design/Plan/SDD or implicit-task lifecycle evidence;
- first Review reports, the accepted repair request, and post-repair Review;
- final focused/full test output and `git diff --check` output;
- final repository status and prohibited-action confirmation.

The overall result is PASS only when both real Claude-backed workflows finish
their complete native cycles. A fake-Claude result, silent Codex implementation
fallback, backend failure, unmatched resume Session, missing review round,
pre-Review Matt commit, failed verification, or shared state between the two
repositories is a failure. The run performs no push, merge, deployment,
history rewrite, dependency installation, or evidence cleanup.
