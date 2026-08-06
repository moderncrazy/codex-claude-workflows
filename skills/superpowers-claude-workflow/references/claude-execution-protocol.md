# Claude Code execution protocol

## Preconditions

Run Claude only in the trusted repository/worktree selected by native Superpowers. Use non-interactive print mode. Do not configure or inspect the provider behind Claude Code; `sonnet` and `opus` are capability aliases selected by the Task.

Read [claude-result.schema.json](claude-result.schema.json) and pass its JSON text to `--json-schema`.

Persist each Task's Session ID, capability alias, attempt number, and latest structured result at `.superpowers/sdd/<plan>/task-N-claude-state.json`. Keep the native task brief/report/progress artifacts authoritative; this adapter file is not a second ledger.

## New Session

Generate a valid UUID before launch. Invoke the local `claude` executable with these semantic arguments:

```text
claude -p
  --session-id <uuid>
  --model <sonnet|opus>
  --permission-mode acceptEdits
  [--allowedTools <task-scoped-command-family> ...]
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
8. instruction that a tool result of `This command requires approval` must return `PERMISSION_REQUIRED` immediately without retrying variants, delegating to another Agent, or continuing implementation.

Do not pass provider-specific model IDs. Do not enable `--fallback-model` because fallback would defeat the capability contract.

## Initial command permissions

Treat approval of the Task executor contract as approval to run the named verification tools within that Task. Before a new Session, derive the smallest task-scoped command-family `--allowedTools` list from the focused tests, full suite, formatter, lint, and typecheck commands recorded in the persisted Plan. Do not require the user to approve harmless argument variations one at a time.

Choose a stable action prefix, not the whole original command and not the whole executable. Examples:

- `.venv/bin/pytest tests/unit/test_x.py -q` becomes `Bash(.venv/bin/pytest *)`, which also covers `.venv/bin/pytest --version`.
- `python -m pytest tests/unit/test_x.py` becomes `Bash(python -m pytest *)`, never `Bash(python *)`.
- `npm run lint` becomes `Bash(npm run lint *)`, never `Bash(npm *)`.
- Add narrow version or help probes for the same authorized executable when the action-family rule does not already cover them.
- Add `Bash(git status *)` and `Bash(git diff *)` for local read-only change inspection.

When the native Task explicitly requires its implementer to create a local checkpoint commit, exact `git add <owned-files>` and `git commit -m <approved-message>` commands may also be approved. Never pre-approve package installation, network commands, push, merge, deployment, history rewriting, a shell/interpreter wildcard, bare `Bash`, or `Agent` as a way around permissions.

Pass every derived family as a narrow `--allowedTools` rule. These rules reduce prompts; they do not expand the Task's file, behavior, or workflow scope. If Claude receives `This command requires approval` for anything outside these families, it must return `PERMISSION_REQUIRED` immediately with that exact command, scope, and reason. It must not retry command variants, spawn another Agent to run it, infer approval, or continue past required evidence.

## Resume

For context, permission continuation, or fix rounds 1–3, use non-interactive `--resume <session-id>` and the same schema. Re-pass the derived command-family `--allowedTools` rules and add only newly approved requests. Verify that the returned Session ID matches the intended task. Never use `--continue`, which can select the wrong task Session.

For fix rounds 4–5, generate a new UUID and provide the native task brief, prior report, Review findings, current diff/test state, and prior concerns. A new Session is an escalation, not a resume.

## Permissions

Default to `--permission-mode acceptEdits`. Never use `bypassPermissions` or `--dangerously-skip-permissions`.

If Claude needs a permission outside the automatic Task families, it returns `PERMISSION_REQUIRED` with exact requests. Show the requested tool/command, scope, and reason to the user. On approval, resume the same Session with only the approved additional `--allowedTools` entries.

`--allowedTools` suppresses prompts for matching tools; it is not an availability boundary. When the task needs an explicit tool boundary, set `--tools` to the required built-ins and use `--disallowedTools` for explicit denials. Managed denials always win.

## Result handling

Validate the structured payload against the bundled schema and verify its `session_id`.

| Status | Action |
|---|---|
| `DONE` | Verify native report and evidence, then enter native Review |
| `DONE_WITH_CONCERNS` | Present concerns; Codex/user decides whether Review can start |
| `NEEDS_CONTEXT` | Supply only listed `context_requests` and resume the same Session |
| `BLOCKED` | Stop the Task and report the blocker |
| `PERMISSION_REQUIRED` | Obtain user approval or stop |

Treat invalid JSON/Schema, missing required fields or native SDD artifacts, a violated permission protocol, wrong Session ID, timeout, CLI absence, authentication/quota/service failure, or failed resume as backend failure. Preserve native SDD state and report:

1. failure category and exact affected Task;
2. completed changes, tests, report/state paths, and known Session ID;
3. safe user choices: repair the Claude environment and retry/resume, explicitly change the persisted executor contract to Codex and reapprove it, or exit the workflow.

Never silently implement with Codex.
