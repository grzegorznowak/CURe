# Progress: cure-chunkhound-daemon-aware-research-calls

## Current Claim
- Claimed at: 2026-08-03T03:47:51Z
- Claimed by: pi PR #33 final proof reconciliation
- Model: gpt-5.6-sol
- Scope: Current HEAD and code/test files remain bound to the accepted pre-finalization TAP-05 proof snapshot; TAP-07, deterministic, broad, static, and independent-review evidence closes the daemon-aware research-call story. The only post-proof deltas are authorized final OpenSpec bookkeeping in `story.md`, `tasks.md`, `progress.md`, and `specs/chunkhound-daemon-aware-research/spec.md`. `/home/vscode/pedf064` is the accepted auditable five-case live proof; `/home/vscode/tap05-auditable-20260803T033533Z-71e1a19f5e01` preserves failed-closed runner evidence; `/home/vscode/tap07-audit-PK8ojJ` is the isolated installed-wheel proof. TAP-07 executes installed production lifecycle APIs outside checkout and separately verifies installed `cure --help`; it does not claim installed CLI `_pr_flow_impl` execution.
- Main-tree targets: CURe
- Primary write surfaces: lifecycle/orchestration readiness implementation and tests, installed-runtime/wheel proof, openspec/changes/cure-chunkhound-daemon-aware-research-calls/
- Status: ✅ DONE

## Progress Timeline
- 2026-07-30T14:10:32Z — **Step**: validated the blocked canary handoff and preserved repository staging/dirty-state invariants.
  - Changed: `progress.md`
  - Test: PASS — default canary path (2 skips), focused Ruff, strict OpenSpec validation, staged-only config check, and exact ten-open-task count; RED — enabled real canary remains blocked by the reviewed-root daemon log write.
  - Notes: broader green gates are intentionally deferred because the external-runtime source-boundary gate remains RED.
- 2026-07-30T14:09:20Z — **Blocked**: the real installed-ChunkHound canary exposed a lifecycle-attributable reviewed-root write that conflicts with locked A22.
  - Changed: `tests/test_daemon_aware_chunkhound_live.py`, `blocked.md`, `story.md`, `progress.md`
  - Test: RED — both enabled non-empty and zero-chunk canary routes reach real keeper readiness/adjudication and release, then fail because installed ChunkHound creates `<reviewed-root>/.chunkhound/daemon.log`.
  - Notes: installed `chunkhound 0.1.dev1298+gb154b2f63` hard-codes the daemon log beneath the canonical project root. The default opt-out path skips cleanly and Ruff passes. No task was checked; exactly ten remain.
- 2026-07-30T14:01:47Z — **Resume**: continued after keeper integration/retention/budget closure with exactly ten tasks open, preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: add the opt-in real installed-ChunkHound no-LLM canary and reconcile its task evidence without duplicating completed deterministic or wheel proof.
- 2026-07-30T13:59:50Z — **Step**: completed surrounding regression, static, type, artifact, and diff validation for keeper-lifetime reconciliation.
  - Changed: `progress.md`
  - Test: PASS — 52 focused keeper/flow/tool-proof tests with 21 subtests; PASS — source/release selector; PASS — full pytest (882 tests, 86 subtests); PASS — Ruff; PASS — configured/scoped mypy; PASS — strict OpenSpec validation; PASS — staged/unstaged diff checks.
  - Notes: `openspec/config.yaml` remains the only staged path; all unrelated dirty and untracked work was preserved.
- 2026-07-30T13:58:30Z — **Step**: reconciled fresh standard, big, and multipass keeper integration/retention and locked cleanup-budget proof.
  - Changed: `tests/_reviewflow_unittest_daemon_aware_impl.py`, `tasks.md`, `progress.md`
  - Test: PASS — one public route proof with 3 subtests covers standard, big, and multipass one-keeper lifetime; PASS — 8 existing integration/retention/retry/no-replay/budget nodes.
  - Notes: production behavior was already implemented, so this reconciliation added exact missing route-shape evidence rather than repeating a completed behavioral RED slice. The two keeper integration/retention tasks and locked 5s TERM/2s KILL/2s drain budget task are checked; ten tasks remain.
- 2026-07-30T13:56:15Z — **Resume**: continued after completed A15 privacy proof with exactly thirteen tasks open, preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: reconcile completed fresh-route keeper integration/retention evidence and verify the locked 5s TERM/2s KILL/2s drain budgets without repeating finished lifecycle slices.
- 2026-07-30T13:54:44Z — **Step**: completed surrounding regression, static, type, artifact, and diff validation for the A15 privacy slice.
  - Changed: `progress.md`
  - Test: PASS — 51 focused keeper/flow/tool-proof tests with 18 subtests; PASS — source/release selector; PASS — full pytest (881 tests, 83 subtests); PASS — Ruff; PASS — configured/scoped mypy; PASS — strict OpenSpec validation; PASS — staged/unstaged diff checks.
  - Notes: `openspec/config.yaml` remains the only staged path; all unrelated dirty and untracked work was preserved.
