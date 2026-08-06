# Executor contract

## Contract

Every Superpowers implementation Task must contain exactly one direct executor contract:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: bounded implementation following established patterns
```

```yaml
executor:
  agent: codex
  reason: requires an authorization available only in the current Codex session
```

## Validation

| Field | Rule |
|---|---|
| `agent` | Required; only `claude-code` or `codex` |
| `model` | Required for `claude-code`; forbidden for `codex`; only `sonnet` or `opus` |
| `reason` | Required, non-empty, specific to the Task |

Do not add provider names, versioned model IDs, Session IDs, permission state, or workflow state to this contract.

## Routing

Default to `claude-code + sonnet`. Use `opus` when at least one material risk is present: architecture ambiguity, cross-module consistency, concurrency, security, data migration, or difficult debugging. Use Codex only for an explicit user override or a genuine Codex-only context, tool, or authorization dependency.

The user's natural-language instruction or direct Plan edit has highest priority. Update the persisted Plan before execution; never keep an out-of-band override.

## Route summary

Before SDD, show:

| Task | Agent | Model | Reason |
|---|---|---|---|
| Task 1 | claude-code | sonnet | bounded implementation |
| Task 2 | claude-code | opus | security-sensitive migration |
| Task 3 | codex | — | Codex-only authorization |

Reject the Plan before execution if any Task lacks a valid contract. Check overlapping files or shared state only for Tasks the controller will actually run concurrently; sequential Tasks may overlap.

## Execution Segments

The executor contract selects the native Task implementer. It does not describe Runner mechanics. Immediately before a Claude-owned Task is dispatched, Codex may divide that Task into sequential Execution Segments for bounded checkpoints. Never write Segment IDs, Session IDs, permissions, or Runner state into the Plan.
