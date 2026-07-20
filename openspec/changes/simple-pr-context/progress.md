# Progress: simple-pr-context

## Current Claim
- Claimed at: 2026-07-20T12:22:10Z
- Claimed by: pi coding agent fresh session (resume)
- Model: coding agent
- Scope: Remediate GATE-001, PRC-001, and PRC-002 from the latest implementation review with RED-first prompt provenance proof, canonical complete-delta Ruff coverage, and sole D-15 validator ownership.
- Main-tree targets: CURe
- Primary write surfaces: `cure.py`, `prompts/mrereview_gh_local_big_synth.md`, targeted prompt/proof owners, and OpenSpec coordination artifacts; preserve unrelated dirty work
- Status: 🟣 IN REVIEW

## PR State
- PR URL: https://github.com/grzegorznowak/CURe/pull/28
- Number: 28
- Title: Add simple PR context to cure pr reviews
- Branch: simple-pr-context-impl
- Opened at: 2026-06-21T04:32:41Z
- PR status: open
- Review decision:
- Merge commit: —
- Merged at: —
- Last synced: 2026-07-20T13:46:51Z

## Progress Timeline
- [2026-07-20T12:26:22Z] **Step**: Completed GATE-001/PRC-001/PRC-002 R14 remediation and transitioned the story to review.
  - Changed: `cure.py`, both multipass synth templates, `tests/cure_pr_context/test_templates.py`, and OpenSpec story/tasks/progress coordination.
  - Test: PASS — prompt/runtime 14; flow 67; resume 4 plus 2 subtests; combined amended 579 plus 30 subtests; full regression 784; complete 18-path Ruff inventory including both previously omitted untracked owners; mypy 6 source files; package smoke; merge-base diff hygiene; structural/provenance/sole-validator scans.
  - Notes: PRC-001 was reproduced RED before heading-only GREEN. The default interpreter's known `build.__main__` limitation remains environmental; disposable `build==1.5.0` wheel/install/import proof passed. Status transition `🔄 IN PROGRESS` → `🟣 IN REVIEW`.

- [2026-07-20T12:22:10Z] **Resume**: Resume the latest implementation-review remediation in the operator-designated dirty primary checkout while preserving unrelated work.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Correct the canonical Ruff changed-path inventory so untracked Python owners are included, label remote-only orientation accurately in both delivery prompts, remove the dead persisted-context reader that bypasses D-15, and reconcile proof.

- [2026-07-20T11:31:48Z] **Step**: Completed R13 canonical reconciliation and transitioned the story to review.
  - Changed: `story.md`, `tasks.md`, and `progress.md` coordination after bounded changes to `cure.py`, `cure_pr_context/corpus.py`, and the named R13 test owners.
  - Test: PASS — TAP-14 parser 1, historical/no-review 4, eligibility/no-remote 8; TAP-15 31; TAP-18/TAP-19 runtime/flow 75; current resume route 4 plus 2 subtests; TAP-22 19; combined amended 578 plus 30 subtests; full regression 783. Ruff passed 16 changed Python paths, mypy passed 6 source files, merge-base diff hygiene passed, and disposable wheel/install/import smoke passed.
  - Notes: A19/A21/A24/A25/A26/A31 are restored to final; all R13 tasks are checked; status transition `🔄 IN PROGRESS` → `🟣 IN REVIEW`. The default interpreter's exact package command remains unable to start because the known repository `build/` namespace has no `build.__main__`; the approved disposable `build==1.5.0` frontend completed the exact build/install/import operations.

- [2026-07-20T11:28:21Z] **Step**: Implemented bounded R13 catch and timestamp-order repairs and confirmed focused GREEN.
  - Changed: `cure.py` and `cure_pr_context/corpus.py` plus the R13 RED owners.
  - Test: PASS — 3 focused D-13 ordering tests; 4 focused real-flow/TAP-18 owner tests, including all four build/raw-file fault variants and required orientation-write degradation.
  - Notes: Fresh artifact-write handling is now scoped to `_finalize_and_persist_fresh_pr_context`; unrelated build and raw orientation cleanup/read faults escape unchanged. D-13 uses signed integer microsecond keys without UTC datetime construction.

