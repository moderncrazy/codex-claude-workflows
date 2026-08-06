# Codex permission broker

Classify each exact `PERMISSION_REQUIRED` request against the approved work unit.

Continue without user interaction and resume the same Session automatically only when every check passes:

1. The request is necessary for the approved work unit.
2. Its data scope stays inside the repository/worktree or an already approved external data scope.
3. Its effect is read-only.
4. Its permission can be expressed as one exact tool or narrow command family.

Qualifying requests include:

- Claude built-ins `Read`, `Glob`, and `Grep` within the repository/worktree;
- a read-only CLI inspection such as a scoped `grep`, `rg`, or `codegraph explore` command;
- a read-only MCP tool whose exact operation and data scope are already approved;
- version/help probes for an approved executable.

For an unfamiliar CLI or MCP tool, inspect its help, configuration, or authoritative description until its data scope and side effects are known. Approve the exact MCP tool or narrow action family. Re-pass the complete narrow allowlist on resume.

Ask the user when the request reaches outside the repository/worktree or approved external data scope, performs an external write, requires installation, accesses new credentials or secrets, changes remote state, is destructive, broadens the work unit, or Codex cannot classify its effects. A managed denial ends permission handling.

If the requested tool is unavailable to Claude Code, permission expansion cannot fix it. Codex may perform an equivalent read-only inspection and return only the result to the same Claude Session. Otherwise report a tool-availability backend failure. Codex implementation still requires an approved executor-contract change.
