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
- [x] Register `explain` subparser (`--pr` required, `--explain-prompt`, llm/codex overrides, quiet/no-stream/verbosity) and `main()` dispatch
- [x] Add `explain_flow` wrapper + `cure commands` catalog entry in cure_commands.py
- [x] Add `fork_codex_session` to cure_llm.py (byte-copy + uuid rewrite; ReviewflowError on missing base)
- [x] Thread `resume_session_id` through `run_llm_exec` / `run_codex_exec` / `build_codex_exec_cmd` (`codex exec resume` branch)

## Verification & Proof
- [x] RED: 10 initial obligations written and failing (missing impl) → GREEN after implementation
- [x] RED: 6 fork-mode obligations (fork+resume, three fallbacks, helper unit tests) → GREEN after fork implementation
- [x] Update stale closed-world catalog contract test (`test_commands_flow_json_returns_curated_agent_catalog` includes `explain`)
- [x] Full regression: 762/762 tests OK; ruff clean; py_compile OK
- [x] Real-run inline proof: `cure explain --pr .../pull/21` (builtin prompt) rc=0, 23.4s, artifact + meta recorded
- [x] Real-run fork proof: `cure explain --pr .../pull/21 --explain-prompt "..."` rc=0, 82.6s, answer with backing knowledge; base rollout sha256 unchanged (`a3711ee6…`); `meta.llm.resume` still base; fork rollout contains the continuation
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
