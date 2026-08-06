# Shared Claude Runner Design

**Status:** Accepted

## Objective

Replace direct, opaque Claude Code invocations in `superpowers-claude-workflow` and `matt-claude-workflow` with a deterministic per-Work-Unit Runner while preserving both Native Workflows unchanged. The change must reduce Codex context consumption, eliminate prompt-dependent permission pauses, expose useful progress, and retain lossless evidence without granting the Runner semantic authority.

## Non-goals

- Do not modify upstream Superpowers or Matt Skills.
- Do not add Codex hooks, a Codex plugin, SessionStart injection, or a global routing file.
- Do not install a global Runner daemon or alter ordinary Codex and Claude Code usage.
- Do not let the Runner plan tasks, choose reviewers, interpret findings, select tests, approve permissions, or decide completion.
- Do not inspect or enforce the concrete provider model behind Claude Code capability aliases.

## Ownership boundaries

### Native Workflow

Superpowers continues to own brainstorming, Design, Plan Tasks, SDD state, per-Task Spec and quality Review, whole-branch Final Review, verification, and branch finishing. Matt continues to own Spec, Ticket or implicit-task state, TDD seams, fixed-point Review, commits, Tracker transitions, and its native user-approved fix behavior.

### Codex

Codex owns requirements, documents, executor contracts, capability aliases, Execution Segment definitions, permission decisions, timeout decisions, Review, verification, repair routing, and final workflow cleanup.

### Runner

The Runner owns only deterministic adapter mechanics: process supervision, event capture, Reporter and permission Hook injection, Adapter State transitions, locking, recovery commands, and exact lifecycle notifications.

### Claude Code

Claude Code owns implementation inside the approved Work Unit and Segment scope. Its progress and completion statements remain claims until independently verified.

## Work Unit and Segment model

One native Task, Ticket, or implicit task maps to one Work Unit. A small Work Unit has one `implement-and-verify` Execution Segment. Codex may split a large Work Unit into sequential Execution Segments immediately before dispatch; the native Plan, Spec, Ticket, blocking edges, Review gates, and completion state do not change.

Each Segment has one primary Claude Session. Permission handling, missing-context continuation, and uninterrupted work inside that Segment resume the same Session. After a Segment has completed and its declared evidence is verified, the next Segment may use a fresh Session with the same executor and Capability Model. Codex, not the Runner, supplies the new Session with compact verified context.

Accepted Review findings that belong to one Segment resume that Segment's Session. Cross-Segment findings, or findings whose original Session is no longer safe to reuse because of context size, become a Codex-defined Repair Segment. Native Review and fix-loop rules remain authoritative.

## Runtime location and cleanup

Before the first Work Unit, Codex ensures the project root `.gitignore` contains `/.tmp/` and includes that configuration change before the implementation fixed point. The Runner resolves the actual execution root from Claude's working directory, whether that is the current working tree or a user-approved worktree.

Each Work Unit uses:

```text
<working-root>/.tmp/codex-claude-workflows/<work-unit-id>/
├── work-unit.json
├── raw-events.jsonl
└── raw-stderr.log
```

The three named files are the only persistent Work Unit files. Lock and atomic-replacement files may exist only while a state operation is active; Reporter configuration and Hook settings are generated in memory and passed to Claude Code as inline JSON. The Runner must never delete `.tmp`, `.tmp/codex-claude-workflows`, or another Work Unit. Successful cleanup occurs only after the Native Workflow's final Review, verification, and finishing behavior completes. Failure, interruption, unresolved permission, or timeout suspicion preserves the directory for recovery.

## Adapter State

`work-unit.json` is the only authoritative Adapter State. It records schema version, Work Unit identity and native reference, working root and fixed point, executor and Capability Model, Segment definitions and Session IDs, process identity, timestamps, timeout observations, permission rules and pending requests, Progress Claim references, declared and verified evidence, commits, and implementation result.

Native Task, Ticket, Review, verification, and completion state remain outside it. Markdown briefs, progress files, permission continuations, repair prompts, and implementation reports are not additional state ledgers. The Runner executable is the only writer: every command takes the Work Unit lock, validates the current transition, writes a complete temporary JSON document, fsyncs it, and atomically replaces the prior file.

## Claude invocation

The Runner uses non-interactive Claude Code with:

```text
claude -p
  --session-id <uuid> | --resume <session-id>
  --model <sonnet|opus>
  --permission-mode acceptEdits
  --allowedTools <approved-rules...>
  --output-format stream-json
  --mcp-config <inline-reporter-json>
  --settings <inline-hook-json>
  --json-schema <bundled-result-schema>
  <segment-prompt>
```

Do not use `--strict-mcp-config`, `--include-partial-messages`, `--fallback-model`, `bypassPermissions`, or `--dangerously-skip-permissions`. Existing user MCP servers such as CodeGraph remain available subject to Claude Code permissions and managed policy.