- [2026-07-20T11:27:11Z] **Step**: Established R13 RED at the genuine fresh-flow and D-13 year-boundary seams before production edits.
  - Changed: `tests/test_cure_pr_flow.py`, `tests/_reviewflow_unittest_grounding_impl.py`, and `tests/cure_pr_context/test_corpus.py`.
  - Test: RED — genuine `_pr_flow_impl` build/raw orientation-file `OSError`/`UnicodeError` cases showed `OSError not raised`; parser-accepted maximum-year offset conversion raised `OverflowError` in `datetime.astimezone()`.
  - Notes: Required artifact-write degradation remains separately covered by the existing orientation-write route owner; no production source changed in the RED step.

- [2026-07-20T11:11:13Z] **Resume**: Resume approved R13 remediation in the operator-designated dirty primary checkout while preserving unrelated work.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Narrow unrelated fresh PR-context fault attribution, implement overflow-safe D-13 ordering, repair canonical TAP owner collection, and complete all reconciliation gates.

- [2026-07-20T10:15:39Z] **Replanning checkpoint from feedback absorption**
  - Feedback IDs: FB-031, FB-032, FB-033.
  - Contract sections updated: `story.md` Plan lane, Verification Commands, Feedback Source and Disposition, Input Boundary Shape Risk, TAP-14/TAP-15/TAP-18/TAP-19/TAP-22, Acceptance Proof Matrix, Critical Files, Implementation Notes, D-13, and Discovery Notes.
  - Risk / miss categories: escaped fail-open boundary recurrence; behavior-vs-mechanics/canonical proof ownership; external timestamp shape and overflow-safe semantic ordering.
  - Plan lane: `🟢 PLAN APPROVED` → `🟠 PLAN CHANGES REQUESTED`.
  - Status: remains `🔄 IN PROGRESS`.
  - Evidence disposition: prior GREEN results remain historical evidence but do not close provisional A19/A21/A24/A25/A26/A31 until the corrected canonical commands collect the named owners and the new real-flow/year-boundary seams pass.
  - Required next action: `/openspec-story-plan-review simple-pr-context simple-pr-context`; implementation resume follows only after the amended proof contract is independently approved.

- [2026-07-19T14:12:52Z] **Step**: Completed FB-025–FB-030 final proof reconciliation and transitioned the implementation to review.
  - Changed: `story.md` and `progress.md` coordination only; `tasks.md` was reviewed and required no new or changed checkbox because all existing R10–R12 remediation/gate tasks were already truthfully complete.
  - Test: PASS — exact focused TAP-14–TAP-22 owners, including TAP-15 30, TAP-16 16, TAP-17 12, TAP-18 26, TAP-19 7 plus 3, TAP-20 1 plus 2 subtests, and TAP-22 18; full suite 780 passed; complete changed-path Ruff, scoped `mypy cure_github.py cure_pr_context/`, merge-base diff hygiene, and disposable wheel/install/import smoke all passed.
  - Notes: Independent review found no remaining FB-025–FB-030 implementation or executable-proof blocker. A21/A22/A24/A25/A26/A31/A32 are final; all A19–A34 rows are final; default-on/general release remains separately operator-gated. Status transition `🔄 IN PROGRESS` → `🟣 IN REVIEW`; next action is a fresh oblivious `/openspec-story-review simple-pr-context simple-pr-context`.

- [2026-07-19T14:06:24Z] **Step**: Completed RED-first FB-025–FB-030 implementation and executable route-proof remediation.
  - Changed: `cure.py`, `cure_pr_context/__init__.py`, `cure_pr_context/corpus.py`, `cure_pr_context/orient.py`, `cure_pr_context/runtime.py`, `tests/cure_pr_context/test_corpus.py`, `tests/cure_pr_context/test_init.py`, `tests/cure_pr_context/test_orient.py`, `tests/cure_pr_context/test_runtime.py`, `tests/test_cure_pr_flow.py`, and `tests/_reviewflow_unittest_grounding_impl.py`.
  - Test: PASS — combined amended proof 575 tests plus 26 subtests; exact TAP-14/15/16/17/18/19/20/22 lanes all collect nonzero genuine owners; affected Ruff, scoped mypy, and diff checks passed during focused iterations.
  - Notes: Independent review found no remaining implementation or executable-proof blocker. A21/A22/A24/A25/A26/A31/A32 are eligible for final reconciliation after fresh broad regression, quality/type, diff, and package gates pass.

