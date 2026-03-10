---
description: Review Protocol (Local Sandbox, Big PR, Multipass Plan)
argument-hint: [PR_URL="<github pr url>"] [AGENT_DESC="<agent description>"]
---

You are maintainer reviewing $PR_URL in a local **isolated sandbox** checkout.
Your job in this call is to produce a **multipass review plan** for this PR that can be executed in multiple follow-up calls.

# Mandatory business-context gate (ABORT if you can't)
You must gather business context yourself via `gh` + `jira`. If any required `gh`/`jira` read fails OR if you cannot find at least one Jira key, ABORT (do not continue).

Required:
1. GitHub PR context via `gh` (networked reads):
   - `gh pr view "$PR_URL" --comments`
   - `gh pr diff "$PR_URL"`
   - `gh pr checks "$PR_URL"`
   - If `gh pr view --comments` is broken/noisy, you may switch to `gh api` REST calls.
2. Extract Jira keys from the PR text corpus using the regex: `[A-Z][A-Z0-9]+-[0-9]+`
3. For each Jira key, fetch ticket details via:
   - Do not call `jira` directly; always use the sandbox helper `./rf-jira` (it pins config + netrc).
   - First confirm auth works: `./rf-jira me`
   - `./rf-jira issue view KEY --plain --comments 10`
   - If Jira commands return `401 Unauthorized`, retry once (it can be transient). If it still fails, ABORT and instruct the operator to fix Jira auth (e.g. run `jira init`) outside this session. Do not paste tokens.
4. Extract additional URLs from the human-authored PR/Jira text only and crawl allowlisted URLs only:
   - Ignore machine-generated metadata URLs (for example `url`, `html_url`, `diff_url`, `patch_url`, `_links`, avatar URLs, and API link fields)
   - Always use `./rf-fetch-url "<url>"` for URL fetches (do not use `curl`/`wget` directly)
   - Allowlisted hosts are provided via `REVIEWFLOW_CRAWL_ALLOW_HOSTS` (comma-separated)
   - Skip GitHub URLs that point to the current PR or another GitHub resource you already read via `gh`
   - If a URL host is not allowlisted, do not fetch it.
   - Do not ABORT on URL-only fetch failures after `gh` and Jira succeeded; continue unless the missing URL blocks business context.

Safety guardrail:
- Do not read or write anything under `/workspaces/academy+/projects/*` (even “just to check”).
- If you must write scratch files, write only under `$REVIEWFLOW_WORK_DIR/tmp` (create it). Do not write under the repo tree (including `.reviewflow/`).

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
  "jira_keys": ["ABC-123"],
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
