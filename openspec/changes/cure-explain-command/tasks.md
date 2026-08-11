# Tasks: cure-explain-command

<!-- All tasks complete — implementation and verification executed 2026-08-10
     under the agentic-workflow-cycle protocol in worktree
     ~/add-worktrees/CURe-explain-command (branch feat/explain-command). -->

## Setup & Prerequisites
- [x] Create implementation worktree latched to home (`~/add-worktrees/CURe-explain-command`, branch `feat/explain-command` from main fc6dba4)
- [x] Research command architecture + synthesized-review/LLM patterns (chunkhound-indexed, distilled to notebook pages)
- [x] Empirical feasibility proof: codex session fork (copy + uuid rewrite) and `codex exec resume <fork>` with `CODEX_HOME` scratch store; base rollout sha unchanged

## Core Implementation
- [x] Add `prompts/explain.md` builtin default prompt template
- [x] Implement `_explain_flow_impl` + `_recorded_resume_session_id` in cure.py (target resolution, auth staging, fork decision, prompt modes, explains entry)
- [x] Register `explain` subparser (`pr_url` positional required, `--explain-prompt`, llm/codex overrides, quiet/no-stream/verbosity) and `main()` dispatch
- [x] Add `explain_flow` wrapper + `cure commands` catalog entry in cure_commands.py
- [x] Add `fork_codex_session` to cure_llm.py (byte-copy + uuid rewrite; ReviewflowError on missing base)
- [x] Thread `resume_session_id` through `run_llm_exec` / `run_codex_exec` / `build_codex_exec_cmd` (`codex exec resume` branch)

## Verification & Proof
- [x] RED: 10 initial obligations written and failing (missing impl) → GREEN after implementation
- [x] RED: 6 fork-mode obligations (fork+resume, three fallbacks, helper unit tests) → GREEN after fork implementation
- [x] Update stale closed-world catalog contract test (`test_commands_flow_json_returns_curated_agent_catalog` includes `explain`)
- [x] Full regression: 762/762 tests OK; ruff clean; py_compile OK
- [x] Real-run inline proof: `cure explain .../pull/21` (builtin prompt) rc=0, 23.4s, artifact + meta recorded
- [x] Real-run fork proof: `cure explain .../pull/21 --explain-prompt "..."` rc=0, 82.6s, answer with backing knowledge; base rollout sha256 unchanged (`a3711ee6…`); `meta.llm.resume` still base; fork rollout contains the continuation
- [x] Remove scratch `~/.codex-test` (contained copied auth.json) after feasibility tests

## Integration & Cleanup
- [x] Notebook pages updated (`cure-command-architecture`, `cure-synthesized-review-and-llm`, `explain-command-spec`)
- [x] OpenSpec change workspace `openspec/changes/cure-explain-command/` (proposal/story/design/tasks)
- [ ] Operator decision: commit `feat/explain-command` branch (worktree untouched by openspec artifacts)
- [ ] Optional follow-ups (not committed): live smoke with other codex versions; `--prompt-file`

## PR #37 Review Remediation (2026-08-10)
- [x] RED: 9 review-obligation tests failing (read-only cmd shape, runtime policy, cleanup-on-config-failure, unique artifacts, meta lock, fork rollback, fork I/O conversion, reexport)
- [x] GREEN: read-only runtime — flow passes bypass:False/approval:None + sandbox_mode="read-only"; exec adds `--sandbox read-only`, resume adds `-c sandbox_mode="read-only"`; no `--dangerously-bypass-approvals-and-sandbox`
- [x] Resume command: whitelist flags to `-m`/`-c` (drop config `--sandbox`/`--search`), honor `--skip-git-repo-check` on retry
- [x] Streaming: register ReviewflowOutput (ui off) around the LLM run → display lines reach stderr live
- [x] Fork I/O failures (OSError/UnicodeError) → ReviewflowError → inline fallback
- [x] Cleanup: whole post-staging span in try/finally; `_stage_review_auth_support` partial-staging rollback (both copies); fork rollout deleted on failure
- [x] Concurrency: `explain-<ts>-<uuid8>.md` artifact names; meta append under file_lock with fresh reload
- [x] selftest: story26_cli_smoke catalog now expects 6 commands; smoke passes rc=0 against editable-install venv
- [x] Exports: `explain_flow` in cure_commands.__all__, cure.py command imports, reexport contract test
- [x] Full suite 770/770; ruff clean; py_compile OK
- [x] Real-run proof (PR21 12:08Z): write + `gh api user` probes denied by read-only sandbox; live stderr streaming; base rollout sha unchanged (a3711ee6…); recorded resume cmd shows `-c sandbox_mode="read-only"`, no bypass

## PR #37 Re-Review Remediation (2026-08-11)
- [x] RED: 9 new obligations failing (rf-jira skip, normalize skip, per-entry provenance,
  path containment ×2, merge-under-lock progress ×2, fork partial-write cleanup, sink
  error-item notice, codex normalize_artifact skip) → GREEN
