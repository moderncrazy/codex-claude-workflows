# Executor contract

## Ticket contract

Every implementation Ticket must contain exactly one direct executor contract:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: bounded tracer-bullet implementation with approved interfaces
```

```yaml
executor:
  agent: codex
  reason: requires an authorization available only in the current Codex session
```

| Field | Rule |
|---|---|
| `agent` | Required; only `claude-code` or `codex` |
| `model` | Required for `claude-code`; forbidden for `codex`; only `sonnet` or `opus` |
| `reason` | Required, non-empty, specific to the work unit |

Do not store provider names, versioned model IDs, Session IDs, permission state, or tracker lifecycle inside the executor contract.

## Implicit-task contract

For a single-session native Matt Implement call, present the same contract in conversation together with scope, acceptance criteria, fixed-point baseline, and confirmed test seams. Do not create a Ticket or routing file solely to persist it.

## Routing

Default to `claude-code + sonnet`. Use `opus` for architecture ambiguity, cross-module consistency, concurrency, security, data migration, difficult debugging, or a single work unit whose highest material risk requires it. Use Codex only for an explicit user override or a genuine Codex-only context, tool, or authorization dependency.

The user's natural-language instruction or direct Ticket edit has highest priority. For Tickets, persist the override before execution. For an implicit task, restate and confirm the changed contract in conversation.

## Route summary

| Ticket | Agent | Model | Reason |
|---|---|---|---|
| T1 | claude-code | sonnet | bounded vertical slice |
| T2 | claude-code | opus | security-sensitive migration |
| T3 | codex | — | Codex-only authorization |

Reject the batch before executing affected work units when a contract is missing/invalid or concurrently available Tickets claim overlapping files or shared mutable state.
