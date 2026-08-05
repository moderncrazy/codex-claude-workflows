# Claude Code execution protocol

## Preconditions

Run Claude only in the trusted repository/worktree selected by native Superpowers. Use non-interactive print mode. Do not configure or inspect the provider behind Claude Code; `sonnet` and `opus` are capability aliases selected by the Task.

Read [claude-result.schema.json](claude-result.schema.json) and pass its JSON text to `--json-schema`.

## New Session

Generate a valid UUID before launch. Invoke the local `claude` executable with these semantic arguments:

```text
claude -p
  --session-id <uuid>
  --model <sonnet|opus>
  --permission-mode acceptEdits
  --output-format json
  --json-schema <schema-json>
  <task-prompt>
```

The task prompt contains only:

1. native SDD task brief and required report path;
2. relevant Design/Plan paths;
3. allowed scope and explicit forbidden scope;
4. acceptance criteria and test commands;
5. repository/worktree path and current task baseline;
6. instruction not to expand scope, push, merge, deploy, rewrite history, or change the workflow;
7. instruction to return the required structured result.

Do not pass provider-specific model IDs. Do not enable `--fallback-model` because fallback would defeat the capability contract.

## Resume

For context, permission continuation, or fix rounds 1–3, use non-interactive `--resume <session-id>` and the same schema. Verify that the returned Session ID matches the intended task. Never use `--continue`, which can select the wrong task Session.

For fix rounds 4–5, generate a new UUID and provide the native task brief, prior report, Review findings, current diff/test state, and prior concerns. A new Session is an escalation, not a resume.

## Permissions

Default to `--permission-mode acceptEdits`. Never use `bypassPermissions` or `--dangerously-skip-permissions`.

If Claude needs another permission, it returns `PERMISSION_REQUIRED` with exact requests. Show the requested tool/command, scope, and reason to the user. On approval, resume the same Session with only the approved `--allowedTools` entries.

`--allowedTools` suppresses prompts for matching tools; it is not an availability boundary. When the task needs an explicit tool boundary, set `--tools` to the required built-ins and use `--disallowedTools` for explicit denials. Managed denials always win.

## Result handling

Validate the structured payload against the bundled schema and verify its `session_id`.

| Status | Action |
|---|---|
| `DONE` | Verify native report and evidence, then enter native Review |
| `DONE_WITH_CONCERNS` | Present concerns; Codex/user decides whether Review can start |
| `NEEDS_CONTEXT` | Supply only missing task context and resume the same Session |
| `BLOCKED` | Stop the Task and report the blocker |
| `PERMISSION_REQUIRED` | Obtain user approval or stop |

Treat invalid JSON/Schema, missing required fields or native SDD artifacts, a violated permission protocol, wrong Session ID, timeout, CLI absence, authentication/quota/service failure, or failed resume as backend failure. Preserve native SDD state and report:

1. failure category and exact affected Task;
2. completed changes, tests, report/state paths, and known Session ID;
3. safe user choices: repair the Claude environment and retry/resume, explicitly change the persisted executor contract to Codex and reapprove it, or exit the workflow.

Never silently implement with Codex.
