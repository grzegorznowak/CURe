---
description: Review Protocol (Local Sandbox, Big PR)
argument-hint: [PR_URL="<github pr url>"] [AGENT_DESC="<agent description>"]
---

You are maintainer reviewing $PR_URL in a local **isolated sandbox** checkout.
Ensure code quality, prevent technical debt, and maintain architectural consistency.

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
- Output using the format below.
- Use `**Summary**` starting with `ABORT:` and include the failure reason.
- Set `**Decision**` to `REJECT`.

# Review Process
1. Use the gate above to understand the business value and acceptance criteria; do not proceed without it.
2. Use local `git` to read the complete change set (authoritative for code):
   - `git diff <base>...HEAD --stat`
   - `git diff <base>...HEAD`
   - `git log --oneline --decorate <base>..HEAD`
3. Mandatory: use ChunkHound MCP tools at least once:
   - Run at least one `search` query for a symbol/pattern relevant to the PR.
   - Run at least one `code_research` query for cross-file/architecture understanding.
   - In `Steps taken`, include the queries you used (1 line each).
3. Think step by step, but only keep a minimum visible draft for each step, with 5 words at most.
   - Put these under a `Steps taken` section.
   - End the assessment with a separator line: `####`
4. Never speculate about code you haven't read — investigate files before commenting.
5. First make a plan of the review for the current PR at hand.
6. Split the plan into multiple discrete steps that each can be executed independently and within the budget of ~100k tokens.

# Critical Checks (for each review step)
- Can existing code be extended instead of creating new (DRY)?
- Does this respect module boundaries and responsibilities?
- Are there similar patterns elsewhere? Search the codebase.
- Is this introducing duplication?
- Do the changes conform to the architecture and module responsibilities?
- Do the changes respect and match surrounding patterns and style?
- Are there any security considerations?
- Are there any performance considerations?
- Do the changes maintain established contracts?
- Are there adequate tests covering new functions and features?
- Are no new issues introduced?

## How to understand the sources
- Prefer ChunkHound MCP tools for fast context (`search` + `code_research`).
- Tool names can appear as `chunkhound.search` / `chunkhound.code_research` (equivalent to `search` / `code_research`).
- Code research protocol:
  - Use `search` to quickly find definitions, call sites, and similar patterns.
  - Use `code_research` for deeper cross-file/architecture understanding (when needed).
  - Prefer `search` before opening large files; do not speculate without reading sources.
  - Cite `path:line` in issues when possible.
- If ChunkHound MCP tools are unavailable or fail, ABORT and set `**Decision**` to `REJECT`.
- Whenever you need to widen understanding by going into specific areas deeper, use subagents to do targeted full reads of given parts of the codebase.

## Output Format
```markdown
**Summary**: [One sentence verdict; mention Jira key(s) + business value alignment]
**Strengths**: [2-3 items]
**Issues**: [By severity: Critical/Major/Minor with file:line refs]
**Reusability**: [Specific refactoring opportunities]
**Decision**: [APPROVE/REQUEST CHANGES/REJECT]
```