- [2026-07-19T09:48:01Z] **Step**: Added RED-first boundary primitives for FB-025, FB-026, and FB-030 before flow integration.
  - Changed: `cure_pr_context/corpus.py`, `cure_pr_context/orient.py`, `cure_pr_context/runtime.py`, `tests/cure_pr_context/test_corpus.py`, `tests/cure_pr_context/test_init.py`, `tests/cure_pr_context/test_orient.py`, and `tests/cure_pr_context/test_runtime.py`.
  - Test: RED confirmed for fixed-overhead overflow, precise timestamp ordering, missing fresh-injection finalization, CRLF byte preservation, and exact-string CRLF cap enforcement; GREEN — 40 package tests passed after FB-025 follow-up, FB-026 focused tests passed, and FB-030 focused/integration/flow tests passed.
  - Notes: FB-025 unit/composition behavior and the isolated FB-026/FB-030 primitives are implemented. Fresh/resume route wiring, failure-attribution and state-preservation proof, and nonzero TAP route owners remain open; provisional acceptance rows remain provisional.

- [2026-07-19T09:24:14Z] **Resume**: Resume approved FB-025–FB-030 remediation in the operator-designated dirty primary checkout while preserving unrelated work.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Correct fixed-overhead overflow classification, independent fresh-injection bounds, fail-open attribution, entered-path persistence and telemetry, route-level executable proof, and exact persisted-brief byte reuse including CRLF.

- [2026-07-18T08:26:57Z] **Step**: Closed the final package/regression gate and transitioned the completed implementation to review.
  - Changed: `story.md`, `tasks.md`, and `progress.md`; no product or test source changed in this pass.
  - Test: PASS — exact disposable `python -m build` wheel/install/import smoke, stronger installed-target import-origin check, 685 full-suite tests, complete changed-path Ruff, scoped mypy, and merge-base diff hygiene.
  - Notes: The ignored generated repository `build/` directory appeared as a namespace only because the default interpreter lacked the PyPA frontend. A disposable environment with `build==1.5.0` ran the approved command without repository dependency changes. A29 and R12 are closed; A19-A34/R10-R12 are complete.

- [2026-07-18T08:24:44Z] **Resume**: Investigate the package frontend failure and close the exact A29/R12 package/regression gate without changing unrelated dirty work.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Determine repository shadowing and available approved tooling, then run exact package smoke plus full regression/quality/type/diff gates before lifecycle reconciliation.

- [2026-07-18T07:28:00Z] **Step**: Closed three-route synth fallback proof and exact partial-stage metadata dictionaries; reconciled all executable gates while retaining the package blocker.
  - Changed: `tests/_reviewflow_unittest_grounding_impl.py`, `tests/cure_pr_context/test_init.py`, `story.md`, `tasks.md`, and `progress.md`.
  - Test: PASS — distinct fresh/regular/incremental fallback success and fatal captures; 480 combined tests plus 11 subtests; 685 full-suite tests; changed-path Ruff, scoped mypy, and merge-base diff hygiene. UNAVAILABLE — package smoke cannot start because `build.__main__` is absent.
  - Notes: A19-A28/A30-A34 and R10/R11 plus executable R12 gates are closed. A29 and the combined packaging/regression checkbox remain provisional/open solely for package smoke; lifecycle remains IN PROGRESS.

- [2026-07-18T07:18:57Z] **Resume**: Complete the remaining approved three-route fallback proof and exact metadata dictionaries, then reconcile final gates without overstating maturity.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Add distinct fresh, regular-resume, and incremental-resume fallback-success/fatal executor captures; close partial-stage D-14/D-18 dictionaries; run and reconcile evidence.