The requested `sonnet` or `opus` alias is the Capability Model. Any concrete model usage reported by Claude Code remains only in the lossless raw event file and is not enforced or promoted into the executor contract.

## Lossless event handling

The Runner consumes every stdout line so the child pipe cannot block. It writes the exact received bytes to `raw-events.jsonl` before parsing a copy. It writes stderr bytes unchanged to `raw-stderr.log`. Unknown event and tool payloads remain opaque; the Runner never rewrites, truncates, summarizes, reranks, or semantically filters them.

The Runner may inspect only protocol envelopes needed for mechanics: JSON validity, event position, Session ID, process result, tool-call identifier pairing, and the exact identity of its own Reporter tool. Complete raw output is not sent to Codex by default. Codex receives lifecycle events, Runtime Facts, verbatim Progress Claims, permission and failure events, timeout suspicions, and the final structured result. It reads raw ranges on demand for audit or diagnosis.

## Active progress reporting

Each invocation adds, rather than replaces, a uniquely named local stdio MCP server exposing `codex_claude_runner.report_progress`. The server uses newline-delimited UTF-8 JSON-RPC and writes no non-protocol output to stdout, consistent with the current MCP stdio transport specification: <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>.

Claude calls the tool only at semantic transitions: Segment start, before an expected long operation, verification result, Segment completion, blocker, permission concern, and completion claim. The input contains `kind`, verbatim `message`, verbatim `next_action`, and optional `evidence_refs`.

The Runner stores the claim unchanged and wraps it with a Work Unit ID, receipt sequence, receipt time, and raw-event position. This envelope proves only that the Runner received the claim. Independently generated heartbeats report process liveness, elapsed time, last raw event time, and last Progress Claim time without asserting semantic progress.

## Permission enforcement

The Runner generates a per-invocation settings file that installs command Hooks for `PermissionRequest` and `PermissionDenied`. It does not modify user, project, or global Claude settings.

- `PermissionRequest` records the exact tool name and input, returns a denial with `interrupt: true`, and stops the current Claude run.
- `PermissionDenied` records the effective denial and returns `continue: false` so Claude cannot continue and later claim success.
- Hook or Reporter startup failure is a Claude Backend Failure.

The Runner returns `PERMISSION_REQUIRED` to Codex. The existing Permission Broker decides whether to add a narrow rule and resume the same Segment Session, ask the user, or deny the request. Managed denials always win. The Runner never approves a request or enumerates every possible Claude tool.

Claude Code documents the relevant Hook controls at <https://code.claude.com/docs/en/hooks> and deny-first permission precedence at <https://code.claude.com/docs/en/permissions>.

## Timeout observations and control

The Runner observes three independent clocks:

- no complete stream event while no tool call is outstanding;
- elapsed time between a structural `tool_use` identifier and its matching result;
- total Work Unit wall-clock duration.

Crossing a configured threshold emits `TIMEOUT_SUSPECTED` with only Runtime Facts. It never automatically terminates Claude. Codex inspects raw evidence and possible external effects, then explicitly extends, interrupts, or terminates the process group. After the first model-idle suspicion, Codex may safely interrupt and resume the same Session once without involving the user when no external side effect is possible. Tool and Work Unit suspicions require direct Codex judgment.

## Failure and recovery

The Runner exposes commands to initialize, run, wait, inspect, approve a permission rule, extend an observation threshold, interrupt, terminate, record verification, finish, and clean up a Work Unit. State and process identity allow Codex to inspect or regain control after its own task or application restarts; there is no cross-project daemon.

Runner crashes, corrupt state, unsafe process identity, missing or incompatible Python or Claude CLI, authentication, quota, service failure, Session creation or resume failure, Reporter or Hook failure, and invalid stream protocol are Claude Backend Failures. The workflow preserves Adapter State and never silently falls back to Codex implementation. The user may repair and resume Claude, explicitly change and reapprove the executor contract, or exit.

## Packaging

The canonical Python-standard-library Runner lives at `shared/claude-runner/`. Release tooling hard-copies it into both Skill packages under `scripts/claude-runner/`, alongside the existing hard-copied permission broker. Validation fails when either packaged runtime differs from the canonical tree. Each installed Skill therefore remains independently runnable without symlinks, the repository checkout, the other Skill, a package manager, or a global service.

## Verification strategy

Deterministic tests use a fake Claude executable and scripted stream fixtures. They cover lossless byte capture, unknown events, Reporter MCP negotiation and validation, Progress Claim envelopes, Hook stop responses, permission resume, state locking and transition validation, process identity and recovery, timeout suspicions without automatic termination, exact cleanup scope, Session boundaries, result-schema validation, and hard-copy consistency.

After deterministic tests pass, run one small complete Superpowers regression and one equivalent Matt regression through real Claude Code. These live checks require explicit cost and authorization confirmation and must preserve each framework's native Review and completion behavior.
