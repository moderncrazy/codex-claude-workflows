# Runner P0 State, Permission Resolution, and Finish Design

## Goal

Make Runner state trustworthy, let Codex resolve a pending permission without approving it, and expose an explicit `finished` terminal state without taking ownership of native Superpowers or Matt review, verification, commit, or branch-finishing steps.

## Scope

This change includes only:

- Work Unit and Segment state consistency;
- separate Segment `attempt` and `resume_count` counters;
- `deny-permission` and `dismiss-permission` commands with an audit trail;
- an explicit `finished` state after native workflow completion;
- migration of persisted schema-version-1 Work Units to schema version 2.

This change does not add capability-based permissions, command normalization, permission-loop detection, richer tool events, automatic semantic progress, verification environment reuse, owned-file enforcement, or security threat profiles.

## Ownership Boundary

The Runner owns Claude process supervision, temporary Work Unit state, Session continuity, permission-request capture, and execution results. The native workflow remains authoritative for requirements, plans or tickets, review, independent verification, commits, tracker state, branch finishing, and the decision that native completion has occurred.

`implementation_complete` means that all Runner Execution Segments have produced an accepted structured implementation result. It does not mean that native review or verification has completed. Only Codex may assert native completion and transition the Work Unit to `finished`.

## Schema Version 2

### Work Unit status

Schema version 2 permits these persisted Work Unit states:

```text
initialized
running
permission_required
interrupted
backend_failure
implementation_complete
finished
```

`timeout_suspected` is a runtime observation, not a lifecycle state. A timeout observation is appended to `runtime.timeout_observations` while the Work Unit remains `running`.

`cleaned` is not persisted because successful cleanup removes the entire Work Unit directory. The cleanup command emits a final `cleaned` response after deletion.

### Segment status and counters

Segment states remain:

```text
pending
running
permission_required
interrupted
complete
failed
```

Each Segment contains:

```json
{
  "attempt": 1,
  "resume_count": 3
}
```

`attempt` counts distinct Claude Sessions used for that Segment. Assigning and starting a new Session increments it. Resuming the same Session increments `resume_count` and does not change `attempt`.

### Current result and result history

The top-level `result` is the structured result from the most recently completed invocation only. Before every invocation launch, the Runner sets `result` to null. Backend failure, permission interruption, or process interruption therefore cannot expose a result from an earlier invocation.

Every accepted structured result is also appended to `runtime.result_history` with its Segment ID, Session ID, launch token, result, and recorded timestamp. History is diagnostic evidence and never substitutes for the current result.

## Atomic Invocation Lifecycle

Before starting Claude, the Runner atomically:

1. rejects dispatch when a permission remains pending;
2. records any inactive prior `active_run` as stale diagnostic history;
3. clears the top-level `result`;
4. records a new launch token;
5. transitions the Work Unit and target Segment to `running`;
6. increments `attempt` for a new Session or `resume_count` for a resumed Session.

When the process ends, one atomic state update clears PID and active-run identity and moves the target Segment to exactly one terminal or resumable state:

| Outcome | Work Unit | Segment |
|---|---|---|
| Accepted `DONE` or `DONE_WITH_CONCERNS` | `implementation_complete` when all Segments are complete, otherwise `running` | `complete` |
| Pending permission | `permission_required` | `permission_required` |
| Controlled interruption or non-permission continuation | `interrupted` | `interrupted` |
| Backend or protocol failure | `backend_failure` | `failed` |

No completed invocation may leave its target Segment in `running`.

Reopening a completed Segment for a native review repair retains its Session and increments `resume_count` on resume. Replacing an abandoned Session increments `attempt` only when the replacement Session is started.

## Permission Resolution

The permissions object contains `initial`, `approved`, `pending`, and `resolved`. `resolved` is an append-only audit list. Every pending permission records the exact `segment_id` that produced it; resolution updates that Segment rather than inferring a target from the current process state.

All permission-resolution commands require a pending request and an exact expected tool-name match. Resolution happens under the state lock.

### Approve

`approve-permission` appends the narrow allow rule to `approved`, appends an `approved` resolution record, clears `pending`, and moves the Work Unit and active Segment to `interrupted`. A separate `resume` starts the process.