- [2026-07-18T07:07:30Z] **Step**: Closed fetched-versus-normalized stage telemetry, provider-usage plumbing, fatal-fallback telemetry retention, and A33 list/prompt-selected sentinels.
  - Changed: `cure_pr_context/{fetcher,__init__}.py`, `cure.py`, `tests/cure_pr_context/test_init.py`, `tests/test_cure_pr_flow.py`, and established historical-selection owner.
  - Test: RED — normalization failure lacked partial metadata and fatal fallback lost available fallback usage; initial A33 fixtures exposed an invalid verdict fixture. GREEN — focused owners, 475 combined amended tests plus 11 subtests, and 680 full-suite tests passed; complete changed-path Ruff, scoped mypy, and merge-base diff hygiene passed.
  - Notes: All endpoint arrays now validate transactionally before normalization, stage errors retain completed counts/latency, orientation/delivery/fallback provider usage is extracted without affecting behavior, and list/prompt-selected explicit-on routes prove immutable pre-sandbox non-invocation. Three-route fallback still needs distinct route-level scripted success/fatal captures before reconciliation.

- [2026-07-18T06:59:08Z] **Resume**: Continue exact D-14/D-18 telemetry, route-level fallback, A33, and final proof reconciliation in the operator-authorized dirty primary checkout.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Complete exact metadata/provider usage and fake-clock dictionaries, three-route executor fallback success/fatal proof, list/prompt-selected non-invocation sentinels, then final gates if evidence is complete.

- [2026-07-18T06:48:45Z] **Step**: Added shared synth fallback and strengthened resume telemetry/persistence without overstating exact-contract closure.
  - Changed: `cure.py`, `cure_pr_context/{__init__,runtime}.py`, `tests/test_cure_pr_flow.py`, and established historical/no-review flow owner.
  - Test: RED — focused flow collection failed for the absent resume metadata constructor; GREEN — 52 package/adapter/flow tests, 472 combined amended-owner tests plus 11 subtests, and 677 full-suite tests passed. Changed-path Ruff, scoped mypy, and complete-delta hygiene passed.
  - Notes: Fresh, regular-resume, and incremental-resume synth callsites now share exactly-one empty-context retry with authoritative pre-fallback flush and fatal fallback propagation; successful resume delivery mirrors current metadata. Remaining exact D-14/D-18 stage-partial/provider-usage real-flow proof and complete A33 variants keep the story IN PROGRESS. Package smoke still cannot start because the environment's `build` package has no `build.__main__`.

- [2026-07-18T05:26:21Z] **Resume**: Continue approved amended implementation from the operator-designated dirty primary checkout while preserving unrelated work.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Complete D-14/D-18 telemetry/persistence, exactly-one synth fallback across fresh/regular/incremental routes, A33/A34 sentinels, and final reconciliation.

- [2026-07-18T05:15:54Z] **Step**: Implemented bounded remote-only package and opt-in runtime/resume wiring with amended tests.
  - Changed: `cure_pr_context/{__init__,corpus,orient,runtime}.py`, `cure.py`, incremental synth template, targeted package/flow/runtime tests.
  - Test: RED — initial package tests failed collection for missing bounded selector/estimator APIs; GREEN — 48 focused package/adapter/flow tests passed.
  - Notes: Preserved strict GitHub adapter and opaque insertion; removed local-history composition/API from production package.

- [2026-07-18T05:15:54Z] **Step**: Ran regression and quality gates; retained IN PROGRESS for named proof gaps.
  - Changed: coordination handoff only.
  - Test: PASS — 468 combined amended-owner tests, 673 full-suite tests, changed-path Ruff, scoped mypy, and complete-delta diff hygiene. FAIL — package command could not start because `python -m build` is unavailable.
  - Notes: Exact three-route synth fallback and full D-14/D-18 metadata/persistence proof remain open, so no task boxes or lifecycle readiness were overstated.

- [2026-07-18T05:06:24Z] **Resume**: Resume approved amended implementation from the operator-designated dirty primary checkout while preserving unrelated work.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Implement FB-021–FB-024 R10–R12 with RED-first TAP-14–TAP-22 proof, then complete R12 gates and coordination.

