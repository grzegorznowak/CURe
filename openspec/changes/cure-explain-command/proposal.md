# Proposal: cure-explain-command

## Goal / Context
Users can run `cure explain --pr <PR_URL> [--explain-prompt <text>]` to get a
human-friendly, LLM-generated explanation of the final synthesized review of a
completed review session — grounded in the review's full context (codex resume-fork
mode) without disturbing the pristine post-review session state that `interactive`
gates on.

The command resolves the most recent completed session for the PR, reads its
`review.md`, and either:
- **resume-fork mode** (codex provider with a recorded resume session): clones the
  base codex session rollout under a fresh session id and runs
  `codex exec resume <fork-id>` with the user's prompt, so the model explains with
  the full backing knowledge of the original review run, or
- **inline mode** (fallback): sends the builtin/custom prompt with the review
  markdown appended as a one-shot LLM call.

The explanation is streamed to stdout and persisted as
`<session>/explain/explain-<ts>.md`; `meta.json` records an `explains` entry
(plus LLM usage) without ever modifying the base codex session or the recorded
resume pointers.

## Story Candidates
<!-- Single story — this change is the full scope. -->

## Decisions & Constraints
- D1 (Gate 1, human): target = `--pr <url>` → most recent completed review session.
- D2 (Gate 1, human): builtin default prompt (`prompts/explain.md`), overridable via
  `--explain-prompt`; prompt optional. Rejected: `--prompt/--prompt-file` mirror of `cure pr`.
- D3 (Gate 1, human): output always streams unless `--quiet`/`--no-stream`.
  Rejected: one-shot print.
- D4 (human): explain runs on a **fork** of the base codex session, never the base,
  so `interactive` keeps gating the pristine post-review state. Rejected: direct
  `codex resume <base>` (would consume the pristine state).
- D5: fork failure (missing base, non-codex provider, no resume info) → transparent
  inline fallback (review text appended), not an error.
- D6: explains entries record `resume: {mode, base_session_id, fork_session_id}`;
  `meta.llm.resume`/`meta.codex.resume` are never modified by explain.
- Scope boundary: deliberately lighter than `followup` — no chunkhound /
  review-intelligence / PR-context / TUI machinery.

## External Resources
- Agentic-workflow-cycle protocol run 2026-08-10 (A_I Gate 1 decisions, A_R design,
  B realization RED→GREEN, DONE report) — planning and evidence source.
- Real-run evidence: completed session `grzegorznowak-cure-pr21-20260804-060854-1f40`
  (codex-cli 0.144.6), inline run 07:12Z and resume-fork run 07:56Z, base rollout
  sha256 `a3711ee693042ae2` unchanged across both.
