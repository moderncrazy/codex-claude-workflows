# Runner Permission and Interrupt Reliability Design

## Goal

Make the existing permission broker usable with real Claude Code permission
denials, and make `interrupt` finish within a deterministic bounded time when
Claude does not respond to a graceful interrupt.

The change must preserve the native Superpowers and Matt workflows. It is a
Runner reliability correction, not a new routing, review, Tracker, or commit
policy.

## Observed Failures

### Permission denial does not become pending

The real regression produced `PermissionDenied` Hook calls for commands that
were outside the narrow allowlist. The Hook stopped those commands, but the
Work Unit retained:

```text
permissions.pending = null
permissions.resolved = []
```

Only `PermissionRequest` currently creates a pending broker request.
`PermissionDenied` stores the raw event in
`runtime.last_permission_denied` and stops Claude, so `deny-permission` and
`dismiss-permission` have nothing to resolve.

### Interrupt has no escalation deadline

`interrupt` sends one `SIGINT` to the Runner-owned Claude process group. It
does not establish a deadline or escalate when the child delays or ignores
that signal. `terminate` already has one `SIGTERM` to `SIGKILL` grace period,
but that machinery is not used by `interrupt`.

## Design

### 1. Promote real `PermissionDenied` events into the existing broker

`handle_permission_denied` will use the same state preconditions and pending
record shape as `handle_permission_request`:

- exactly one Segment must be `running`;
- no permission may already be pending;
- the complete Hook request is preserved verbatim;
- `segment_id`, `tool_name`, `tool_input`, and `received_at` are recorded;
- the Hook continues to stop Claude outside the prompt.

The existing `PermissionRequest` behavior remains unchanged. The Runner will
not parse Claude's natural-language response or infer command capabilities.
Once the child exits, the Supervisor's existing `pending` check transitions
the Work Unit and Segment to `permission_required`.

If there is no unique running Segment, the request is malformed, or another
permission is already pending, the Hook fails closed without overwriting
state. Approval, denial, dismissal, and same-Session resume keep their current
contracts.

No `PreToolUse` Hook is added. This preserves Claude's native permission path
and the existing two-Hook integration boundary.

### 2. Give `interrupt` bounded, staged escalation

An interrupt request will apply these stages to the validated Runner-owned
process group:

```text
SIGINT
  -> wait termination_grace_seconds
SIGTERM
  -> wait termination_grace_seconds
SIGKILL
```

The default remains 15 seconds per stage, so an unresponsive process is
forcibly stopped in approximately 30 seconds plus polling and process-reaping
overhead. The existing `termination_grace_seconds` setting is reused; no new
configuration option is introduced.

`terminate` retains its existing `SIGTERM -> grace -> SIGKILL` behavior.
Only one control action may own a running invocation. The runtime
`control_requested` record will include the requested action, current stage,
request time, and stage time so status inspection can distinguish a requested
interrupt from ordinary running work without adding a new lifecycle enum.

The Work Unit remains `running` while its validated child is alive and becomes
`interrupted` after the process exits. The Supervisor continues to clear the
active process identity and does not retain a stale structured result.

## Files and Packaging

The canonical implementation remains under `shared/claude-runner/runner/`.
Tests remain under `tests/`. After the canonical implementation passes, the
existing shared-assets synchronizer will update the hard copies in:

- `skills/superpowers-claude-workflow/scripts/claude-runner/runner/`
- `skills/matt-claude-workflow/scripts/claude-runner/runner/`

No native Matt or Superpowers skill routing documents need behavioral changes.
Protocol wording will change only if required to describe the corrected
mechanical behavior.

## Test Strategy

### Permission RED/GREEN

Add a Hook-level test that invokes `PermissionDenied` against one running
Segment and expects a pending request containing the exact raw event. It must
fail before the implementation because current code leaves `pending` null.

Add a fake-Claude end-to-end scenario that invokes the installed
`PermissionDenied` Hook, exits, and expects:

- Work Unit and Segment status `permission_required`;
- an exact pending request;
- `deny-permission` or `dismiss-permission` clears pending and audits the
  resolution;
- explicit resume reuses the same Session.

Also cover fail-closed behavior for duplicate pending permissions and for the
absence of one unique running Segment.

### Interrupt RED/GREEN

Add a fake Claude scenario that ignores both `SIGINT` and `SIGTERM`. Invoke
public `interrupt` with a short configured grace period and assert:

- the control command returns promptly;
- runtime control evidence advances through `interrupt`, `terminate`, and
  `kill` stages;
- the Runner process exits within the bounded two-stage interval;
- Work Unit and Segment end as `interrupted`;
- the invocation can resume with the same Session afterward.

This test must fail or time out before the implementation because current
`interrupt` never escalates beyond `SIGINT`.

### Full verification

Run the complete unit suite, shared-assets synchronization check, package
validation, and `git diff --check`. Then exercise the packaged skills with real
Claude Code:

1. trigger a narrow, previously unapproved safe command;
2. confirm a real `PermissionDenied` event creates pending state;
3. resolve it with deny or dismiss and resume the same Session;
4. start a separate long-running Work Unit and confirm public `interrupt`
   reaches `interrupted` within the configured bound.

Real regression artifacts stay under an ignored or system temporary directory
and are removed after evidence is summarized.

## Acceptance Criteria

- A real `PermissionDenied` Hook request becomes the single pending permission
  for its running Segment without natural-language parsing.
- `approve-permission`, `deny-permission`, and `dismiss-permission` can resolve
  that request and explicit resume reuses the same Claude Session.
- Claude cannot continue trying alternate tools after a pending permission has
  stopped the invocation.
- `interrupt` escalates from `SIGINT` to `SIGTERM` to `SIGKILL` using two
  configured grace periods.
- An unresponsive child cannot leave a Work Unit running indefinitely after
  an accepted interrupt request.
- State transitions, process identity checks, stale-result clearing, and
  `FINISHED` behavior continue to pass their existing tests.
- Both packaged skills remain exact hard copies of the canonical shared Runner.
- Matt and Superpowers native workflow logic is unchanged.