- [2026-07-17] **P0 planning-artifact supersession/amendment**
  - Added initiative decisions FB-021–FB-024 for bounded end-to-end context, remote same-PR-only MVP, opt-in/fail-open control, and pilot observability/release gating.
  - Reconciled initiative, proposal, design, story, and tasks to fixed 12,000/1,000/100/2,000/2,000 estimated-token/event limits. The 12,000 limit covers the canonically serialized fully assembled orientation-generation prompt, with newest-first admission using only the budget remaining after fixed instructions/framing/PR-stats overhead and chronological model input restoration. Full unchanged remote audit evidence, stable metadata, and strict failure boundaries remain required.
  - Added normative resume authority: reuse only for originating `pr_context.outcome == "used"` plus an exact valid/in-cap persisted brief; missing/non-used/legacy/invalid states resume context-free without network enrichment.
  - Split no-data bypasses: zero normalized endpoint events is `bypassed/no_remote_context`; a nonempty corpus with zero admitted events preserves its complete audit artifact, skips orientation, and is `bypassed/no_selected_context`.
  - Plan transitioned `🟢 PLAN APPROVED` → `🟠 PLAN CHANGES REQUESTED`; Status remains `🔄 IN PROGRESS`. Historical implementation/review/task records were preserved and marked superseded where incompatible.
  - Replaced obsolete unchecked R10–R12 with RED-first TAP-14..TAP-17, bounded implementation, and TAP-18 final/opt-in pilot gates.
  - No production code/tests, lifecycle command, commit, push, or network action.

- [2026-07-16T16:01:17Z] **Replanning checkpoint from feedback absorption**
  - Feedback IDs: FB-019, FB-020.
  - Contract sections updated: initiative Feedback-Derived Decisions; story Scope, S3, A2/A4/A9/A10, Feedback Source and Disposition, Fail-open Checks, Input Boundary Shape Risk, Surface / Branch Proof Matrix, Design Sources, Design Element Trace, TAP-02/TAP-05, Acceptance Proof Matrix, Critical Files, Implementation Notes, Locked Decisions, and Discovery Notes; aligned `design.md` package/data-flow/API/corpus/orchestration design.
  - Risk / miss category: semantic invariant naming — selected-PR endpoint membership is the remote corpus boundary; footer/session/commit metadata is orientation data, not identity authority.
  - Plan lane: 🟢 PLAN APPROVED → 🟠 PLAN CHANGES REQUESTED.
  - Status: remains 🔄 IN PROGRESS.
  - Red-first seam: operator confirmed `test_corpus.py` remote-retention cases plus `test_integration.py` full endpoint-to-orientation/debug proof; existing local safety and all prior regression gates remain unchanged.
  - Required next action: `/openspec-story-plan-review simple-pr-context simple-pr-context`; implementation resume follows only after the amended contract is independently approved.
- [2026-07-16T14:36:49Z] **Step**: Completed R9 proof reconciliation and transitioned the story to review.
  - Changed: finalized `story.md`, `tasks.md`, and `progress.md`; all affected A2-A6/A8/A10/A12-A16 rows are `final`, and all approved tasks are checked.
  - Test: PASS — 86 focused package/adapter/flow tests; 4 established real synth runtime captures; 711 full-suite tests; Ruff on all 16 merge-base-delta Python paths; scoped mypy on 5 typed source files; isolated installed-wheel imports; structural traceability; and `base="$(git merge-base HEAD origin/main)"; git diff --check "$base" --` at merge base `775c8617c9fb6b63c51cd400a974d22e109cf6fb`.
  - Notes: Status transition `🔄 IN PROGRESS` → `🟣 IN REVIEW`. Main-tree target remains `CURe`; no commit, push, live GitHub CLI, or network request occurred.
- [2026-07-16T14:35:11Z] **Step**: Completed FB-012..FB-018 implementation/proof and distinct TAP-11/TAP-12 adapter coverage.
  - Changed: `cure.py`, `cure_github.py`, `cure_pr_context/{corpus,orient}.py`, `tests/test_cure_github.py`, affected PR-context/flow tests, and established real fresh/resume runtime proof owners.
  - Test: RED — 14 intended failures reproduced zero-document decoding, variable/unterminated fence and canonical-instruction gaps, terminal-footer precedence, relative-root drift, and marker/cardinality insertion defects; TAP-11/TAP-12 plus seeded normal/big freshness checkpoints were already GREEN against preserved implementation. GREEN — 86 focused package/adapter/flow tests and all 4 established fresh-nonempty/fresh-empty/resume-persisted/resume-absent runtime captures passed.
  - Notes: TAP-11 proves exact CLI command/retry/cache/routing only; TAP-12 separately proves real public-helper two-page Link traversal and invalid-JSON/non-array failures with fake HTTP. No live CLI/network was used; FB-010 terminal both-attempt exception provenance remains deferred.
