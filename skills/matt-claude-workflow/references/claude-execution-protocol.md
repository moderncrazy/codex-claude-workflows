# Claude Runner execution protocol

## Preconditions

Run the packaged `scripts/claude-runner/claude_runner.py` from the trusted Matt repository/worktree. Require Python 3, Claude Code, an existing tracked `/.tmp/` ignore rule, and the native Review fixed point. `sonnet` and `opus` are capability aliases; do not inspect the provider model.

One Ticket or implicit task owns one temporary Work Unit. Only `work-unit.json`, `raw-events.jsonl`, and `raw-stderr.log` persist under `.tmp/codex-claude-workflows/<uuid>/`. Tracker and conversation state remain authoritative.

## Dispatch

Immediately before implementation, Codex defines Execution Segments within the approved native work unit. Segments are adapter state, never Spec, Ticket, or Tracker data. Use one Segment for small work; use sequential checkpoints for a large cohesive work unit. Each new Segment gets a fresh Session; resume only the active Segment Session.

Initialize with the native brief, capability, fixed point, result Schema, narrow allowed tools, and Segment JSON, then call `run`. Use the bundled entry point's `--help` for exact arguments. The Runner supplies print mode, Session selection, `acceptEdits`, `stream-json`, Reporter MCP, permission Hooks, and Schema. It preserves existing Claude MCP configuration, including CodeGraph.

Pass the bundled result Schema verbatim. Do not add provider IDs or fallback models.

## Initial command permissions

Derive the smallest task-scoped command-family allowlist from confirmed Red/Green tests, full suite, lint, typecheck, formatter, and local inspection. Native Review and the post-Review commit remain Codex-owned workflow actions outside the Claude Runner.

- `.venv/bin/pytest ...` → `Bash(.venv/bin/pytest *)`, including version or help probes.
- `python -m pytest ...` → `Bash(python -m pytest *)`, never a Python wildcard.
- Include `Bash(git status *)` and `Bash(git diff *)`.

Pass every family through Runner `init`; the Runner emits repeated `--allowedTools`. Never pre-approve commit, package installation, network commands, push, merge, deployment, history rewriting (amend/rebase/reset/tag), a shell/interpreter wildcard, bare `Bash`, or Agent delegation.

## Progress and time

Claude actively reports unverified Progress Claims through `codex_claude_runner.report_progress`. Runner heartbeats and stream offsets are Runtime Facts. Raw bytes are Execution Evidence for Codex on demand; unknown tool events remain opaque.

Model-idle, tool-idle, and Work Unit thresholds produce `timeout_suspected` only. Codex explicitly extends, interrupts, or terminates after inspecting evidence. The Runner never kills Claude because a timer fired.

## Permissions

Injected `PermissionRequest` and `PermissionDenied` Hooks stop Claude outside the prompt and record the exact request. A structured `PERMISSION_REQUIRED` result enters the same pending broker contract. Apply [claude-permission-broker.md](claude-permission-broker.md), call `approve-permission` with one narrow rule, then `resume`. For `NEEDS_CONTEXT`, answer the exact request with bounded `resume --continuation-context`; never edit adapter state directly. Hook/Reporter/state failure is a backend failure.

`--allowedTools` reduces prompts; it does not remove existing MCP tools. Managed denials still win.

## Results, Review, and cleanup

Validate Session and structured result, then inspect the artifacts required by the Native Workflow. `record-verification` stores optional adapter evidence; the Native Workflow decides when verification is required. `finish` marks implementation handoff only: Runner `implementation_complete` is not native completion.

When the Native Workflow routes a finding back to implementation, resume its owning Segment Session. For cross-Segment findings, add a Codex-defined Repair Segment. The adapter does not decide Review disposition.

Malformed streams, wrong Session, missing result, failed resume, CLI/authentication/quota/service failure, or unsafe process identity become `backend_failure`. Preserve state and report it to the user. When evidence proves Claude rejected a Session before creating it, use `restart-segment-session` with the exact Segment and reason, then `run`; the abandoned Session remains recorded. Do not silently implement with Codex.

After accepted native Review, verification, commit evidence, and Tracker/implicit-task completion, call `cleanup --native-workflow-complete`. Cleanup removes exactly the owned UUID directory.
