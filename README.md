# Codex Claude Workflows

Two explicit Codex orchestration Skills that keep native workflow management in Codex while routing approved implementation work to Claude Code.

本项目包含两套互相独立的薄编排 Skill：

- `superpowers-claude-workflow`：保留 Superpowers 的需求分析、Plan、SDD、Task Review、Final Review 和分支收尾流程。
- `matt-claude-workflow`：保留 Matt Pocock Skills 的需求澄清、Spec、Tickets、TDD seam、双 Reviewer、提交和 Tracker 流程。

它们只替换原生工作流中的 Implementer。不会修改上游 Skill，不使用 Hook、Plugin、SessionStart 注入或全局路由状态。

## Responsibilities

| Responsibility | Owner |
|---|---|
| Requirements and domain decisions | Codex + user |
| Design, Plan, Spec and Tickets | Codex through native Skills |
| Implementation | Claude Code by default; Codex when explicitly routed |
| Test-seam decisions | Codex + user |
| Independent code review | Native Codex reviewers |
| Verification, commits and workflow completion | Native workflow |

Directly invoking the original Superpowers or Matt Skills remains unchanged. Claude routing activates only when one of the two Skills in this repository is explicitly invoked.

## Repository layout

```text
skills/
├── superpowers-claude-workflow/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   └── references/
│       ├── executor-contract.md
│       ├── claude-execution-protocol.md
│       └── claude-result.schema.json
└── matt-claude-workflow/
    ├── SKILL.md
    ├── agents/openai.yaml
    └── references/
        ├── executor-contract.md
        ├── claude-execution-protocol.md
        └── claude-result.schema.json
```

## Prerequisites

- Codex with Agent Skills support.
- Claude Code CLI available as `claude`.
- For `superpowers-claude-workflow`: the native Superpowers Skills used by the workflow.
- For `matt-claude-workflow`: `grill-with-docs` or `grill-me`, `to-spec`, `to-tickets`, `implement`, `tdd`, and `code-review` as required by the selected path.
- Matt multi-Ticket work also requires the issue tracker expected by the native Matt Skills.

The repository selects only the capability aliases `sonnet` and `opus`. Configure the actual Claude Code model provider, gateway, and model mapping in the user's Claude Code environment.

## Installation

Codex and Claude Code recognize personal Skills under `~/.agents/skills/`.

Clone this repository and copy the Skills into the personal Skills directory:

```bash
git clone <repository-url>
cd codex-claude-workflows
mkdir -p ~/.agents/skills
cp -R skills/superpowers-claude-workflow ~/.agents/skills/superpowers-claude-workflow
cp -R skills/matt-claude-workflow ~/.agents/skills/matt-claude-workflow
```

Remove or rename an existing destination before copying, so an old installation cannot leave stale files behind. The Skills intentionally set `allow_implicit_invocation: false`.

## Usage

### Superpowers

```text
Use $superpowers-claude-workflow to take this feature from requirements through reviewed implementation.
```

The workflow:

1. uses native brainstorming and writing-plans;
2. writes an executor contract for every Plan Task;
3. accepts only SDD-eligible Plans;
4. uses native SDD state and Codex Review;
5. keeps native Final Review and branch finishing.

### Matt

```text
Use $matt-claude-workflow to turn this requirement into reviewed implementation.
```

Single-session work uses an in-conversation implicit task without creating a Ticket. Multi-session work uses native `to-spec` and `to-tickets`; each Ticket receives an independent Claude Code Session and preserves native blocking relationships.

## Executor contract

Claude implementation:

```yaml
executor:
  agent: claude-code
  model: sonnet
  reason: bounded implementation following approved interfaces
```

Codex implementation:

```yaml
executor:
  agent: codex
  reason: requires an authorization available only in the current Codex session
```

Rules:

- `agent` is `claude-code` or `codex`.
- `model` is required only for Claude Code and is `sonnet` or `opus`.
- `sonnet` is the default capability tier.
- Use `opus` for material architecture, security, concurrency, migration, consistency, or debugging risk.
- User instructions and persisted Plan/Ticket edits have highest priority.

## Claude Code execution

Claude runs in non-interactive mode with a structured JSON result:

```text
claude -p
  --session-id <uuid>
  --model <sonnet|opus>
  --permission-mode acceptEdits
  --output-format json
  --json-schema <schema-json>
  <task-prompt>
```

Supported result states:

- `DONE`
- `DONE_WITH_CONCERNS`
- `NEEDS_CONTEXT`
- `BLOCKED`
- `PERMISSION_REQUIRED`

Claude's `DONE` result never replaces native independent Review.

## Permissions and failures

- Default to `acceptEdits`.
- Never use `bypassPermissions` or `--dangerously-skip-permissions`.
- Request additional tools with exact scope and reason.
- Resume the same Session after user-approved permissions.
- Respect managed denials.
- Report CLI, authentication, quota, service, timeout, JSON/Schema, permission-protocol, native-artifact, and Session failures.
- Never silently fall back from Claude Code to Codex.

An executor change requires explicit user direction, an updated contract, revalidation, and renewed approval.

## Validation

Validate each Skill with Codex's Skill validator:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/superpowers-claude-workflow
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/matt-claude-workflow
python3 -m json.tool skills/superpowers-claude-workflow/references/claude-result.schema.json
python3 -m json.tool skills/matt-claude-workflow/references/claude-result.schema.json
```

The two Skills are packaged separately on purpose. Framework-specific state, Review, repair, and completion semantics must not be combined into a shared runtime orchestrator.