- [2026-07-16T14:25:46Z] **Resume**: Continue the approved implementation contract from the operator-designated dirty primary checkout without discarding prior work.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Implement FB-012..FB-018 and distinct TAP-11/TAP-12 proof with RED-first checkpoints, then complete R9 validation and coordination reconciliation.
  - FB-013 checkpoint: preserved source `manual:sha256-ebd73804df89:2`; merge base `775c8617c9fb6b63c51cd400a974d22e109cf6fb`; `git diff --check "$base" --` passed before remediation, superseding the historical bare-gate contradiction with current complete tracked-delta evidence.
- [2026-07-16T12:37:27Z] **Replanning checkpoint from feedback absorption**
  - Feedback IDs: FB-012, FB-013, FB-014, FB-015, FB-016, FB-017, FB-018
  - Contract sections updated: `story.md` Plan lane, Fail-open Checks, Input Boundary Shape Risk, Surface / Branch Proof Matrix, Verification Commands, TAP-02/TAP-03/TAP-05/TAP-06/TAP-07/TAP-08/TAP-10, Acceptance Proof Matrix, and Implementation Notes; `design.md` decoder, corpus, orientation-finalization, and opaque-insertion design.
  - Risk / miss categories: behavior-vs-mechanics proof; platform/API failure; prompt/template fail-open; semantic footer identity; filesystem/input-boundary shape.
  - Plan lane: `🟢 PLAN APPROVED` → `🟠 PLAN CHANGES REQUESTED`.
  - Status: remains `🔄 IN PROGRESS`; the preceding implementation review already reopened the story.
  - Evidence disposition: prior GREEN results remain historical evidence but do not close the newly provisional A2/A3/A4/A5/A6/A8/A10/A12/A13 rows. The prior bare `git diff --check` readiness claim is superseded by TAP-08's merge-base-to-working-tree check, which must pass after remediation.
  - Required next action: `/openspec-story-plan-review simple-pr-context simple-pr-context`; implementation resume follows only after the amended proof contract is independently approved.
- [2026-07-16T11:24:29Z] **Step**: Repaired the canonical claim classification and restored the completed story to review.
  - Changed: `openspec/changes/simple-pr-context/progress.md` only; product implementation and tests were untouched.
  - Test: PASS — story-review worktree preflight resolves `CURe` as an intentional dirty main-tree target with no feature-worktree branch gate; A1-A13 final proof, all checked tasks, required coordination sections, approved Plan, PR branch/state, and `git diff --check` remain valid.
  - Notes: Status transition `🔄 IN PROGRESS` → `🟣 IN REVIEW`; no blocker, commit, push, worktree creation, or branch rename occurred.
- [2026-07-16T11:23:26Z] **Resume**: Reopened the review submission transiently to repair the prior oblivious review's named worktree-preflight mapping defect.
  Worktrees: none
  Main-tree targets: CURe
  Claim: Classify the active primary checkout as intentional dirty main-tree work, validate review preflight, and preserve all completed implementation/proof and delivery state.
  Status transition: `🟣 IN REVIEW` → `🔄 IN PROGRESS` for the bounded readiness repair.
- [2026-07-16T06:23:46Z] **Step**: Completed approved remediation, reconciled proof, and transitioned the story to review.
  - Changed: `cure_github.py`, `cure_pr_context/{corpus,orient}.py`, `cure.py`, all affected TAP owners, `story.md`, `tasks.md`, and `progress.md`.
  - Test: PASS — 58 focused package/flow tests; 2 established full fresh/resume prior-context tests; 681 full-suite tests plus 11 subtests; scoped Ruff and mypy; isolated wheel/install imports; structural traceability and `git diff --check`.
  - Notes: A2/A3/A4/A5/A8/A10/A12/A13 are final; all tasks are checked; no blockers remain.
- [2026-07-16T06:18:00Z] **Step**: Implemented and proved FB-003/FB-007/FB-008 flow boundaries.
  - Changed: `cure.py`, `tests/cure_pr_context/test_templates.py`, `tests/test_cure_pr_flow.py`, and established fresh/resume owners in `tests/_reviewflow_unittest_grounding_impl.py`.
  - Test: RED — 8 focused failures reproduced missing opaque insertion, canonical finalized persistence, missing/empty/stale pass artifacts, and non-atomic draft acceptance; GREEN — all focused tests and both full runtime prompt captures passed.
  - Notes: scanner raw output is noncanonical; finalized orientation persistence is atomic; context-bearing singlepass uses fresh draft/reconcile artifacts and atomic pass-two promotion; fresh/resumed synth insertion preserves the active-key sentinel byte-for-byte.
