# Supervise Claude Code with a per-Work-Unit Runner

Use a deterministic, per-Work-Unit Runner between both orchestration Skills and Claude Code. The Runner owns temporary Adapter State, lossless event capture, active Progress Claim transport, permission interruption, liveness observation, and process recovery; Codex retains every semantic decision, while the unmodified Superpowers or Matt workflow retains Native State, Review, verification, and completion. This avoids global Codex hooks, a permanent daemon, changes to upstream Skills, and prompt-dependent permission enforcement, while accepting a small Python runtime that is hard-copied into each independently installable Skill package.

## Considered Options

- Modify Superpowers and Matt directly: rejected because upstream upgrades would conflict and direct calls would no longer preserve native behavior.
- Add global Codex hooks or a plugin: rejected because routing would affect unrelated work and could unintentionally disable native Codex implementation.
- Parse and summarize every Claude tool event: rejected because tools are open-ended and semantic filtering could mislead Codex.
- Keep prompt-only orchestration: rejected because it cannot reliably enforce permission stops, expose long-running progress, or recover deterministic state.

## Consequences

- The two public Skills remain explicit and independent, but share one source-controlled Runner implementation through validated hard copies.
- Claude reports are unverified Progress Claims; Codex uses Runtime Facts and Execution Evidence before accepting tests, commits, or completion.
- Temporary state lives below the active working tree's ignored `.tmp` directory and is removed only after the Native Workflow finishes.
