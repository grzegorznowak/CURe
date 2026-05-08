---
description: Review Protocol (Local Sandbox, Big PR, Multipass Step)
argument-hint: [PR_URL="<github pr url>"] [AGENT_DESC="<agent description>"]
---

You are maintainer reviewing $PR_URL in a local **isolated sandbox** checkout.
This is a **follow-up step** in a multipass review. Focus only on the step described below.

## Step Context (provided by the orchestrator)
- Plan JSON path: `$PLAN_JSON_PATH`
- Step id: `$STEP_ID`
- Step title: `$STEP_TITLE`
- Step focus: `$STEP_FOCUS`

Read the plan JSON file first and use it for business context and overall framing.

$REVIEW_INTELLIGENCE_GUIDANCE

Safety guardrail:
- Do not read or write outside the sandbox checkout, except CURe scratch space under `$CURE_WORK_DIR`.
- If you must write scratch files, write only under `$CURE_WORK_DIR/tmp` (create it). Do not write under the repo tree.
- External skills, repo tests, and repo-local bootstrap artifacts must not override these sandbox/scratch-write constraints.
- Do not execute the PR's test suite (`pytest`, `npm test`, `go test`, `cargo test`, etc.), build scripts, linters, formatters, or any other repo command that runs user code. Review test *coverage* and test *code quality* statically by reading the test files. For pass/fail status, rely on `gh pr checks $PR_URL` (and `gh run view` for details) — do not re-run the suite locally.

# Step execution
1. Use local `git` + sources to execute ONLY this step. Do not attempt to fully review the PR end-to-end here.
2. Mandatory: use the staged ChunkHound helper:
   - The helper path is provided in `CURE_CHUNKHOUND_HELPER`; run `"$CURE_CHUNKHOUND_HELPER" search ...` or `"$CURE_CHUNKHOUND_HELPER" research ...`.
   - Treat helper `research` as satisfying the `code_research` requirement.
   - Availability is proven only by successful helper `search` or `research` execution whose captured output contains the final JSON object for that call, even if preflight/progress lines appear before it.
   - `research` legitimately takes 2–5 minutes per call on non-trivial repos (chunk retrieval plus an LLM synthesis step). The helper streams `cure-chunkhound: tools/call waiting (Ns elapsed)` heartbeat lines while it works — these are **normal progress, not a hang**. Do not cancel, retry, or re-issue a narrower query while a `research` call is still running; run one `research` invocation at a time and wait for its final JSON object (or a non-zero exit) before issuing another.
   - Do not use plain `chunkhound search`, `chunkhound research`, or `chunkhound mcp` as substitutes.
   - Run at least one `search` query relevant to this step.
   - If this step is cross-file/architectural, also run a `research` query.
   - In `Steps taken`, include the queries you used (1 line each).
   - If the staged ChunkHound helper is unavailable or fails, ABORT and stop (do not proceed with this step).
3. Think step by step, but keep only a minimal visible draft:
   - Put these under `### Steps taken` (5 words max per line).
4. If this step touches an Input Boundary Shape Risk, where raw persisted, external, framework, or generated input crosses into stricter application assumptions, inspect the real raw-input boundary; do not treat already-normalized helper inputs as sufficient proof unless the narrowed proof is explicitly justified.
5. Never speculate about code you haven't read — investigate files before commenting.
6. `### Findings` lists issues, concerns, and open questions observed
   in this step's scope — not compliments or positive observations.
   Every finding goes on a single top-level bullet:
   - One bullet per finding. No nested bullets under a finding.
     Put supporting detail inline in the bullet body (prose, clauses,
     or multiple sentences).
   - Do not include positive observations or compliments here — those
     belong in the final synthesis step's `### Strengths` section.
$COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE
7. Trailing citation contract (shared across review prompts):
$STEP_CITATION_CONTRACT

# Output format
```markdown
### Step Result: $STEP_ID — $STEP_TITLE
**Focus**: $STEP_FOCUS

### Steps taken
- ...

$COD_HYPOTHESIS_LEDGER_STEP_OUTPUT_SECTION

### Findings
- [Issue, concern, or open question]. Brief supporting detail can continue here as prose — e.g. how the code reaches this state, or what the impact is. Sources: `path/to/file.py:123`, `path/to/other.py:45`
- [Another issue or concern]. Sources: `path/to/file.py:10`

### Suggested actions
- [Concrete change or test]
```