- 2026-07-30T13:53:09Z — **Step**: completed the A15 recursive seeded-secret lifecycle-output audit and privacy-safe startup/continuity reporting.
  - Changed: `cure.py`, `tests/_reviewflow_unittest_daemon_aware_impl.py`, `tasks.md`, `progress.md`
  - Test: RED then PASS — secret-bearing native readiness failure no longer persists raw exception text; PASS — secret-bearing mid-review continuity failure persists/renders only a typed privacy-safe category and no replay; PASS — all 22 daemon-aware flow tests with 7 subtests.
  - Notes: terminal keeper startup/readiness and every fresh-route continuity boundary now replace raw external exception messages with a typed privacy-safe `ReviewflowError`; the initial multipass step route was corrected to use the same canonical wrapper rather than passing `lease.assert_alive` directly. The lifecycle-output privacy-audit task is checked.
- 2026-07-30T13:49:33Z — **Resume**: continued after completed safe-boundary continuity/no-replay and bounded pre-dispatch retry at the next workflow-selected unmet deterministic A1–A15 lifecycle proof slice, preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: select and complete the next unmet deterministic lifecycle proof red-first, then run the required regression and artifact gates.
- 2026-07-30T13:47:11Z — **Step**: completed TAP-03 A12 model-boundary continuity and bounded pre-model startup retry.
  - Changed: `cure.py`, `tests/_reviewflow_unittest_daemon_aware_impl.py`, `tasks.md`, `progress.md`
  - Test: RED then PASS — post-step/pre-synth loss and singlepass pre-reconcile loss nodes; RED then PASS — exactly-one keeper startup retry success and terminal second-failure nodes; PASS — all 22 daemon-aware flow tests with 7 subtests; PASS — 51 focused keeper/flow/tool-proof tests with 18 subtests; PASS — source/release selector; PASS — full pytest (881 tests, 83 subtests); PASS — Ruff; PASS — configured/scoped mypy; PASS — strict OpenSpec validation.
  - Notes: fresh orientation, multipass plan, every initial/retried step, every synth attempt, single-pass review, and prior-context reconciliation now check the retained lease immediately before model dispatch. Keeper open/readiness failure closes the failed attempt and retries exactly once before helper preflight or model work; a second failure remains terminal. Completed model work is never replayed after continuity loss.
- 2026-07-30T13:46:02Z — **Resume**: continued from the TAP-03 A12 partial state while preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: complete remaining fresh model-boundary continuity checks and one bounded pre-model keeper startup retry without replay after dispatch.
- 2026-07-30T13:32:58Z — **Step**: completed the first TAP-03 A12 safe-boundary continuity/no-replay slice.
  - Changed: `cure.py`, `tests/_reviewflow_unittest_daemon_aware_impl.py`, `tests/_reviewflow_unittest_grounding_impl.py`, `progress.md`
  - Test: RED then PASS — post-plan keeper loss node; PASS — all 19 daemon-aware flow tests with 7 subtests; PASS — 48 focused keeper/flow/tool-proof tests with 18 subtests; PASS — source/release selector; PASS — full pytest (878 tests); PASS — Ruff; PASS — configured/scoped mypy; PASS — strict OpenSpec validation; PASS — staged/unstaged diff checks
  - Notes: every initial multipass step and grounding retry now performs the retained lease's continuity check immediately before model dispatch. A loss after the already-dispatched plan prevents every step and synthesis dispatch; the plan is not replayed. The broader task remains open for other safe boundaries and bounded pre-model startup retry.
- 2026-07-30T13:28:53Z — **Resume**: continued from completed TAP-03 A4 eight-client overlap at the next unmet deterministic lifecycle slice while preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: prove safe-boundary keeper continuity loss stops subsequent model dispatch and never replays work after dispatch may have occurred.
- 2026-07-30T12:43:18Z — **Step**: completed broad regression, static, type, and artifact validation for the A4 overlap slice.
  - Changed: `progress.md`
  - Test: PASS — 47 focused keeper/flow/tool-proof tests with 18 subtests; PASS — source/release selector; PASS — full pytest (877 tests); PASS — Ruff; PASS — configured/scoped mypy; PASS — strict OpenSpec validation; PASS — staged/unstaged diff checks
  - Notes: `openspec/config.yaml` remains the only staged path; all unrelated dirty and untracked work was preserved.
- 2026-07-30T12:41:46Z — **Step**: completed TAP-03 A4 eight-client overlap proof against the canonical fresh multipass route.
  - Changed: `tests/_reviewflow_unittest_daemon_aware_impl.py`, `tasks.md`, `progress.md`
  - Test: initial harness-signature failure then PASS — focused eight-client overlap node; PASS — all 18 daemon-aware flow tests with 7 subtests; PASS — focused Ruff and diff checks
  - Notes: the initial failure was a test callback signature defect, not a behavioral RED. After correction, a deterministic eight-party barrier proved the existing implementation already supports all eight independent step/helper clients simultaneously on distinct worker threads, observing one expected generation and completing before the single continuously held keeper closes. No product implementation change was required.
