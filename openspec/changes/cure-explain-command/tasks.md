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
