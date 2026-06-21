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
- Do not execute the PR's test suite (`pytest`, `npm test`, `go test`, `cargo test`, etc.), build scripts, linters, formatters, or any other repo command that runs user code. Review test *coverage* and test *code quality* statically by reading the test files. For pass/fail status, rely on `gh pr checks $PR_URL` (and `gh run view` for details) — do not re-run the suite locally.

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
   - The helper path is provided in `CURE_CHUNKHOUND_HELPER`; run `"$CURE_CHUNKHOUND_HELPER" search ...` for at least one symbol/pattern relevant to the PR.
   - Initial planning proof requires successful helper `search` execution whose captured output contains the final structured output for that call, even if preflight/progress lines appear before it. For `search`, this may be a JSON object with a `results` list or a markdown/text block.
   - Helper `research` is optional/guidance-only for this plan template; if you use `"$CURE_CHUNKHOUND_HELPER" research ...`, CURe records it as `code_research` evidence, but it is not required to satisfy the plan proof gate.
   - `research` typically takes 2–5 minutes per call on non-trivial repos (chunk retrieval plus an LLM synthesis step); extreme valid calls may run until the configured helper timeout. The helper streams `cure-chunkhound: tools/call waiting (Ns elapsed)` heartbeat lines while it works — these are **normal progress, not a hang**. Do not cancel, retry, or re-issue a narrower query solely because it has exceeded five minutes while a `research` call is still running; run one `research` invocation at a time and wait for its final structured output (or a non-zero exit) before issuing another.
   - Do not use plain `chunkhound search`, `chunkhound research`, or `chunkhound mcp` as substitutes.
   - Build decomposition from review intelligence, PR metadata/context, branch diffs, source reads, and ChunkHound `search`.
   - Defer broad or costly architecture research to scoped step agents; use planning-time `research` only when a narrow decomposition question cannot be answered from lighter evidence.
   - In `Steps taken`, include the queries you used (1 line each), including any optional narrow `research` query.
   - If the staged ChunkHound helper is unavailable or fails, ABORT (no plan steps) and set `"abort": true` in the JSON output.
4. Build a step-by-step review plan:
   - Use the fewest genuinely independent steps needed for strong review coverage; treat `$MAX_STEPS` as a hard cap, not a target.
   - Cluster work by distinct root-cause family, failure contract, or primary evidence surface rather than by overlapping semantic labels.
   - If changed code may move raw persisted, external, framework, or generated input into stricter application assumptions, keep the Input Boundary Shape Risk check inside the owning subsystem step and make the step inspect the real raw-input boundary.
   - Merge candidate steps that would re-read the same changed-file cluster or investigate the same implementation fault line from multiple entrypoints.
   - Keep tests, regressions, and gap-checking inside the subsystem step that owns the risk unless they require a truly independent pass.
   - Avoid label-only fragmentation: do not split lifecycle, recovery, acceptance, caller-semantics, or background-flow checks into separate steps when they inspect the same code paths or invariants.
   - Each retained step must still be narrow enough to run independently without bloating context.
   - Each retained step must have a clear goal and focus area.
$COD_HYPOTHESIS_LEDGER_PLAN_GUIDANCE

# Output
Provide:
1) `### Steps taken` (minimal; 5 words max per line)
2) `### Plan` (human-readable bullets)
3) `### Plan JSON` (machine-readable; exactly one JSON code fence)

The JSON must conform to the schema below. Preserve `suggested_ch_search` and `suggested_ch_code_research` on every initial-plan step; use `suggested_ch_code_research` for narrow per-step research questions for the scoped step agents, not broad planner-executed architecture research.
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