- 2026-07-30T12:39:17Z — **Resume**: continued from completed TAP-07 A25 at the next unmet deterministic lifecycle slice while preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: prove eight independent multipass clients overlap without CURe-side serialization while one keeper remains continuously held.
- 2026-07-29T11:08:09Z — Resumed approved implementation, verified repository state and staged `openspec/config.yaml`, validated the change strictly with OpenSpec CLI 1.7.0, and mapped current architecture/test owners.
- 2026-07-29T12:02:26Z — Completed GREEN foundation slices for explicit MCP environment/canonical bootstrap, retained keeper lease, tagged Linux owned-process registry, and lossless final-index capture transport; focused daemon-aware proof is 13 passed with 12 subtests.
- 2026-07-29T15:03:40Z — **Resume**: reconciled the stale TODO header and false worktree entry, re-baselined the completed strict receipt/readiness primitives, and resumed at authoritative final-index receipt routing.
  Main-tree targets: CURe
  Claim: final index must produce the only receipt authority; exact-identity keeper readiness must complete before helper preflight/orientation/model work and remain leased through review cleanup.
- 2026-07-29T15:15:26Z — **RED (TAP-03 A1/A11)**: added a public `pr_flow` supported fresh indexed Codex-helper route proof. The focused test fails with `events == ["orientation"]` instead of `final-index/receipt-ready → keeper-native-health/expected-session-ready → helper-preflight → orientation`, proving optional orientation currently dispatches before the authoritative final-index receipt/readiness gate.
- 2026-07-30T10:59:49Z — **Resume**: verified the approved in-progress lifecycle state, preserved the intentionally dirty main-tree implementation and staged-only OpenSpec config, and resumed by re-baselining current proof before selecting the next unmet lifecycle slice.
  Main-tree targets: CURe
  Claim: re-baseline current daemon-aware implementation/proof and continue the next unmet A1–A25 slice red-first.
- 2026-07-30T11:09:29Z — **Step**: re-baselined current daemon-aware implementation proof and reconciled completed task checkboxes against executable evidence.
  - Changed: `openspec/changes/cure-chunkhound-daemon-aware-research-calls/tasks.md`, `progress.md`
  - Test: PASS — 58 focused daemon-aware tests with 54 subtests; PASS — full suite, 873 tests; PASS — Ruff; PASS — configured and scoped mypy
  - Notes: the story's original focused command is stale because `ChunkHoundHelperParityTests` is not exported; the corrected current public façade set is green. Twelve tasks are now checked and nineteen remain; live/source/wheel/release/documentation and broader concurrency/lifecycle proof remain open.
- 2026-07-30T11:15:30Z — **Resume**: continued from the latest verified baseline at the isolated A22 source-boundary proof seam.
  Main-tree targets: CURe
  Claim: add executable proof that daemon-aware lifecycle execution preserves reviewed-repository and operator-checkout bytes, types, modes, and symlink targets.
- 2026-07-30T11:18:05Z — **Step**: completed the isolated TAP-06 A22 source-boundary proof and repaired the stale focused verification selector.
  - Changed: `tests/test_chunkhound_daemon_aware_source.py`, `story.md`, `tasks.md`, `progress.md`
  - Test: PASS — dedicated source-boundary lifecycle test; PASS — source/release selector; PASS — 46 focused keeper/flow/tool-proof tests with 18 subtests; PASS — Ruff; PASS — configured and scoped mypy
  - Notes: the lifecycle test executes native fake keeper bootstrap, health, expected-session search adjudication, and close while byte/type/mode/symlink manifests prove both reviewed repository and operator checkout remain unchanged. The A16–A22 proof task is now checked.
- 2026-07-30T11:19:24Z — **Step**: completed the surrounding regression and artifact validation gates for the A22 slice.
  - Changed: `progress.md`
  - Test: PASS — full pytest (874 tests); PASS — `ruff check .`; PASS — strict OpenSpec change validation
  - Notes: no product implementation change was required; the source-boundary contract was green on its first executable run against the existing lifecycle implementation.
- 2026-07-30T12:05:12Z — **Resume**: continued from the completed A16–A22/source-boundary proof at TAP-07 installed-wheel evidence while preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: prove the isolated installed wheel executes the eligible keeper/helper lifecycle, imports no CURe module from the source checkout, and leaves no owned process or database-lock residue.
- 2026-07-30T12:10:27Z — **Step**: completed the first TAP-07 A23/A24 isolated-wheel slice and made it an exact release-workflow gate.
  - Changed: `tests/daemon_aware_research_calls_smoke.py`, `tests/test_release_workflow_unittest.py`, `.github/workflows/publish-package.yml`, `tasks.md`, `progress.md`
  - Test: RED then PASS — release-workflow owner; PASS — isolated sdist/wheel build, Twine, external-cwd wheel smoke; PASS — 12 release tests; PASS — full pytest (875 tests, 83 subtests); PASS — Ruff; PASS — configured/scoped mypy; PASS — strict OpenSpec validation
  - Notes: the smoke runs with `PYTHONPATH` unset and safe-path enabled, verifies the installed `cure --help` entrypoint, rejects CURe module origins under the source checkout, and exercises installed keeper bootstrap, native health/search adjudication, launch-identity equality, and close. A25 success/failure/Ctrl-C publication and spawn/terminate residue scenarios remain open, so the joint A23–A25 task stays unchecked; release-workflow ownership is checked.
- 2026-07-30T12:25:41Z — **Resume**: continued from the isolated-wheel A23/A24 gate at TAP-07 A25 while preserving the intentional dirty main-tree target and staged-only OpenSpec config.
  Main-tree targets: CURe
  Claim: prove installed-wheel success/failure/Ctrl-C publication and spawn-versus-terminate paths leave no owned descendants, keeper process, or database lock.
