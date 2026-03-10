---
description: Review Protocol (Local Sandbox, Big PR Follow-up)
argument-hint: [PR_URL="<github pr url>"] [AGENT_DESC="<agent description>"] [PREVIOUS_REVIEW_MD="<path>"]
---

You are maintainer continuing a prior review of $PR_URL in a local **isolated sandbox** checkout.

This is a FOLLOW-UP review for a large/complex PR. You must first read the previous review output:
- Previous review markdown: $PREVIOUS_REVIEW_MD

Current HEAD information:
- head_sha_before_update: $HEAD_SHA_BEFORE
- head_sha_after_update: $HEAD_SHA_AFTER

If the SHAs differ, focus on verifying fixes + new deltas. If they match, focus on validating that
the current state meets merge readiness against the previous review's concerns.

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

# Big Follow-up Review Process
1. Read the previous review at `$PREVIOUS_REVIEW_MD` and extract:
   - The critical/major issues that blocked approval
   - Any tests or proofs that were requested
2. Use local `git` to identify deltas since the previous review:
   - `git log --oneline --decorate $HEAD_SHA_BEFORE..$HEAD_SHA_AFTER` (if SHAs differ)
   - `git diff --stat $HEAD_SHA_BEFORE..$HEAD_SHA_AFTER` (if SHAs differ)
   - `git diff $HEAD_SHA_BEFORE..$HEAD_SHA_AFTER` (if SHAs differ)
3. Re-evaluate the PR holistically for merge readiness:
   - `git diff <base>...HEAD --stat`
   - `git diff <base>...HEAD`
   - `git log --oneline --decorate <base>..HEAD`
4. Mandatory: use ChunkHound MCP tools at least once:
   - Run at least one `search` query for a symbol/pattern relevant to the follow-up.
   - Run at least one `code_research` query for cross-file/architecture understanding.
   - Tool names can appear as `chunkhound.search` / `chunkhound.code_research` (equivalent).
   - In `Steps taken`, include the queries you used (1 line each).
5. Think step by step, but only keep a minimum visible draft for each step, with 5 words at most.
   - Put these under a `Steps taken` section.
   - End the assessment with a separator line: `####`
6. Never speculate about code you haven't read — investigate files before commenting.

## Output Format
```markdown
**Summary**: [One sentence verdict; mention Jira key(s) + what changed since last review]
**Strengths**: [2-3 items]
**Issues**: [By severity: Critical/Major/Minor with file:line refs]
**Reusability**: [Specific refactoring opportunities]
**Decision**: [APPROVE/REQUEST CHANGES/REJECT]
```
