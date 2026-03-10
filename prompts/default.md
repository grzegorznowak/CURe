# Review instructions

You are reviewing a GitHub PR checked out locally in an **isolated sandbox** (not the real working repo).

## What to review
- Correctness, security, performance, maintainability.
- Anything that could break prod or leak secrets.

## How to inspect
- Use git to see the change set:
  - `git diff <base>...HEAD`
- Prefer ChunkHound MCP tools for fast context (`search` + `code_research`).
  - Tool names can appear as `chunkhound.search` / `chunkhound.code_research` (equivalent to `search` / `code_research`).
  - Use `search` to locate symbols, references, and similar patterns.
  - Use `code_research` for deeper cross-file/architecture questions.
  - When reporting findings, cite `path:line` whenever possible.
- Requirement: use `search` at least once; use `code_research` at least once if any cross-file behavior is discussed.
- If ChunkHound MCP tools are unavailable or fail, ABORT and clearly state it in **Summary** (do not continue).
- If you must write scratch files, write only under `$REVIEWFLOW_WORK_DIR/tmp` (create it). Do not write under the repo tree (including `.reviewflow/`).
- Keep shell commands read-only (no edits). Do not run destructive commands.

## Output format (Markdown)
Provide:
- **Summary** (1–3 sentences)
- **Must-fix** (bullets with `file:line` when possible)
- **Suggestions** (bullets)
- **Tests / Verification** (what to run / what to check)
- **Questions / Unknowns** (anything you cannot verify)