- 2026-07-30T12:31:05Z — **Step**: completed TAP-07 A25 installed-wheel owned-residue and database-release proof.
  - Changed: `tests/daemon_aware_research_calls_smoke.py`, `tests/test_release_workflow_unittest.py`, `tasks.md`, `progress.md`
  - Test: RED then PASS — release owner for the complete A25 scenario matrix; PASS — source process probe; PASS — isolated sdist/wheel build, Twine, and external-cwd installed-wheel smoke; PASS — 13 release tests; PASS — full pytest (876 tests); PASS — Ruff; PASS — configured/scoped mypy; PASS — strict OpenSpec validation
  - Notes: the installed smoke now exercises success and failure, provider/helper Ctrl-C after child creation before publication, spawn-first snapshot cleanup with a TERM-ignoring descendant, close-first pre-`Popen` rejection, keeper-process exit, and nonblocking database-lock reacquisition. The joint A23–A25 task is checked; no product implementation change was required.
- 2026-08-01T06:39:58Z Opened PR delivery record — https://github.com/grzegorznowak/CURe/pull/33 (status: open)

## Session Handoff

- **Timestamp**: 2026-07-31T14:10:55Z
- **Status**: ✅ DONE
- **Completed In This Session**:
  - Closed the A22 creation-only daemon-log contract with exact installed-runtime filter, source-boundary, and generation-ownership proof.
  - Passed the focused and full deterministic gates, independent pre-live review, and both enabled installed-ChunkHound non-empty/zero-chunk no-LLM canaries.
  - Documented keeper eligibility, lifetime, failure behavior, cleanup, privacy, and exclusions; reconciled every task.
  - Preserved all unrelated intentional dirty/untracked work and staged-only `openspec/config.yaml`.
- **Remaining**: none for this story.
- **Blockers**: none.
- **Next Steps**: none; final OpenSpec, build, Twine, and installed-wheel validation is complete.
- **Worktrees**:
  - CURe: /workspaces/cure_workspace/projects/CURe (intentional main-tree target)
- **Proof Statement**: PASS — focused 74 tests plus 72 subtests; full 918 tests with 2 default-skipped live tests; Ruff; configured and scoped mypy; isolated build, Twine, and installed-wheel smoke; strict completed OpenSpec status; independent re-review; and enabled live non-empty/zero-chunk canaries (2 passed in 31.72s).

## PR State
- PR URL: https://github.com/grzegorznowak/CURe/pull/33
- Number: 33
- Title: Retain one ChunkHound daemon across indexed review research calls
- Branch: feat/daemon-aware-chunkhound-research-calls
- Opened at: 2026-08-01T06:39:32Z
- PR status: open
- Review decision:
- Merge commit: —
- Merged at: —
- Last synced: 2026-08-01T06:39:58Z

## Unresolved Debt Friction
- None.

- 2026-07-31T10:18:15Z — **Contract amendment (A22 only)**: narrowed the approved source-boundary contract to the creation-only native daemon-log exception without changing product or test code.
  - Changed: initiative `initiative.md`; change `spec.md`, `story.md`, `proposal.md`, `design.md`, `tasks.md`, and this append-only `progress.md` entry. `blocked.md` and story blocked/status state remain unchanged.
  - Decision: native lifecycle may create exactly an initially absent canonical indexed-root `.chunkhound/` directory and its initially absent regular `daemon.log`. If either pre-exists, it is fully immutable; every other reviewed-root entry and every operator-checkout entry remains immutable in path, type, mode, symlink target, and content.
  - Gate: CURe must inject/dedupe exact `**/.chunkhound/**` in the materialized config and fail closed unless a non-degraded installed-runtime effective-filter probe demonstrates exclusion on every startup attempt and exact config/runtime identity. Daemon-log bytes cannot contribute to corpus, search, research, readiness, witness, receipt, launch/generation identity, or expected-session identity.
  - Tasks: retained A16–A21 parity as checked; reopened A22 exact-manifest/config/filter proof and retained the enabled non-empty/zero live canary as unchecked. There are now eleven unchecked tasks; a default skipped canary does not satisfy A22.
  - Implementation status: still blocked pending RED-first product/test implementation and enabled live proof; no blocker/status clearance is claimed.
  - Validation: PASS — `openspec validate cure-chunkhound-daemon-aware-research-calls --type change --strict --no-interactive`; staged-only `openspec/config.yaml` remained staged-only.

- 2026-07-31T10:38:57Z — **Blocking amendment correction (A22 only)**: corrected creation-only and generation-bound filter authority across the initiative/change artifacts; no product or test code changed.
  - Creation semantics: an absent `.chunkhound/` parent may be created as a directory as needed; when a real-directory parent already exists and `daemon.log` is absent, only the regular log may be created while parent type, mode, content metadata, and all siblings remain unchanged. A pre-existing log is fully immutable; a symlink or non-directory parent fails closed.
  - Generation gate: every startup attempt rejects every pre-existing or unattested same-root generation. After open, only the CURe-owned generation newly opened under that attempt's probed exact materialized-config/runtime identity may proceed; any mismatch is closed and fails before helper/model work.
  - Proof/tasks: the exact parent-present/log-absent case, invalid-parent faults and pre-existing-log immutability, pre-existing/unattested generation rejection, and post-open ownership/identity mismatch are explicit in A22, TAP rows, matrices, tasks, and the enabled live canary. The earlier requirement that both paths be absent is superseded.
  - Status: remains **BLOCKED**; `blocked.md` is unchanged, and no blocker/status clearance is claimed.