- [2026-07-16T06:10:00Z] **Step**: Implemented and proved A13 plus FB-002/FB-004/FB-005/FB-006/FB-009 boundaries.
  - Changed: `cure_pr_context/corpus.py`, `cure_pr_context/orient.py`, `cure_github.py`, corpus/orient/init/integration tests, and decoder tests.
  - Test: RED — 13 intended failures reproduced permissive missing/non-file omission, containment escapes, identity pruning, fenced headings, and non-array decoding; GREEN — 31 package tests and 22 focused boundary tests passed.
  - Notes: matching completed-session artifacts now fail hard with session/path observability before orientation or artifact writes.
- [2026-07-16T06:05:41Z] **Resume**: Continue the approved implementation contract from the operator-designated active checkout while preserving dirty planning artifacts.
  Worktrees: CURe=/workspaces/cure_workspace/projects/CURe
  Claim: Implement FB-002..FB-009 and A13 with RED-first deterministic proof, then complete R1-R6 validation and coordination reconciliation.
- [2026-07-15T14:19:32Z] **Replanning checkpoint from feedback absorption**
  - Feedback IDs: FB-001 contradicted-proof umbrella; FB-002 resolved sandbox containment and corrupt local metadata/file propagation; FB-003 context-bearing pass-artifact freshness; FB-004 right-anchored production session-ID parsing; FB-005 identity-first discussion pruning; FB-006 fence-aware heading normalization; FB-007 finalized canonical persistence and exact resume consumption; FB-008 opaque context substitution; FB-009 strict array-document/page decoding.
  - Contract sections updated: `Scope`; `Scenarios / Behavior Examples` (S2, S3, S5-S9); `Acceptance` (A2-A5, A8, A10, A12); `Verification Commands`; `Fail-open Checks`; `Input Boundary Shape Risk`; `Surface / Branch Proof Matrix`; `Risk Lens Inventory`; `Design Element Trace`; `Test Architecture Plan` (TAP-01..TAP-07, TAP-10 source-fit); `Acceptance Proof Matrix`; `Critical Files`; `Implementation Notes`; `Locked Decisions`; `Discovery Notes`; and aligned architecture text in `design.md`. All affected proof rows remain provisional with explicit open details.
  - Risk / miss categories: contradicted final proof; permissions/security and filesystem containment; corrupt persisted input; generated-artifact freshness; production identifier parsing; semantic identity/deduplication; fenced-Markdown validation; canonical persistence/interruption/resume consistency; prompt substitution fail-open; external API/subprocess shape validation.
  - Phase C: operator confirmed four red-first seam groups covering corpus/containment/parser/identity, orientation/corrupt-input/finalization, `cure.py` flow/artifact/persistence/resume/substitution, and raw GitHub decoding.
  - Plan transition: `🟢 PLAN APPROVED` → `🟠 PLAN CHANGES REQUESTED`.
  - Status transition: `🟣 IN REVIEW` → `🔄 IN PROGRESS`.
  - Required next command: `/openspec-story-plan-review simple-pr-context simple-pr-context`
- [2026-07-15T11:29:50Z] **Step**: Completed the approved story and transitioned it to review.
  - Changed: preserved prior corpus/orientation WIP; added cure.py resume wiring and A5/A8/A12 tests; updated only story/progress/tasks coordination artifacts.
  - Test: PASS — 27 PR-context/flow tests; 649 full-suite tests; scoped Ruff and mypy; wheel/install imports; template-token, package-file, and diff checks.
  - Notes: All acceptance rows A1-A12 are final and all tasks are checked. An extra non-gate whole-module mypy probe exposed 225 existing errors across cure.py/imported legacy modules; the approved TAP-08 scope remains clean.
