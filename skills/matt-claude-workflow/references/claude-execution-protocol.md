# Claude Code execution protocol

## Preconditions

Run Claude in the trusted repository/worktree used by native Matt `implement`. Use non-interactive print mode. Do not configure or inspect the provider behind Claude Code; `sonnet` and `opus` are capability aliases selected by the work unit.

Read [claude-result.schema.json](claude-result.schema.json) and pass its JSON text to `--json-schema`.

For a Ticket, capture the Review fixed-point baseline before implementation and keep the Session ID in the Ticket's existing progress/comment channel. For an implicit task, keep the Session ID in the active Codex conversation. Do not create an extra ledger.

## New Session

Generate a valid UUID for every new Ticket or implicit task. Invoke the local `claude` executable with these semantic arguments:

```text
claude -p
  --session-id <uuid>
  --model <sonnet|opus>
  --permission-mode acceptEdits
  --output-format json
  --json-schema <schema-json>
  <work-unit-prompt>
```

The prompt contains only:

1. complete Ticket or implicit implementation brief;
2. relevant Spec and domain-context paths;
3. confirmed public test seams and Red–Green expectations;
4. exact allowed and forbidden scope;
5. focused/typecheck/full-suite verification requirements;
6. repository/worktree and fixed-point baseline;
7. instruction not to change requirements, seams, Tickets, tracker state, workflow, remote state, or Git history;
8. instruction to return the required structured result.

Do not use provider-specific model IDs or `--fallback-model`.

## Resume

Use non-interactive `--resume <session-id>` for missing context, approved permissions, or user-requested fixes to the same work unit. Verify the returned Session ID. Never use `--continue`, and never resume one Ticket's Session for another Ticket.

If the original Session cannot resume, report infrastructure failure. Do not create a replacement Claude Session for that work unit.

## Permissions

Default to `--permission-mode acceptEdits`. Never use `bypassPermissions` or `--dangerously-skip-permissions`.

When another permission is required, Claude returns `PERMISSION_REQUIRED` with exact requests. Show tool/command, scope, and reason to the user. If approved, resume the same Session with only the approved `--allowedTools` entries.

`--allowedTools` suppresses prompts; it does not limit availability. Use `--tools` and `--disallowedTools` for actual tool boundaries. Managed denials always win.

## Result handling

Validate the structured payload against the bundled schema and verify its `session_id`.

| Status | Action |
|---|---|
| `DONE` | Verify tests/evidence, then run native Matt `code-review` |
| `DONE_WITH_CONCERNS` | Present concerns; Codex/user decides whether Review can start |
| `NEEDS_CONTEXT` | Supply only missing work-unit context and resume the same Session |
| `BLOCKED` | Preserve native blocker state and report |
| `PERMISSION_REQUIRED` | Obtain user approval or stop |

Treat invalid JSON/Schema, missing required native Matt artifacts, a violated permission protocol, wrong Session ID, timeout, CLI absence, authentication/quota/service failure, Session creation failure, or failed resume as backend failure. Preserve native Ticket blockers and report:

1. failure category and exact affected Ticket/implicit task;
2. completed changes, tests, tracker state, and known Session ID;
3. safe user choices: repair the Claude environment and retry/resume; change the Ticket's persisted executor contract to Codex and reapprove it, or for an implicit task restate and reapprove the in-conversation Codex contract; or exit the workflow.

Never silently implement with Codex.