- 2026-07-31T14:10:55Z — **Complete**: cleared the A22 native-daemon-log blocker after the approved creation-only contract and enabled installed-runtime proof.
  - Changed: `README.md`, `story.md`, `tasks.md`, `progress.md`, `openspec/schemas/story-change/schema.yaml`; removed `blocked.md`.
  - Evidence: PASS — focused 74 passed + 72 subtests; full 918 passed / 2 skipped; Ruff; configured mypy (9 files); scoped mypy (3 files); isolated build, Twine, and external-cwd installed-wheel smoke; strict OpenSpec change/schema validation with `isComplete: true`; unstaged/cached diff checks; independent re-review; enabled non-empty/zero-chunk live canary 2 passed in 31.72s.
  - Notes: the canary proved only the permitted daemon-log delta and exclusion; all 25 acceptance rows are reconciled to executable evidence. The OpenSpec 1.7.0 graph cannot model an optional negative-presence blocker artifact, so the explicit `blocked.md` gate remains workflow-owned rather than a required graph artifact. `openspec/config.yaml` remains the sole staged path.

- 2026-07-31T15:31:27Z — **PRE-LIVE A22 proof correction**: the prior enabled two-case non-empty/zero canary is insufficient because it did not cross both chunk-count branches with absent-parent and existing-real-parent/log-absent state.
  - Schema correction: removed the false description that every story-change workspace has an explicit blocked artifact. The actual graph has required proposal/story/design/tasks/specs artifacts plus progress; blocker state is workflow-owned in story/progress.
  - Status/tasks: reopened the enabled live-canary task and current completion reconciliation; story status is BLOCKED and A22 remains provisional pending exactly four enabled cases: non-empty/zero × absent/existing parent. No enabled four-case result is claimed.
  - Allocation: TAP-02/TAP-03 deterministic proof owns seeded/pre-existing/unattested same-root rejection and post-open ownership mismatch; TAP-06 may own static/config/manifest proof. TAP-05 does not seed or manipulate pre-existing native generations and does not cover A13; it owns clean-start immediate pre-open/pre-spawn absence, exactly one validation, newly lease-owned `ExpectedGenerationEvidence`, continuity through marker/native session/readiness/client concurrency/pre-close, release to absence, exact `['**/.chunkhound/**']` once/effective exclusion, and marker/sibling/path absence plus exact source boundary across all four cases.
  - Deterministic correction proof: RED — helper-focused seam reported 13 pass / 3 fail because required helpers were absent; GREEN — 16 pass after the helpers were present. This is deterministic evidence only and is not an enabled-live result.

- 2026-07-31T15:55:14Z — **PRE-LIVE A22 zero-client remediation**: repaired the zero-chunk live row so it executes the same ordinary-client concurrency workload as the non-empty row before any enabled canary.
  - RED: the new always-run control-flow/behavior owner failed `1 failed` because `_exercise_live_index` had no shared ordinary-client workload after the non-empty/zero receipt split; tuple equality alone had not exposed the skipped zero-row clients.
  - GREEN: each receipt branch now selects an ordinary fresh `JsonRpcSession` operation (strict path/literal search for non-empty; strict healthy `daemon_status` for zero), then runs two sequential clients plus eight concurrent clients through one shared helper, bracketed by owned-generation continuity checks.
  - Evidence: PASS — exact RED owner `1 passed`; default source/live collection `17 passed, 4 skipped`; focused public daemon-aware owners `64 passed, 30 subtests`; source/release selection `17 passed, 13 deselected`; targeted Ruff, `py_compile`, scoped mypy, unstaged/cached diff checks, and sole-staged-path check. This is deterministic PRE-LIVE evidence only; no enabled four-case result is claimed and A22 remains provisional pending independent GO.

- 2026-07-31T16:09:29Z — **PRE-LIVE A22 proof-owner correction**: independent review rejected the first remediation because a new `if total_chunks and exercise_clients` wrapper could skip zero-row clients while the detached helper/lexical owner remained green.
  - RED: tightened the always-run owner to require the receipt-client route as an unconditional direct statement after the receipt split and to execute that route behaviorally for both `total_chunks=1` with a witness and `total_chunks=0` without one; the exact owner failed `1 failed` against the vulnerable structure.
  - GREEN: factored receipt dispatch into `_run_a22_receipt_client_concurrency`, invoked it unconditionally after both branches, and proved for each branch that the selected witness reaches one factory and its workload completes exactly two sequential plus eight simultaneously overlapping client calls. The live factory still creates one fresh bootstrapped `JsonRpcSession` per call and the zero route performs strict healthy `daemon_status` without search.
  - Evidence: PASS — exact owner `1 passed`; source/live default collection `17 passed, 4 skipped`; targeted Ruff, `py_compile`, scoped mypy, unstaged/cached diff checks, and sole-staged-path check. No enabled canary result is claimed; A22 remains provisional pending a fresh independent PRE-LIVE GO.