- [x] Read-only checkout: `_stage_review_auth_support(stage_rf_jira=False)` for explain —
  no `rf-jira` write/delete in the sandbox repo checkout
- [x] Prose preservation: `normalize_artifact` param through `run_llm_exec` /
  `run_codex_exec` / `run_http_response_exec` (default True; explain passes False)
- [x] Provenance: `explains[]` entries carry provider/model/preset/transport + usage;
  explain no longer writes the review's top-level `meta.llm`
- [x] Containment: persisted `meta.paths` repo_dir/work_dir/review_md validated inside
  the session dir before any read/stage
- [x] Concurrency: `SessionProgress(merge_under_lock=True)` — flushes overlay
  progress-owned keys on a fresh reload under `file_lock`
- [x] Fork hygiene: partial rollout unlinked on write failure in `fork_codex_session`
- [x] Streaming reality: sink renders codex `error` items as `Codex notice:` lines;
  A5/S8 amended to item-granular delivery (codex emits whole completed items)
- [x] OpenSpec `--pr` examples → positional; suite counts 16 → 31
- [x] Full suite 771/771; ruff clean; py_compile OK

## PR #37 Re-Review Follow-up (2026-08-11, second user report)
- [x] Root cause A (explain re-produces the whole review): the builtin explain
  template is written for inline mode ("Below is the final synthesized review…");
  in fork/resume mode no review text is embedded, so the model can treat the
  prompt as a fresh review request and re-run the review (observed 09:02Z run:
  16KB review-shaped answer vs 2.8KB explanation at 07:25Z with the same base
  session). Fix: `EXPLAIN_RESUME_CONTEXT_NOTE` prepended in fork mode — the
  review is already in context, do NOT re-produce it, answer the question.
- [x] Root cause B (raw JSON garbage on the terminal): run.py's pump reads
  ~8192-char chunks and calls flush() after every chunk; CodexJsonEventSink.flush()
  force-consumed the partial `_pending` buffer, splitting single-line JSON events
  >8KB into parse-failing fragments that were compacted and dumped as raw JSON.
  Fix: flush() never consumes partial lines; new drain() consumes the final
  partial line when the stream ends (run_logged_cmd cleanup + run_codex_exec
  else-branch). Large events now render as compacted agent text.
- [x] RED: 3 new obligations (fork-prompt note, inline-prompt no-note, chunked
  flush sink ×2) → GREEN. Suite 771 → 774; ruff + py_compile + mypy clean.

## Converged explain prompt + additive question (2026-08-11)
- [x] `prompts/explain.md` rewritten to ONE converged format: bottom line →
  complete issue list (most important first, compact what/why/example/action
  blocks, no cutting issues) → what to do next; plain-language register for
  domain newcomers with concrete examples; grounding clause unchanged.
- [x] `--explain-prompt` is now additive: the user's text is appended as a
  `## User's question` block (landing after the review in inline mode, last in
  both modes) instead of replacing the builtin template; `explains[]` entries
  record the `question` text; `prompt_source: user:explain_prompt` unchanged.
- [x] RED: 2 new + 1 updated obligation (appended question, no-question default,
  fork-mode question) → GREEN. Suite 774 → 776; ruff + py_compile clean.

## HTTP provider removal — codex-only backend (2026-08-11, PR#37 review point)
- [x] Decision (operator): remove OpenAI/OpenRouter HTTP providers instead of
  implementing SSE streaming; codex CLI is the only LLM backend (gemini precedent).
- [x] Removed: `run_http_response_exec`, `build_http_response_request`,
  `_extract_http_response_output_text`, `_extract_json_object`,
  `_extract_usage_from_payload` (cure_llm/cure_runtime/cure.py dead copies),
  `HTTP_LLM_PROVIDERS`, openai-responses/openrouter-responses presets + compat
  mapping, provider_exec_smoke HTTP server/branches.
- [x] Stale configs fail with a clear `_raise_removed_http_provider_support`
  error (builtin preset, explicit http block, `--llm-preset`, run_llm_exec
  dispatch) mirroring the gemini removal pattern.
- [x] RED: 4 new removal tests + updated fixtures (utility/legacy/setup presets
  → codex; tests now use temp configs instead of the real `~/.config/cure`).
  Suite 776 → 779; ruff + py_compile clean.
- [x] User action: `~/.config/cure/cure.toml` still contains an
  `[llm_presets.openai-responses]` block — must be removed or every CURe run
  fails with the removal error.
- NOTE (pre-existing, not in suite): UtilityModelConfigTests
  `test_partial_utility_model_invalid_final_combination_fails_fast` fails
  standalone (expects an obsolete utility-effort rejection); excluded from the
  full-suite aggregator since before this change.
