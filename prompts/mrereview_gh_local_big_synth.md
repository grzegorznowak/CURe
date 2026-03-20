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

$REVIEW_INTELLIGENCE_GUIDANCE

Safety guardrail:
- Do not read or write outside the sandbox checkout, except CURe scratch space under `$CURE_WORK_DIR`.
- If you must write scratch files, write only under `$CURE_WORK_DIR/tmp` (create it). Do not write under the repo tree.

# Mandatory: ChunkHound MCP tools
If you still need to confirm anything before deciding, use ChunkHound MCP tools (`search` / `code_research`) rather than guessing.
Tool names can appear as `chunkhound.search` / `chunkhound.code_research` (equivalent to `search` / `code_research`).
Do not use `list_mcp_resources` or `list_mcp_resource_templates` as the ChunkHound availability check.
ChunkHound is a tools-first MCP server, so empty resource/template results are expected and are not an outage signal.
Availability is proven only by a successful `search` or `code_research` tool call.
If ChunkHound MCP tools are unavailable or fail, ABORT and set both `**Verdict**` lines to `REJECT`.

# Assessment Rules
- Produce two independent assessments:
  - `Business / Product Assessment`: requested behavior, acceptance criteria, feature completeness, user-visible correctness, stakeholder value.
  - `Technical Assessment`: architecture, maintainability, tests, performance, security, and newly introduced debt.
- The two verdicts may disagree.
- Every pushback item must be classified into either `In Scope Issues` or `Out of Scope Issues`.
- For `Business / Product Assessment`, `In Scope` means the currently requested outcome as established by the ticket or product context first, then the PR description, plus clarifying discussion when present.
- For `Technical Assessment`, `In Scope` means code paths, behavior, and implementation responsibilities the PR directly changes or owns.
- `Out of Scope` means adjacent debt, follow-on work, or auxiliary improvements outside that section's scope basis.
- The same issue may be `In Scope` for business/product and `Out of Scope` for technical, or vice versa.
- Out-of-scope issues may still downgrade a verdict when materially important.
- Use `- None.` when a scope bucket is empty.
- Every non-empty bullet under `Strengths`, `In Scope Issues`, `Out of Scope Issues`, and `Reusability` must end with a `Sources:` suffix containing one or more real `review.step-XX.md:line` citations.

# Output Format
Output ONLY the final review (no plan, no step outputs appended):
```markdown
### Steps taken
- [1 line per major action]

**Summary**: [One sentence summary; mention the relevant ticket key(s) + business value alignment]

## Business / Product Assessment
**Verdict**: [APPROVE/REQUEST CHANGES/REJECT]

### Strengths
- ... Sources: `review.step-01.md:12`

### In Scope Issues
- ... Sources: `review.step-02.md:8`

### Out of Scope Issues
- ... Sources: `review.step-03.md:6`

## Technical Assessment
**Verdict**: [APPROVE/REQUEST CHANGES/REJECT]

### Strengths
- ...

### In Scope Issues
- ...

### Out of Scope Issues
- ...

### Reusability
- ... Sources: `review.step-01.md:18`
####
```