- 2026-07-31T16:14:20Z — **PRE-LIVE A22 ordinary-search correction**: independent review found that non-empty ordinary clients accepted any search text containing the literal rather than the strict native path/fence/footer witness grammar.
  - RED: a fresh-session ordinary-client owner supplied an exact successful JSON-RPC/tool envelope whose malformed search text contained the expected literal; the owner failed `1 failed` because the weak client accepted it.
  - GREEN: non-empty ordinary clients now delegate to the production `_require_native_search_witness` validator; the malformed literal-bearing payload fails closed while the session still closes. Zero clients remain strict `daemon_status` only.
  - Evidence: PASS — exact owner `1 passed`; source/live default collection `18 passed, 4 skipped`; targeted Ruff, `py_compile`, scoped mypy, unstaged/cached diff checks, and sole-staged-path check. No enabled canary result is claimed; A22 remains provisional pending fresh independent PRE-LIVE GO.

- 2026-07-31T16:38:05Z — **LIVE PASS and A22 completion reconciliation**: after a fresh independent PRE-LIVE GO, ran the exact enabled no-LLM four-case TAP-05 matrix and reconciled the current completion state.
  - Changed: `story.md`, `tasks.md`, `design.md`, and this append-only `progress.md` entry.
  - Evidence: PASS — `CURE_RUN_LIVE_CHUNKHOUND=1 python -m pytest tests/test_daemon_aware_chunkhound_live.py -v` completed all non-empty/zero-chunk × absent/existing-real-parent cases: `4 passed in 68.54s` with no skips or failures.
  - Reconciliation: tasks 34 and 45 are checked; A1–A25 proof maturity is final; A22 and TAP-05 pending language is closed; story status is `✅ DONE`. The prior two-case evidence remains historical and insufficient rather than being treated as this completion proof.
  - Notes: no live-harness behavior changed after the enabled run; `openspec/config.yaml` remains the sole staged path. Broad completion gates and final independent review follow in later append-only entries.

- 2026-07-31T16:41:17Z — **Final broad-gate PASS**: completed every non-live verification command owned by the story against the reconciled dirty tree.
  - Focused evidence: PASS — public keeper/lease/flow/tool-proof owners `64 passed, 30 subtests`; source/release selector `18 passed, 13 deselected`.
  - Broad evidence: PASS — full pytest `923 passed, 4 skipped in 48.39s`; `ruff check .`; configured mypy `9 source files`; scoped mypy `3 source files`; unstaged and cached `git diff --check`.
  - Artifact evidence: PASS — isolated disposable-mirror sdist/wheel build, Twine checks for both artifacts, external-cwd installed-wheel daemon-aware smoke, and deprecated `reviewflow` entrypoint absence.
  - OpenSpec evidence: PASS — strict change/schema validation; status JSON `isComplete: true`; 32/32 tasks checked; all 28 physical A1–A25 rows final; current story `✅ DONE`; no change-local blocker artifact.
  - Notes: the enabled four-case live proof was not rerun because no live-harness behavior changed. `openspec/config.yaml` remains the sole staged path; final independent review follows.

- 2026-07-31T16:52:59Z — **Final independent review: GO**: a fresh reviewer found no completion blocker in the current dirty tree.
  - Review: GO — DONE state, tasks 34/45 and all 32 checkboxes, all 28 final proof rows, historical two-case insufficiency, exact four-case live closure, current TAP-05 behavior, append-only progress, schema/status consistency, and sole-staged config all agree.
  - Evidence: no current normative A22/TAP-05 pending, provisional, or blocked language; no unproven claim, post-live harness change, or product regression found.
  - Notes: no files were modified or staged by the reviewer.

- 2026-08-01T08:50:06Z — **PR #33 local readiness correction opened**: reopened TAP-02/TAP-03/TAP-05/TAP-07 readiness proof before product edits.
  - Failure: one-shot strict native readiness observed exact `status="initializing"` with `query_ready=false`; the first attempt closed, and its retry collided with the newly created canonical `.chunkhound/daemon.log`. No helper or model work started.
  - Runtime evidence: an observed installed-runtime warm readiness interval was about 128 seconds, so retained-lease waiting requires a distinct bounded deadline rather than immediate rejection or close/reopen.
  - Required correction: wait only for the exact transient on one owned lease/generation with no pre-ready helper/model/search; timeout and degraded/malformed/transport/liveness/generation faults remain fail closed with one cleanup. TAP-05 must reuse the production primitive and TAP-07 receives proportionate delayed-ready/timeout coverage.
  - Status: implementation and proof are not complete; A22 semantics and its absent-log startup precondition remain unchanged.

