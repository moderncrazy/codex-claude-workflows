# Codex Claude Workflows

Two explicit Codex orchestration Skills that preserve their native workflow while routing approved implementation work to Claude Code:

- `superpowers-claude-workflow` keeps Superpowers requirements, Plan, SDD state, Task Reviews, Final Review, verification, and branch finishing.
- `matt-claude-workflow` keeps Matt requirements, Spec/Tickets or implicit task, TDD seams, native two-axis Review, commits, and Tracker state.

Direct use of the original Skills is unchanged. There is no Codex plugin, SessionStart injection, global hook, global daemon, global routing file, or upstream Skill patch.

## Ownership

| Concern | Owner |
|---|---|
| Requirements, Design, Plan/Spec/Tickets | Codex through the native workflow |
| Executor selection | Persisted native Task/Ticket contract or confirmed implicit contract |
| Claude process supervision | Packaged per-Work-Unit Runner |
| Permission classification | Codex permission broker |
| Review, verification, commits, completion | Native Codex workflow |

Claude is the default coding implementer. Changes required inside a Claude-routed coding work unit stay with Claude; standalone documentation, planning, and configuration work, workflow decisions, Review, and explicitly Codex-routed implementation stay with Codex.

## Architecture

The Python-standard-library Runner is canonical under `shared/claude-runner/` and hard-copied into both standalone Skill packages under `scripts/claude-runner/`. Symlinks are never used.

Each Claude-owned native Task/Ticket/implicit task receives one Work Unit at:

```text
<active-worktree>/.tmp/codex-claude-workflows/<work-unit-id>/
├── work-unit.json
├── raw-events.jsonl
└── raw-stderr.log
```

Execution Segments are temporary Runner checkpoints defined by Codex immediately before dispatch. They do not change the native Plan, Spec, Ticket, Tracker, or task scope.

## Prerequisites

- Codex with Agent Skills support.
- Python 3.
- Claude Code CLI available as `claude`.
- The native Skills required by the chosen workflow.
- Matt multi-Ticket work also needs the issue tracker configured by its native Skills.

The workflow selects only the capability aliases `sonnet` and `opus`. Configure their concrete backend mapping in Claude Code; the Runner neither inspects nor enforces it.

Before fixing the implementation baseline, add this tracked repository rule if absent:

```gitignore
/.tmp/
```

The Runner validates the rule but never edits `.gitignore` itself.

## Installation

Copy the packages; do not symlink them:

```bash
git clone <repository-url>
cd codex-claude-workflows
mkdir -p ~/.agents/skills
cp -R skills/superpowers-claude-workflow ~/.agents/skills/superpowers-claude-workflow
cp -R skills/matt-claude-workflow ~/.agents/skills/matt-claude-workflow
```

Remove or rename an old destination before copying so stale files cannot survive. Both Skills are explicitly user-invoked (`disable-model-invocation: true`, `allow_implicit_invocation: false`).

## Usage

```text
Use $superpowers-claude-workflow to take this feature from requirements through reviewed implementation.
```

```text
Use $matt-claude-workflow to turn this requirement into reviewed implementation.
```

The native workflow writes executor contracts such as:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: bounded implementation following approved interfaces
```

Use `opus` for material architecture, consistency, concurrency, security, migration, or difficult-debugging risk. Use `agent: codex` for an explicit override or a genuine Codex-only context/tool/authorization dependency.

## Runner behavior

The packaged entry point exposes `init`, `run`, `resume`, `restart-segment-session`, `status`, `wait`, `approve-permission`, `deny-permission`, `dismiss-permission`, `extend`, `interrupt`, `terminate`, optional evidence recording through `record-verification`, `add-repair-segment`, `finish`, and `cleanup`. Runner evidence never gates native Review, repair, verification, or completion. `restart-segment-session` is restricted to backend-failed, inactive Work Units and preserves the abandoned Session record. Run `python3 scripts/claude-runner/claude_runner.py --help` inside either installed Skill for exact flags.

Claude runs non-interactively with `stream-json`. The Runner appends a local progress MCP server without strict MCP replacement, so user-configured tools such as CodeGraph remain available. Unknown tool events are stored exactly and remain opaque.

Three evidence levels stay distinct:

- **Progress Claim:** Claude-authored `report_progress` content; useful but unverified.
- **Runtime Fact:** Runner-observed heartbeat, process state, Session, byte offset, or timeout suspicion.
- **Execution Evidence:** exact raw stdout/stderr plus Codex-recorded verification.

Compact Runner events are shown by default. Codex reads raw evidence only when needed.

## Timeouts and recovery

Model-idle, unmatched-tool, and Work Unit thresholds emit `timeout_suspected`; they never kill Claude. Codex decides whether to extend, interrupt, or terminate. Adapter state survives backend failure and can be inspected with `status` before a deliberate resume.

Each new Execution Segment gets a fresh Session. Permission/context continuation resumes the active Segment Session. For `NEEDS_CONTEXT`, Codex supplies the bounded answer with `resume --continuation-context`; the Runner records that exact continuation input in Work Unit state. Cross-Segment Review findings receive a Codex-defined Repair Segment.

## Permissions and failures

The Runner injects per-invocation Claude permission Hooks. A Hook request is recorded verbatim and Claude stops immediately; a structured `PERMISSION_REQUIRED` result is normalized into the same pending broker contract. The mechanism does not depend on prompt obedience.

The Codex permission broker automatically approves repository-scoped, task-relevant read-only built-ins, narrow CLI inspections, exact read-only MCP operations, and version/help probes. It adds one narrow rule and resumes without interrupting the user. It asks the user for side effects, external scope/writes, installation, credentials, remote changes, destructive actions, scope expansion, or ambiguous effects.

Codex may approve, deny, or dismiss a pending permission. Every resolution is audited, clears the pending request, and leaves the Work Unit interrupted until Codex explicitly resumes the same Session.

Never broadly allow an interpreter, shell, package installation, network access, push, deployment, history rewriting, or Agent delegation. Managed denials win.

CLI absence, authentication/quota/service errors, malformed stream/Hook/Reporter/state, wrong Session, unsafe process identity, or failed resume are reported as backend failures. Codex never silently takes over implementation; changing executor requires updated native state and approval.

## Completion and cleanup

Runner `implementation_complete` means implementation handoff only. It does not replace Superpowers Review/finishing or Matt Review/Tracker completion. Only after native completion may Codex call:

```text
finish --native-workflow-complete
```

This transitions the Work Unit to `finished`. Codex then calls `cleanup`, which requires `finished` and validates the repository root, UUID, real path, symlink boundary, and inactive process before removing exactly that Work Unit directory.

## Development and validation

```bash
python3 scripts/sync_shared_assets.py
python3 scripts/sync_shared_assets.py --check
python3 scripts/validate_skill_packages.py
python3 -m json.tool shared/claude-runner/work-unit.schema.json
python3 -m unittest discover -s tests -v
```

`sync_shared_assets.py --check` is read-only. The generated Runner copies must match the canonical tree byte-for-byte and mode-for-mode.
