---
description: Review Protocol (Local Sandbox, Big PR, Multipass Plan)
argument-hint: [PR_URL="<github pr url>"] [AGENT_DESC="<agent description>"]
---

You are maintainer reviewing $PR_URL in a local **isolated sandbox** checkout.
Your job in this call is to produce a **multipass review plan** for this PR that can be executed in multiple follow-up calls.

# Mandatory review-intelligence gate (ABORT if you can't)
Use the configured review-intelligence guidance below to gather the required product, PR, ticket, and external context for this review plan.
$REVIEW_INTELLIGENCE_GUIDANCE
If any required intelligence read fails, or you cannot gather enough context to understand the requested outcome, ABORT (do not continue).

Safety guardrail:
- Do not read or write outside the sandbox checkout, except CURe scratch space under `$CURE_WORK_DIR`.
- If you must write scratch files, write only under `$CURE_WORK_DIR/tmp` (create it). Do not write under the repo tree.

If you must ABORT:
- Still output the JSON plan (with `"abort": true` and an `"abort_reason"` string).
- Do not output any steps.

# Plan-building process (this call only)
1. Use the gate above to understand the business value and acceptance criteria.
2. Use local `git` to read the complete change set (authoritative for code):
   - `git diff <base>...HEAD --stat`
   - `git diff <base>...HEAD`
   - `git log --oneline --decorate <base>..HEAD`
3. Mandatory: use ChunkHound MCP tools at least once:
   - Tool names can appear as `chunkhound.search` / `chunkhound.code_research` (equivalent to `search` / `code_research`).
   - Do not use `list_mcp_resources` or `list_mcp_resource_templates` as the ChunkHound availability check.
   - ChunkHound is a tools-first MCP server, so empty resource/template results are expected and are not an outage signal.
   - Availability is proven only by a successful `search` or `code_research` tool call.
   - Run at least one `search` query for a symbol/pattern relevant to the PR.
   - Run at least one `code_research` query for cross-file/architecture understanding.
   - In `Steps taken`, include the queries you used (1 line each).
   - If ChunkHound MCP tools are unavailable or fail, ABORT (no plan steps) and set `"abort": true` in the JSON output.
4. Build a step-by-step review plan:
   - The plan may contain any number of steps, but MUST NOT exceed `$MAX_STEPS` steps.
   - Each step must be narrow enough to run independently without bloating context.
   - Each step must have a clear goal and focus area.

# Output
Provide:
1) `### Steps taken` (minimal; 5 words max per line)
2) `### Plan` (human-readable bullets)
3) `### Plan JSON` (machine-readable; exactly one JSON code fence)

The JSON must conform to:
```json
{
  "abort": false,
  "abort_reason": null,
  "ticket_keys": ["ABC-123"],
  "steps": [
    {
      "id": "01",
      "title": "Short title",
      "focus": "What to investigate",
      "suggested_ch_search": ["query 1"],
      "suggested_ch_code_research": ["query 1"]
    }
  ]
}
```