- 2026-08-01T11:13:28Z — **PR #33 readiness correction complete; independent final GO**: closed all eight reopened tasks and restored DONE without changing A22 semantics.
  - Implementation: one owned lease/generation waits only on exact typed `status="initializing"` plus `query_ready=false`; every probe rechecks liveness/generation, authoritative top-level daemon `status` determines degraded/terminal state while backend-dependent dictionary `scan_progress` remains opaque, and search/helper/model dispatch stays behind ready. Exactly one retry remains only for typed `PreNativeSpawnLeaseOpenError` before native spawn and before any helper/model dispatch.
  - Budgets: native readiness is separately bounded at 600 seconds with 0.5-second polling; witness search retains its separate 60-second timeout; locked TERM/KILL/drain budgets remain unchanged.
  - Proof: PASS — full pytest `937 passed, 4 skipped, 122 subtests`; enabled TAP-05 production-route matrix `4 passed in 76.85s` (latest); isolated sdist/wheel build, Twine, and external-cwd installed-wheel lifecycle smoke; Ruff; configured mypy (9 files); scoped lifecycle mypy (3 files); strict OpenSpec; detect-secrets; diff checks; independent final review GO.
  - Packaging boundary: TAP-07 lifecycle-only readiness smoke proves delayed-ready/timeout behavior and no pre-ready search; it does not claim installed CLI `_pr_flow_impl` execution. TAP-03 owns no pre-ready helper/model dispatch.
  - Reconciliation: all acceptance rows remain final and now cite current correction evidence; historical runs remain append-only and are not current completion proof.

- 2026-08-01T12:41:26Z — **PR #33 second readiness incident; story reopened before product edits**: reopened the smallest fresh-instance readiness implementation, deterministic/route/live/wheel verification, broad-gate, and final-reconciliation tasks; no Python or tests changed in this step.
  - Preserved sandbox: `~/.local/state/cure/sandboxes/grzegorznowak-cure-pr33-20260801-112705-cced`. Installed tip `dd8c357` did execute. Final indexing completed with 4258 chunks; daemon startup succeeded; the command failed about 0.4 seconds later.
  - Evidence boundary: the exact `daemon_status` response was not persisted. Installed-source derivation plus preserved config/runtime/timing artifacts strongly infer a Watchman fresh-instance resync-derived degraded response; this is explicitly an inference, not a recorded payload.
  - Outcome: no model invocation occurred, and owned daemon/socket/registry/database-lock residue from this run was cleaned up.
  - Narrow amendment: general degraded remains terminal fail-closed. Exactly one waitable degraded condition requires documented active fresh-instance reconciliation (`needs_resync`, exact realtime-loss and fresh-instance reason/details), exact-null scan/realtime/resync errors, present non-degraded service state, and present non-stalled live-indexing state. Unknown, missing, wrong-typed, malformed, contradictory, non-fresh, or otherwise degraded evidence remains terminal.
  - Preserved contracts: A22 is unchanged; the retained lease/generation, 600-second readiness deadline, 0.5-second polling, separate 60-second witness search, and pre-native-spawn-only retry boundary remain unchanged.
  - Proof reopened: TAP-02 exhaustive transition/near-miss status matrix; TAP-03 real `_pr_flow_impl` retained-generation/no-pre-ready-dispatch/cleanup proof; one proportionate Watchman-enabled TAP-05 fresh-state canary while preserving the existing four A22 cases; TAP-07 installed-wheel fake fresh-resync success and true-degraded terminal cleanup. Current affected proof rows are pending until implementation and verification complete.

- 2026-08-01T15:09:17Z — **Second-incident contract correction before live rerun**: source/runtime inspection and the preserved correctly gated TAP-05 failure established that installed Watchman materializes packaged runtime files beneath the initially absent excluded `.chunkhound/watchman/` subtree.
  - Readiness clarification: `scan_progress.scan_error` is accepted only when absent or exactly null; `realtime.last_error` and `resync.last_error` must be present and exactly null. Strict malformed/truthy `needs_resync` rejection remains unchanged.
  - A22 amendment: the four ordinary clean-start cases retain their exact daemon-log-only boundary. The dedicated clean-start Watchman case alone may additionally create regular files/directories confined beneath the initially absent `.chunkhound/watchman/` subtree, while every pre-existing reviewed-root/operator-checkout entry and every path outside that narrow exception remains immutable and all runtime bytes remain excluded from corpus and expected-session evidence.
  - Proof state: static Watchman confinement/escape tests and focused readiness tests are green; A22 and the affected readiness rows remain pending until a new enabled dedicated TAP-05 result, TAP-07, broad gates, and independent final review complete.

- 2026-08-01T15:20:25Z — **Second-incident implementation and proof GREEN; awaiting independent final review**.
  - Product contract: one retained owned lease/generation waits on exact initializing/false or the sole typed active Watchman fresh-instance degraded condition. `scan_progress.scan_error` may be absent or exactly null; realtime/resync errors must be present and exactly null; ordinary-state true or non-boolean `needs_resync` and all other malformed/degraded near misses remain terminal.
  - TAP-05: PASS — dedicated correctly gated preserved run `/home/vscode/tap05-watchman-green-20260801TJMeQIx`, `1 passed in 15.83s`; PASS — current combined preserved run `/home/vscode/tap05-all-green-20260801T4mWOMc`, `5 passed in 94.56s`, preserving all four ordinary exact boundaries and adding the dedicated Watchman reconciliation/runtime-confinement case.
  - TAP-07: PASS — preserved `/home/vscode/tap07-wheel-green-20260801TZrowdW`; isolated sdist/wheel build, Twine checks, external-cwd installed-wheel smoke with fresh-resync success and true-degraded terminal cleanup, and release-workflow `13 passed`.
  - Broad gates: PASS — focused daemon-aware owners `69 passed, 30 subtests`; source/release selection `23 passed, 13 deselected`; full pytest `947 passed, 5 skipped`; Ruff; configured mypy (9 files); scoped mypy (3 files); strict OpenSpec; detect-secrets; staged/unstaged diff checks.
  - Reconciliation state: readiness/TAP-02/TAP-03/TAP-05/TAP-07/gate tasks and affected A1/A2/A3/A10/A11/A22/A23 rows are final. Story remains IN PROGRESS and the final reconciliation task remains unchecked until independent review GO.
