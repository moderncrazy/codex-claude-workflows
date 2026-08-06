# Codex-Claude Workflow Orchestration

This context describes how Codex-owned development workflows delegate implementation to Claude Code without surrendering their native planning, review, verification, or completion semantics.

## Language

**Native Workflow**:
The unmodified Superpowers or Matt process that owns requirements, planning, task state, review, verification, and completion.
_Avoid_: Host workflow, upstream workflow

**Work Unit**:
One native Superpowers Task, Matt Ticket, or Matt implicit task whose implementation is assigned through one executor contract.
_Avoid_: Job, runner task, checkpoint

**Executor Contract**:
The approved assignment of a Work Unit to Codex or Claude Code together with its capability model and routing reason.
_Avoid_: Agent profile, model mapping

**Capability Model**:
The `sonnet` or `opus` capability requested from Claude Code without asserting which provider or concrete backend model serves it.
_Avoid_: Provider model, model ID

**Execution Segment**:
An ephemeral, sequential slice of one Claude-owned Work Unit used to bound implementation context without changing native task boundaries or lifecycle state.
_Avoid_: Checkpoint, subtask, Ticket

**Repair Segment**:
An Execution Segment created by Codex to address accepted native Review findings that span prior segments or no longer fit safely in an earlier Session.
_Avoid_: Extra review round, residual task

**Progress Claim**:
A verbatim, structured statement that Claude Code actively reports about its current activity, next action, concern, or claimed result. It is informative but unverified.
_Avoid_: Progress fact, verified status

**Runtime Fact**:
An observation the Runner can establish directly, such as process liveness, elapsed time, receipt time, event position, or an unmatched tool-call identifier.
_Avoid_: Progress Claim

**Execution Evidence**:
An independently inspectable artifact such as an original stream event, repository change, test result, or commit identifier used by Codex to verify a claim.
_Avoid_: Self-check, completion claim

**Native State**:
The authoritative Task, Ticket, Review, verification, and completion state maintained by the Native Workflow.
_Avoid_: Runner state

The Native Workflow decides what happens next. Adapter State and Execution Evidence may describe or support a native transition; they never authorize or block it.

**Adapter State**:
The temporary execution state needed to supervise Claude Code for one Work Unit. It never replaces Native State.
_Avoid_: Ticket state, workflow ledger

**Permission Broker**:
The Codex-owned decision boundary that classifies a stopped Claude Code permission request as automatically approvable, user-gated, or denied.
_Avoid_: Runner approval, Claude approval

**Claude Backend Failure**:
A failure of the Runner, Claude Code CLI, injected reporting or permission infrastructure, authentication, service, quota, Session, or event protocol that prevents the approved Claude executor from continuing safely.
_Avoid_: Implementation fallback
