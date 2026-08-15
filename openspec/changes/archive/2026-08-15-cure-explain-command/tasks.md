# Tasks — Cure Explain Command

Absorption checklist for the delivered `cure explain` feature + review-flow hardening (PR #37, branch `feat/explain-command`, historical baseline sha `2d8c2b1`) and the operator-directed permission-model delta delivered at HEAD `f684f18`, followed by the pending A18–A25 round-6 remediation. Delivered tasks stay checked; pending delta tasks stay unchecked.

## Setup & Prerequisites
- [x] Initiate OpenSpec initiative `cure-explain-command` (initiative.md) under `projects/CURe/openspec/initiatives/`.
- [x] Verify the delivered branch state (sha 2d8c2b1, worktree clean, PR #37 CI green).
- [x] Carry the branch's change-workspace knowledge (S1–S16, A1–A16, D1–D28, 90 completed tasks) into this absorbed workspace; D29 is the subsequent operator-directed amendment.

## Core Implementation
- [x] Command surface: `cure explain <PR_URL>` positional + `--explain-prompt` + `--open-in-codex`; catalog entry; re-export contract (`cure_commands.__all__`, `cure` re-export).
- [x] Prompt: newcomer-first `prompts/explain.md` (persona, glosses, example policy, question mode, banned internal-prompting mentions, `EXPLAIN_RESUME_CONTEXT_NOTE` for forks).
- [x] Delivered inline + fork baseline: `_explain_flow_impl` via `run_llm_exec`; fork-on-resume with inline fallback when missing/unforkable history is surfaced as `ReviewflowError` (raw rollout-discovery `OSError` remains D28 F4); delivered forced read-only behavior at sha 2d8c2b1; `normalize_artifact=False`.
- [x] Provenance: `explains[]` entries record prompt source, provider/model/preset/transport, usage, question, and `resume: {mode, base_session_id, fork_session_id, interactive_command}`.
- [x] Streaming: active output controller, item-granular codex delivery, `Codex notice:` rendering for codex `error` items, `CodexJsonEventSink` drain for the stream tail.
- [x] Delivered interactive-handoff baseline: `--open-in-codex` flag + tty prompt → `codex resume <fork>`; sha 2d8c2b1 drops staged credential pointers from the spawn env (superseded by D29).
- [x] Codex-only backend: HTTP/gemini providers and transports rejected at parse/exec; removed-provider docs and positive fixtures made codex-only.
- [x] Session-meta lock-and-merge protocol: `mutate_session_meta` + `_session_meta_lock_path` (sidecar OUTSIDE the session dir); SessionProgress deep-baseline diff flushes + `drop()`/`deleted_keys` (both modes); no-op flush skip; `init()` sole full write.
- [x] Writers routed through the protocol: follow-up (paths, tool-proof persist via `_FOLLOWUP_FLOW_OWNED_META_KEYS`, followups append), resume drops, `_mark_resume_noop_completed`, interactive-resume `meta_updates`, verdicts persistence (`_persist_normalized_session_verdicts`), live-progress `drop("live_progress")`.
- [x] Strict metadata mutation: missing/corrupt `meta.json` raises in `mutate_session_meta`; flushes skip instead of resurrecting; deletion coordinated through the same lock (`clean_session`, `_delete_cleanup_sessions`).
- [x] Discovery: newest-first completed-session selection INCLUDING md-less sessions; `review_md_path: Path | None`; clear errors at explain / `pr --if-reviewed=latest` / follow-up dispatch; picker markers.
- [x] Retry isolation + drain: trust-error retry uses a fresh per-attempt events file and answer state; `drain()` in `finally` on every direct attempt; retention policy (retry success → failed file unlinked; retry failure → pointers restored).
- [x] Credential cleanup: `prepare_review_agent_runtime` owns cleanup on post-staging exceptions; staging-internal partial failures remove the private root.
- [x] CI collection repair: aggregate module class lists + `__all__` re-export the four restored impl classes; guard test in WorkflowContractTests.

## Verification & Proof
- [x] Rounds 2–5 findings remediated RED→GREEN: concurrency (SessionMetaMutationTests), discovery, strict meta, retry isolation/drain, credential cleanup, and test collection. Round 6 was triaged and verified; its findings are absorbed into this story (D28/A18–A25, operator decision 2026-08-13).
- [x] Full explicit suite: 2209 passed + 2 skipped + 2 known deselections + 434 subtests (known pre-existing `UtilityModelConfigTests::test_partial_utility_model_invalid_final_combination_fails_fast` deselected under BOTH node ids).
- [x] Bare `python -m pytest --collect-only` (CI parity) includes SessionMetaMutationTests / DarwinProcessIdentityTests / UtilityModelProvenanceTests / ChunkhoundCacheBuildLiveProgressTests.
- [x] Delivered live read-only baseline proof: `CURE_RUN_LIVE_READONLY=1 pytest tests/test_readonly_sandbox_live.py` passes with output outside the checkout + clean `git status` (to be reworked for D29).
- [x] Static checks: ruff, mypy 1.20.0, py_compile clean.
- [x] CI (ubuntu + macos-14 + detect-secrets) green across all rounds; PR #37 checks green at 2d8c2b1.

## Operator-Directed Permission Delta (D29)
- [x] Add a loud explain startup mode line reporting the delivered-interactive effective state on every run: sandbox `None`, approval `None`, bypass on.
- [x] Update the explain catalog copy at `cure_commands.py:216-217` to exactly `Same runtime-policy permission model as interactive sessions; effective sandbox/approval/bypass announced at run start.`; add separate RED→GREEN Story 26 assertions for the JSON `safety` value and the same rendered human-catalog copy, independent of explain entry presence.
- [x] Reuse the exact `prepare_review_agent_runtime` Codex construction (`cure_llm.py:1240-1288`): bypass `True`, sandbox/approval `None`, and `build_codex_flags_from_llm_config(..., include_sandbox=False)`; do not add permission config knobs.
- [x] Remove explain's hardcoded read-only/bypass-false `run_llm_exec` policy and `sandbox_mode` parameter (`cure.py:12789-12805`) so the inline explain-triggered `_strip_sandbox_search_flags` path is no longer entered; retain `normalize_artifact=False` and interactive-compatible remaining flags.
- [x] Replace the delivered fork filter (`_resume_compatible_codex_flags`, `cure_llm.py:356-367`, applied at `403-420`) on explain's fork path by routing through interactive `build_codex_resume_command`'s direct runtime-flag construction (`cure.py:2263+`; extract/reuse that construction if branch-specific `codex exec resume` framing must remain); preserve `--search` and every other interactive-forwarded flag in order, with no explain-specific stripping.
- [x] Rework `_open_interactive_codex_resume` (`cure.py:12625-12646`) from bare `codex resume <fork>` to `build_codex_resume_command`-style interactive construction (`cure.py:2263-2310`, interactive call at `13903+`): directly forward ordered runtime flags including `--search`, retain config overrides, apply delivered-interactive bypass, run in the session repository, and carry staged `GH_CONFIG_DIR`, `JIRA_CONFIG_FILE`, and `NETRC` pointers in the env; keep every target present for the full handoff, then clean every staged path after both successful and failing interactive exits.
- [x] RED→GREEN unit tests: all default/question × inline/fork prompts activate the intended builtin/context/question blocks with captured prompts proven to originate from the loaded literal template in every enabled branch (token-freedom by construction + template inspection per Fail-open Checks); exact inline explain/interactive policy parity at the shared seam (bypass on, sandbox/approval none, configured sandbox suppressed); for one shared runtime fixture, fork command runtime flags equal interactive resume's directly forwarded sequence, including `--search` and representative non-`-m`/`-c` flags, and `_resume_compatible_codex_flags` is not invoked; truthful mode-line behavior in both variants; inline/fork filter-path removal; and, as separate A14 obligations, actual `_open_interactive_codex_resume` command/env equality with the interactive resume builder (ordered flags/overrides, `--search`, bypass, repository cwd, staged pointers) plus staged-credential existence during handoff and cleanup after successful and failing exits.
- [x] Rework the opt-in live test into an interactive-parity proof that asserts the truthful mode line and a bounded expected mutation in a disposable checkout (`CURE_RUN_LIVE_POLICY=1`, owning file `tests/test_explain_runtime_policy_live.py`).
- [x] Run affected suites, full explicit suite with known deselections, collection parity, `ruff`, mypy 1.20.0, `py_compile`, catalog selftest, and CI; record evidence before approval/claim completion.

## Round-6 Findings Absorption (F1–F9, operator decision 2026-08-13)
- [x] F1: RED→GREEN table-driven containment for persisted `meta.logs.codex`/`codex_events` — each resolver rejects both absolute-outside and relative-`..` traversal after resolution, before any mkdir/write/open, same contract as `_session_path_within`; regressions cover both log keys × both persisted forms.
- [x] F2: RED→GREEN — after `run_llm_exec`, require `explain_md_path` to exist and be non-empty (stripped) before registering the `explains` entry or printing the output path; missing/empty artifact raises a clear error / nonzero exit.
- [x] F3: RED→GREEN — reject accepted-but-ignored codex-only controls at parse/preset (`--llm-header`, `--llm-set`, `--llm-verbosity`, `--llm-max-output-tokens`; preset request/metadata/headers/api_key/store/include), consistent with the removed HTTP providers.
- [x] F4: RED→GREEN — convert raw rollout-discovery `OSError` to the inline-fallback error path in explain's fork wrapper (or inside `fork_codex_session`); crash-repro regression test.
- [x] F6: RED→GREEN as two proof obligations — at the real streaming `run_cmd`/Popen boundary, terminate the untagged codex process group on `BaseException` before re-raise (killpg, reusing `_terminate_pipe_holder_group`); separately, at the `run_codex_exec` retry boundary, make cleanup `BaseException`-aware so cancellation restores retry artifacts/pointers.
- [x] F7: design first — recursive deep-merge or field-ownership rules for nested top-level `meta` fields; RED→GREEN per-field variants cover `phases` through SessionProgress flushes and `llm`/`codex` through `_persist_followup_meta`, proving concurrent different-member updates both persist.
- [x] F8: RED→GREEN — `flush` returns `persisted: bool`; `done()`/`error()` raise `ReviewflowError` when the write did not happen (missing/corrupt meta.json).
- [x] F9: RED→GREEN — stage `rf-jira` under the per-run UUID credential root (register before write); the rf-jira helper respects an already-staged `NETRC` instead of real-home `.netrc`; concurrent-prepare race regression.
- [x] Proof: run affected suites, full explicit suite with known deselections, collection parity, ruff, mypy 1.20.0, py_compile, selftest; record evidence before review.

## Implementation-Review Round 1 Repair
- [x] A23/TAP-14: replace helper-only `llm`/`codex` proof with interleaved on-disk variants through production `_persist_followup_meta` → `mutate_session_meta`; retain behavior-facing SessionProgress `phases` proof.
- [x] A24/TAP-13c: automate corrupt- as well as missing-`meta.json` variants for both `done()` and `error()`.
- [x] A25/TAP-15: execute the generated rf-jira helper as a subprocess and assert the staged `NETRC` reaches Jira despite an inaccessible real-home `.netrc`.
- [x] Reconcile Discovery Notes F7/F8 as delivered-baseline findings with pointers to D31/A23/TAP-14 and A24/TAP-13c.
- [x] Re-run focused owners, affected/full explicit suites, collection parity, ruff, mypy 1.20.0, py_compile, and selftest; record evidence and return to review.

## Implementation-Review Round 2 Repair
- [x] A18/TAP-11: validate `meta.logs.codex_events` containment at the effective generated events-file target after parent derivation, rejecting persisted `.` and absolute session-root values before flush/write/mkdir/open.
- [x] Add RED→GREEN raw-boundary variants in both TAP-11 owners, plus contained file-path and default-path positive resolver proof; align APM and Input Boundary Shape Risk wording with the effective-target contract.
- [x] Re-run focused owners, affected/full explicit suites, collection parity, ruff, mypy 1.20.0, py_compile, and selftest; record evidence and return to review.

## Implementation-Review Round 3 Repair
- [x] A23/D31: recursively merge fresh/working mappings added at the same baseline-absent member while preserving current-writer ownership for same-leaf conflicts, non-mapping leaves, and explicit deletions.
- [x] TAP-14: add RED→GREEN production-owner variants for baseline-absent `phases.review`, `llm.usage`, and `codex.capabilities`, plus a same-added-leaf different-value characterization.
- [x] Re-run focused owners, affected/full explicit suites, collection parity, ruff, mypy 1.20.0, py_compile, and selftest; record evidence and return to review.

## Implementation-Review Round 4 Repair
- [x] A23/D31: make recursive three-way mapping merge level-uniform by treating a baseline-absent value as an empty mapping at both the top-level entry and nested levels when fresh/working are mappings; preserve current-writer leaf/scalar/list ownership and explicit deletions.
- [x] TAP-14: add RED→GREEN production-owner variants where baseline omits top-level `phases`, `llm`, and `codex`; retain the pre-seeded top-level variants that guard baseline-absent nested mappings.
- [x] Re-run focused owners, affected/full explicit suites, collection parity, ruff, mypy 1.20.0, py_compile, and selftest; record evidence and return to review.

## Implementation-Review Round 5 Repair
- [x] A18: replace the `repo_dir.parent` log-containment derivation with the authoritative selected `session_dir`; thread it through `run_llm_exec`/`run_codex_exec` and every production caller into both display/event resolvers.
- [x] TAP-11: add RED→GREEN variants for both `codex` and `codex_events` across persisted `repo_dir == session root` and nested-repository shapes, covering sibling/sandbox-adjacent absolute targets, relative traversal, raw `.`/session-root event values, contained targets, and defaults.
- [x] Re-run focused owners, affected/full explicit suites, collection parity, ruff, mypy 1.20.0, py_compile, and selftest; record evidence and return to review.

## Integration & Cleanup
- [x] Accepted-exclusion documentation (story.md D27): symlink escape, rollout-tail validation, malformed-`explains` recovery, handoff env/exit semantics, interactive-resume race, and dashboard stderr; D27 records the accepted exclusions while D28 records the absorbed F1–F9 remediations.
- [x] Round-6 findings F1–F4 and F6–F9 triaged (verified real); absorbed into this story by operator decision 2026-08-13 (story.md D28/A18–A25) — no next-story seed.
- [x] Absorbed workspace written in the main tree: proposal.md, story.md (scaffold anchors + TAP-10 matrix + A1–A17 proof matrix), design.md, tasks.md; no delta specs (no capability spec covers CLI commands).

## Absorption
- [x] Commit the absorbed initiative + story workspace in the main tree (`projects/CURe/openspec`). (d708cdc + d2e0c70 pushed 2026-08-15)
- [x] At PR #37 merge: drop/archive the branch's `openspec/changes/cure-explain-command` to avoid an add/add conflict with this absorbed workspace. (b568783; PR #37 merged 2026-08-15)
- ~~Kick off the next story (round-6 findings F1–F4 and F6–F9) from this contract.~~ — superseded 2026-08-13 by the absorption decision (story.md D28/A18–A25).

## Round-7 Findings Absorption (G2–G13 scoped, operator decision 2026-08-15)
- [x] G2 (A26): RED fork+live command-shape test → GREEN resume search mapping + loud note; amend A9/D29 clause
- [x] G3 (A27): RED full-manifest cleanup tests (failure + success) → GREEN single enclosing finally
- [x] G4 (A28): RED interleaved interactive/early-persist merge tests → GREEN D31 ownership extension
- [x] G6 (A29): RED utility/saved-session validator tests → GREEN one shared validator
- [x] G7 (A30): RED first-attempt rollback tests → GREEN retry-parity envelope
- [x] G12 (A31): RED handoff-rc propagation test → GREEN exit-code propagation
- [x] G13 (A32): RED dashboard-stderr test → GREEN diagnostic tail

## Absorption Delta & Merge Prep
- [x] Amend story.md (badges, Scope, Out of Scope, S26–S32, A26–A32, TAP-16..21, APM rows, D27 partial supersession, D29 amendment, D31 formalization, D32–D34) and design.md; record scope decision on PR #37 comment
- [x] Fresh plan review approval entry in Plan Review Log (required by D30/D32; 2026-08-15T08:59:18Z request_changes + follow-up approve)
- [x] Update progress.md cycle record
- [x] Re-run full explicit suite + ruff + mypy at the new branch head (`5c71c1d`): 2269 passed; ruff/mypy clean
- [x] Confirm hosted CI green before merge (ubuntu/macos-14/detect-secrets green at b568783)
- [x] At PR #37 merge: drop/archive the branch openspec copy (records the stale A9 read-only text) — extends the existing box above (b568783; PR merged)