- 2026-08-01T16:25:38Z — **Fresh NO-GO proof remediation implemented; live re-proof intentionally pending**.
  - TAP-05 harness: the dedicated Watchman case directly instantiates the installed `RealtimePathFilter`, requires at least one actual added regular Watchman file, and checks every actual materialized addition beneath `.chunkhound/watchman/`, while retaining the daemon-log effective probe and unchanged ordinary four-case source-delta semantics. Each of the four ordinary cases and the dedicated case writes to a distinct new child beneath the runner's preserved live-artifacts root.
  - Ledger: from classification-path/event-ledger initialization onward a finalizer attempts exclusive mode-0600, flush/fsync persistence on every failure path; successful proof persists before read-back. Open-vocabulary non-stalled live states and benign initializing observations may occur between the required first `fresh_instance_degraded` observation and first ready; no search may precede ready and subsequent status observations remain ready.
  - Auditable runner: `tests/tap05_live_proof_runner.py NEW_UNIQUE_PROOF_ROOT` refuses every existing root, executes five explicit leaf node IDs with both live gates, `PYTHONPATH=$PWD`, `-vv`, and private JUnit XML, and rejects zero-exit false success unless exactly those five nodes pass with no skip/failure/unexpected node and all five case roots exist. It separately records pytest and validated-proof exits plus validation audit, installed ChunkHound/Watchman path/version/digest identity, complete tracked/nonignored-untracked worktree manifests/digests and binary diffs before/after, stdout/stderr, and preserved live artifacts.
  - Semantic contract: exact `service_state == "degraded"` and exact `live_indexing_state == "stalled"` alone are terminal state values; both state fields otherwise accept open-vocabulary strings. Exact discriminator/fault fields retain strict unknown/malformed semantics; absent-or-null `scan_error` and malformed/truthy `needs_resync` behavior are unchanged.
  - Evidence state: runner RED tests exposed absent-report/all-skipped false-success seams and are now green in focused non-live proof. Previous TAP-05/TAP-07/broad passes remain pre-remediation evidence. A1/A2/A3/A10/all A11/A22/A23, TAP-05 re-proof, broad re-proof, and final reconciliation remain pending until a new live bundle and independent re-review pass. No live TAP-05 was run in this remediation step.

- 2026-08-03T03:47:51Z — **Final proof reconciliation complete; independent GO; story DONE**.
  - Tree binding: current HEAD `dd8c357bd5f044ff6d72ffe6cfe459ca0d45c441`; accepted TAP-05 bundle `/home/vscode/pedf064` records identical before/after HEAD, status, binary diff, and complete 119-entry tracked/nonignored-untracked manifest for the pre-finalization proof snapshot. Since that proof, only `story.md`, `tasks.md`, `progress.md`, and `specs/chunkhound-daemon-aware-research/spec.md` changed for authorized final OpenSpec bookkeeping; product and test files remain unchanged from the bound snapshot.
  - TAP-05: PASS — runner and validated-proof exits zero; private JUnit and exact `-vv` output agree on exactly five explicit passed leaves with zero skips/failures/unexpected nodes (`5 passed in 90.56s`). Failed-closed root `/home/vscode/tap05-auditable-20260803T033533Z-71e1a19f5e01` preserves pytest/proof exit 1, `accepted:false`, private empty ledger, and unchanged tree identity after the Watchman socket-length failure.
  - TAP-07: PASS — `/home/vscode/tap07-audit-PK8ojJ`; all eight build/Twine/fresh-install/external-cwd smoke/release-owner steps exited zero and release ownership completed `13 passed`. Installed production lifecycle APIs proved fresh-resync and terminal cleanup outside checkout; installed `cure --help` separately verified the entrypoint, without claiming installed CLI `_pr_flow_impl` execution.
  - Broad/static gates: PASS — full pytest `958 passed, 5 skipped, 178 subtests`; focused daemon-aware owners `69 passed, 30 subtests`; source/release selection `28 passed, 13 deselected`; Ruff; configured mypy (9 files); scoped mypy (3 files); strict OpenSpec; detect-secrets; unstaged and cached diff checks.
  - Production semantics: exact typed Watchman fresh-instance reconciliation alone is waitable on the retained owned lease/generation; all near misses remain terminal; A22 startup/filter/generation and source-boundary contracts remain intact.
  - Review/reconciliation: fresh independent review returned GO with no product, test, live-proof, gate, or production-semantics blocker. Exactly the three remaining tasks were checked; A1/A2/A3/A10, all four A11 rows, A22, and A23 are final; zero unchecked tasks and zero current pending proof rows remain.
