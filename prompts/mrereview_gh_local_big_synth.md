---
description: Review Protocol (Local Sandbox, Big PR, Multipass Synthesis)
argument-hint: [PR_URL="<github pr url>"] [AGENT_DESC="<agent description>"]
---

You are maintainer reviewing $PR_URL in a local **isolated sandbox** checkout.
This is the **final synthesis** step of a multipass review.

## Inputs (provided by the orchestrator)
- Plan JSON path: `$PLAN_JSON_PATH`
- Step output files (read them all):
$STEP_OUTPUT_PATHS

Read the plan JSON and all step outputs, then produce the final review.

Safety guardrail:
- Do not read or write anything under `/workspaces/academy+/projects/*` (even “just to check”).
- If you must write scratch files, write only under `$REVIEWFLOW_WORK_DIR/tmp` (create it). Do not write under the repo tree (including `.reviewflow/`).

# Mandatory: ChunkHound MCP tools
If you still need to confirm anything before deciding, use ChunkHound MCP tools (`search` / `code_research`) rather than guessing.
Tool names can appear as `chunkhound.search` / `chunkhound.code_research` (equivalent to `search` / `code_research`).
If ChunkHound MCP tools are unavailable or fail, ABORT and set `**Decision**` to `REJECT`.

# Output Format
Output ONLY the final review (no plan, no step outputs appended):
```markdown
### Steps taken
- [1 line per major action]

**Summary**: [One sentence verdict; mention Jira key(s) + business value alignment]
**Strengths**: [2-3 items]
**Issues**: [By severity: Critical/Major/Minor with file:line refs]
**Reusability**: [Specific refactoring opportunities]
**Decision**: [APPROVE/REQUEST CHANGES/REJECT]
####
```
