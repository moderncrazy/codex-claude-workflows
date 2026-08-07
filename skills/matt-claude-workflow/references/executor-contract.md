# Executor contract

## Native work-unit contract

Every native implementation work unit must have exactly one direct executor contract:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: bounded implementation with approved interfaces
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

## Native-selected persistence

Persist the contract in the artifact or conversation selected by the native workflow. When that workflow represents the work unit with a Ticket, store the contract in that Ticket. When it persists the work unit in conversation, present the contract together with scope, acceptance criteria, fixed-point baseline, and confirmed test seams. Do not create a Ticket or routing file solely to persist it.

## Routing

Default to `claude-code + sonnet`. Use `opus` for architecture ambiguity, cross-module consistency, concurrency, security, data migration, difficult debugging, or a single work unit whose highest material risk requires it. Use Codex only for an explicit user override or a genuine Codex-only context, tool, or authorization dependency.

The user's natural-language instruction or direct edit to the selected native artifact has highest priority. When the native workflow selected a Ticket, persist the override there before execution. When it selected conversational persistence, restate and confirm the changed contract in conversation.

## Route summary

| Work unit | Agent | Model | Reason |
|---|---|---|---|
| W1 | claude-code | sonnet | bounded implementation with approved interfaces |
| W2 | claude-code | opus | security-sensitive implementation |
| W3 | codex | — | Codex-only authorization |

Reject affected work units when a contract is missing or invalid. Check overlapping files or shared mutable state only for work units the controller will actually run concurrently; sequential native work units may overlap.

## Execution Segments

The executor contract selects the native implementation work unit's implementer. Codex may define sequential Execution Segments immediately before Claude dispatch to bound a large implementation. Segments never become native workflow or Tracker data and never change native work-unit scope.
