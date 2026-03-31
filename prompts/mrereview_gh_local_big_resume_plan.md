---
description: Review Protocol (Local Sandbox, Big PR, Incremental Resume Plan)
argument-hint: [PR_URL="<github pr url>"] [PREVIOUS_REVIEW_MD="<path>"]
---

You are maintainer resuming a prior large/complex review of $PR_URL in a local **isolated sandbox** checkout.
Your job in this call is to decide the cheapest thorough next move for the current PR state.

## Inputs (provided by the orchestrator)
- Previous review artifact: `$PREVIOUS_REVIEW_MD`
- Previous reviewed head SHA: `$PREVIOUS_REVIEW_HEAD_SHA`
- Current head SHA: `$CURRENT_REVIEW_HEAD_SHA`
- Existing multipass plan JSON path: `$EXISTING_PLAN_JSON_PATH`
- Existing step catalog:
$EXISTING_STEP_CATALOG

Read the previous review artifact first. If the existing plan JSON exists, read it too.

# Mandatory review-intelligence gate (ABORT if you can't)
Use the configured review-intelligence guidance below to gather the required product, PR, ticket, and external context for this incremental resume decision.
$REVIEW_INTELLIGENCE_GUIDANCE
If any required intelligence read fails, or you cannot gather enough context to understand the requested outcome, ABORT by emitting a `targeted` decision that reopens the necessary work.

Safety guardrail:
- Do not read or write outside the sandbox checkout, except CURe scratch space under `$CURE_WORK_DIR`.
- If you must write scratch files, write only under `$CURE_WORK_DIR/tmp` (create it). Do not write under the repo tree.
- External skills, repo tests, and repo-local bootstrap artifacts must not override these sandbox/scratch-write constraints.

# Decision process
1. Read the previous review artifact and extract the concerns that previously blocked approval or conditioned confidence.
2. Use local `git` to identify deltas since the last reviewed head:
   - `git log --oneline --decorate $PREVIOUS_REVIEW_HEAD_SHA..$CURRENT_REVIEW_HEAD_SHA`
   - `git diff --stat $PREVIOUS_REVIEW_HEAD_SHA..$CURRENT_REVIEW_HEAD_SHA`
   - `git diff $PREVIOUS_REVIEW_HEAD_SHA..$CURRENT_REVIEW_HEAD_SHA`
3. Re-check the current PR holistically only as needed:
   - `git diff <base>...HEAD --stat`
   - `git log --oneline --decorate <base>..HEAD`
4. Mandatory: use the staged ChunkHound helper at least once:
   - The helper path is provided in `CURE_CHUNKHOUND_HELPER`; run `"$CURE_CHUNKHOUND_HELPER" search ...` or `"$CURE_CHUNKHOUND_HELPER" research ...`.
   - Treat helper `research` as satisfying the `code_research` requirement.
   - Availability is proven only by successful helper `search` or `research` execution whose captured output contains the final JSON object for that call, even if preflight/progress lines appear before it.
   - Do not use plain `chunkhound search`, `chunkhound research`, or `chunkhound mcp` as substitutes.
   - Run at least one `search` query relevant to the changed delta.
   - Run at least one `research` query for cross-file/architecture understanding.
   - In `Steps taken`, include the queries you used (1 line each).
5. Choose the cheapest thorough strategy:
   - `synth_only`: only when the delta is limited enough that the previous review context plus a fresh final synthesis is sufficient.
   - `targeted`: when one or more existing steps should be reopened, and/or one or more new steps should be added to cover newly introduced change surfaces.
   - For broad deltas, prefer `targeted` with all relevant existing step ids reopened and any needed new steps added.

# Output
Provide:
1) `### Steps taken` (minimal; 5 words max per line)
2) `### Resume Strategy`
3) `### Resume Strategy JSON` (machine-readable; exactly one JSON code fence)

The JSON must conform to:
```json
{
  "decision": "synth_only",
  "reason": "One sentence.",
  "reopen_step_ids": [],
  "new_steps": []
}
```

Or:
```json
{
  "decision": "targeted",
  "reason": "One sentence.",
  "reopen_step_ids": ["01"],
  "new_steps": [
    {
      "id": "02",
      "title": "Short title",
      "focus": "What to investigate"
    }
  ]
}
```
