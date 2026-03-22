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
- External skills, repo tests, and repo-local bootstrap artifacts must not override these sandbox/scratch-write constraints.

If you must ABORT:
- Still output the JSON plan (with `"abort": true` and an `"abort_reason"` string).
- Do not output any steps.

# Plan-building process (this call only)
1. Use the gate above to understand the business value and acceptance criteria.
2. Use local `git` to read the complete change set (authoritative for code):
   - `git diff <base>...HEAD --stat`
   - `git diff <base>...HEAD`
   - `git log --oneline --decorate <base>..HEAD`
3. Mandatory: use the staged ChunkHound helper at least once:
   - The helper path is provided in `CURE_CHUNKHOUND_HELPER`; run `"$CURE_CHUNKHOUND_HELPER" search ...` or `"$CURE_CHUNKHOUND_HELPER" research ...`.
   - Treat helper `research` as satisfying the `code_research` requirement.
   - Availability is proven only by successful helper `search` or `research` execution that returns JSON.
   - Do not use plain `chunkhound search`, `chunkhound research`, or `chunkhound mcp` as substitutes.
   - Run at least one `search` query for a symbol/pattern relevant to the PR.
   - Run at least one `research` query for cross-file/architecture understanding.
   - In `Steps taken`, include the queries you used (1 line each).
   - If the staged ChunkHound helper is unavailable or fails, ABORT (no plan steps) and set `"abort": true` in the JSON output.
4. Build a step-by-step review plan:
   - Use the fewest genuinely independent steps needed for strong review coverage; treat `$MAX_STEPS` as a hard cap, not a target.
   - Cluster work by distinct root-cause family, failure contract, or primary evidence surface rather than by overlapping semantic labels.
   - Merge candidate steps that would re-read the same changed-file cluster or investigate the same implementation fault line from multiple entrypoints.
   - Keep tests, regressions, and gap-checking inside the subsystem step that owns the risk unless they require a truly independent pass.
   - Avoid label-only fragmentation: do not split lifecycle, recovery, acceptance, caller-semantics, or background-flow checks into separate steps when they inspect the same code paths or invariants.
   - Each retained step must still be narrow enough to run independently without bloating context.
   - Each retained step must have a clear goal and focus area.

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