### Deny

`deny-permission` requires `--expected-tool-name` and `--reason`. It appends a `denied` resolution containing the original request and reason, clears `pending`, and moves the Work Unit and active Segment to `interrupted`. The Session remains available for a bounded continuation that directs Claude to use a safer approach.

### Dismiss

`dismiss-permission` requires `--expected-tool-name` and `--reason`. It appends a `dismissed` resolution containing the original request and reason, clears `pending`, and moves the Work Unit and active Segment to `interrupted`. Dismissal records no allow rule and no lasting denial rule.

Neither deny nor dismiss marks the Work Unit failed or abandons its Session. `replace-permission` is outside this design.

## Native Finish and Cleanup

The Runner automatically reaches `implementation_complete` after its final Segment completes. No handoff command is required at that point.

After native review, independent verification, commits or tracker updates, and branch finishing are complete, Codex calls:

```text
finish --state-dir <path> --native-workflow-complete
```

`finish` requires an inactive Runner, `implementation_complete`, all Segments complete, no pending permission, and the explicit native-completion assertion. It atomically transitions the Work Unit to `finished` and records `runtime.finished_at`.

`cleanup` requires an inactive `finished` Work Unit and the existing safe-path checks. It no longer accepts native completion as a substitute for `finish`. For a compatibility window, the parser may accept the old cleanup flag, but the flag cannot bypass the `finished` requirement.

Adding a Repair Segment is allowed from `implementation_complete`, but not from `finished`. Native findings must therefore be routed before final completion is asserted.

## Schema Migration

The state store accepts schema versions 1 and 2. Loading version 1 produces a version-2 in-memory state before contract validation; the next mutation persists version 2.

Migration rules are deterministic:

- add an empty `permissions.resolved` list;
- add `segment_id` to an existing pending permission by selecting the unique `permission_required` Segment; reject migration when no unique Segment exists;
- add `resume_count: 0` to every Segment;
- preserve existing `attempt`, except a Segment with a Session and `attempt: 0` becomes `attempt: 1`;
- convert Work Unit `timeout_suspected` to `running` and retain its existing timeout observations;
- convert Work Unit `cleaned` to `finished` only for validation of a surviving diagnostic copy; normal cleanup has no surviving state file;
- preserve `backend_failure`, `implementation_complete`, and all other valid statuses;
- do not infer `finished` from `runtime.implementation_handoff_at`;
- initialize `runtime.result_history` as an empty list without treating a pre-migration top-level result as a new invocation result.

Migration never edits native workflow state.

## Error Handling

- Resolving permission without a pending request returns `no_pending_permission`.
- An expected-tool mismatch returns `permission_mismatch` without changing state.
- `resume` continues to reject an unresolved pending permission.
- `finish` without the native-completion assertion returns `native_completion_required`.
- `finish` rejects active processes, incomplete Segments, pending permission, and any state other than `implementation_complete`.
- `cleanup` rejects every state other than `finished` and preserves the Work Unit on failure.
- Migration rejects unknown fields or values after applying only the explicit version-1 rules above.

## Verification Strategy

Tests must demonstrate:

1. a prior successful result is null after a later backend failure;
2. permission, interruption, and backend failure never leave a Segment running;
3. first Session launch produces `attempt: 1, resume_count: 0`;
4. same-Session resume increments only `resume_count`;
5. replacement Session launch increments `attempt`;
6. approve, deny, and dismiss clear pending, append the correct audit record, enter `interrupted`, and permit explicit resume;
7. mismatched or absent pending permission cannot mutate state;
8. `finish --native-workflow-complete` produces `finished` only after implementation completion;
9. cleanup rejects `implementation_complete` and accepts `finished`;
10. version-1 fixtures migrate deterministically;
11. both packaged workflows remain byte-identical to the shared Runner and preserve native Superpowers and Matt lifecycle ordering.

The implementation follows test-driven development in the canonical `shared/claude-runner/` tree. After tests pass, the shared assets are copied into both packaged skills and package validation plus the full test suite must pass.