- [2026-07-15T11:27:24Z] **Step**: Closed provisional A5, A8, and A12 implementation/proof gaps.
  - Changed: cure_pr_context/orient.py, cure.py, tests/cure_pr_context/test_orient.py, tests/test_cure_pr_flow.py, tasks.md
  - Test: GREEN — 14 direct orient/flow tests passed; 27 full PR-context plus flow tests passed.
  - Notes: Scanner prompt now bounds resolved-area claims to supplied text; resumed shared synth reads persisted context or `""`; reconcile failure proof observes propagated exception, error session state, and no successful draft acceptance.
- [2026-07-15T11:26:18Z] **Step**: Added deterministic A5, A8, and A12 regression proofs before implementation.
  - Changed: tests/cure_pr_context/test_orient.py, tests/test_cure_pr_flow.py
  - Test: RED as expected for A5 (1 failed) and A8 present/absent resume cases (2 failed); A12 proof passed against existing fail-hard flow behavior (1 passed).
  - Notes: A5 lacks the bounded scanner instruction; A8 lacks persisted-or-empty resume loading/substitution. A12 already propagates and records the reconcile exception while leaving the draft in a failed session.
- [2026-07-15T11:23:35Z] **Resume**: Continue the approved implementation contract from the preserved eight-file WIP.
  Worktrees: CURe=/home/vscode/add-worktrees/CURe-simple-pr-context-impl
  Claim: Close provisional A5 scanner-prompt proof, A8 resumed-synth substitution, and A12 reconcile fail-hard observability using red-first deterministic tests.
- [2026-07-15T06:26:05Z] **Step**: Implemented and verified all three review remediations; story is ready for fresh review.
  - Changed: cure_pr_context/corpus.py, cure_pr_context/orient.py, tests/cure_pr_context/test_corpus.py, tests/cure_pr_context/test_orient.py, OpenSpec contract/progress artifacts.
  - Test: PASS — focused 9 passed; context/flow 24 passed; full suite 644 passed plus 13 subtests; Ruff, mypy, diff check, and package smoke passed.
  - Notes: All tasks remain checked; status transitioned to `🟣 IN REVIEW`.
- [2026-07-15T06:24:00Z] **Step**: Added red-first regressions for all three review findings.
  - Changed: tests/cure_pr_context/test_corpus.py, tests/cure_pr_context/test_orient.py
  - Test: FAIL as expected — 3 failed, 6 passed.
  - Notes: Failures independently reproduce duplicate retained reviews, 5-gram threshold behavior, and substring-based section detection.
- [2026-07-15T06:20:01Z] **Resume**: Address three latest implementation-review findings using TDD.
  Worktrees: CURe=/home/vscode/add-worktrees/CURe-simple-pr-context-impl
  Claim: Deduplicate local/remote copies of one review, enforce character 3-grams with threshold coverage, and guarantee five required Markdown headings.
- 2026-06-21T04:32:50Z Opened PR delivery record — https://github.com/grzegorznowak/CURe/pull/28 (status: open)
- 2026-07-20T13:46:51Z Refreshed PR delivery record — https://github.com/grzegorznowak/CURe/pull/28 (status: open)

## Session Handoff

- **Timestamp**: 2026-07-20T12:26:22Z
- **Plan**: 🟢 PLAN APPROVED
- **Status**: 🟣 IN REVIEW
- **Completed In This Session**:
  - Acknowledged and remediated GATE-001, PRC-001, and PRC-002 under R14 without changing the approved product contract.
  - Repaired the canonical Ruff inventory to include untracked non-ignored Python owners, corrected remote-only orientation provenance labels RED-first, and removed the dead reader that bypassed D-15 validation.
  - Reconciled all focused, broad, quality/type, package, hygiene, and structural proof.
- **Remaining**:
  - Completely fresh, oblivious implementation review only.
  - Default-on/general release remains outside this story and requires separate operator approval.
- **Blockers**: none.
- **Next Steps**: Run `/openspec-story-review simple-pr-context simple-pr-context` from a completely fresh oblivious session.
- **Worktrees**: none
- **Main-tree targets**: CURe
- **Proof Statement**: Ready for review. All tasks complete. Focused prompt/runtime/flow/resume proof, 579-test amended proof plus 30 subtests, 784-test full regression, complete 18-path Ruff, scoped mypy, merge-base diff hygiene, structural/provenance/sole-validator scans, and disposable wheel/install/import smoke pass.
