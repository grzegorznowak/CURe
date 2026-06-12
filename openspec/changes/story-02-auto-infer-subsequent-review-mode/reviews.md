# Reviews: story-02-auto-infer-subsequent-review-mode

> Implementation review artifact migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite.
> Canonical story contract: `story.md`. Legacy source remains under `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`.

## Review Log

- 2026-06-12T10:44:57Z Review run after FB-026 footer-marker implementation
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Plan lane: `🟢 PLAN APPROVED` unchanged
  - Files reviewed: PR-head worktree `cure_subsequent_review/prior_corpus.py`; `cure_subsequent_review/decision.py`; `cure_subsequent_review/github_history.py`; focused subsequent-review decision/prior-corpus/PR-flow/reconciliation tests; Story 02 and MASTER coordination docs.
  - Checks run: `python -m pytest tests/_subsequent_review_unit_decision_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py -q` ✅ (10 passed, 8 subtests); focused Story 02 split suites ✅ (46 passed, 14 subtests); `python -m pytest tests/test_subsequent_review.py -q` ✅ (103 passed, 29 subtests); review-comment-with-footer direct probe ✅; `ruff check . && mypy && git diff --check` ✅.
  - Broad-suite caveat: `python -m pytest tests/test_reviewflow_unittest.py -q` ❌ with only `BaselineSelectionTests.test_pr_flow_picker_abort_leaves_no_created_session`; the same test fails isolated. Disposition: non-blocking for FB-026 because the working diff touches only subsequent-review prior-corpus/tests, `git diff --quiet -- cure.py tests/_reviewflow_unittest_grounding_impl.py tests/test_reviewflow_unittest.py` is clean, and the failure exercises picker-abort sandbox cleanup (`tests/_reviewflow_unittest_grounding_impl.py:3682` / `_maybe_apply_pr_llm_picker`) rather than the footer marker predicate or decision/corpus path.
  - Acceptance review: official CURe footer blocks in issue comments and pull review bodies now enable auto decision and enter prior corpus regardless of author; generic/body-only CURe-looking text, spoofed or allowlisted authors without the footer, thread metadata, and review-comment line comments remain non-positive/non-corpus. Decision and corpus behavior stay consistent through the shared `_looks_cure_authored` predicate.
  - Finding closure: FB-026 closed; no new material findings. Remaining picker-abort cleanup failure should be handled by Story 04/runtime coordination or a separate reviewflow maintenance pass.
  - Debt Friction: none for Story 02/FB-026.

- 2026-06-12T10:25:00Z Review-readiness checkpoint after `/epic-story-resume`
  - Decision: implementation ready for fresh story review with one broad-suite caveat
  - Approval gate: not run in this pass
  - Status transition: `✅ DONE` -> `🔄 IN PROGRESS` -> `🟣 IN REVIEW`
  - Plan lane: `🟢 PLAN APPROVED` unchanged
  - Files changed: `cure_subsequent_review/prior_corpus.py`; focused subsequent-review decision/corpus/reconciliation/PR-flow tests.
  - Checks: red-first focused decision/corpus tests failed before implementation as expected; focused Story 02 split suites ✅; public subsequent-review wrapper ✅; `ruff check .` ✅; `mypy` ✅; `git diff --check` ✅; broad `tests/test_reviewflow_unittest.py` has one unrelated picker-abort cleanup failure on the current Story 04 PR-head worktree.
  - Next action: run `/epic-story-review cure-subsequent-pr-review 02` after deciding whether the broad reviewflow cleanup failure should be handled in Story 04/another follow-up or waived for FB-026 review.

- 2026-06-12T09:39:53Z Manual operator feedback absorbed by `/epic-feedback`
  - Source: manual:2026-06-12T09:39:53Z:1; sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-083747-6b5c`
  - Feedback ID: FB-026
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Plan lane transition: 🟢 PLAN APPROVED -> 🟠 PLAN CHANGES REQUESTED
  - Epic contract drift: present; current Story 02/Story 01 marker contract still requires trusted CURe authorship plus CURe-looking body, but the operator decision now requires official CURe footer-only remote prior-review detection/ingestion regardless of author.
  - Status transition: `✅ DONE` -> `✅ DONE` (`/epic-feedback` does not transition implementation status)
  - Sections reviewed: Scope, Scenarios / Behavior Examples, Acceptance A2/A3/A13/A14, Critical Files, Implementation Notes, Locked Decisions, Review Log.
  - Original intent checked: Story 02 auto-infer remote marker policy, prior FB-002/FB-012/FB-015 false-positive and spoofing constraints, Story 01 prior corpus remote-ingestion boundary, operator decision from PR #22 sandbox 20260612-083747-6b5c.
  - Traceability: forward gaps; backward complete
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `projects/CURe/cure_subsequent_review/decision.py` (`remote_cure_markers`, `_is_positive_remote_marker`), `projects/CURe/cure_subsequent_review/prior_corpus.py` (`_looks_cure_authored`, remote corpus entry admission), `projects/CURe/cure_subsequent_review/github_history.py` (issue comment / review body event normalization), `projects/CURe/tests/_subsequent_review_unit_decision_unittest.py`, `projects/CURe/tests/_subsequent_review_unit_prior_corpus_unittest.py`.
  - Risk / miss category: remote marker policy/cross-module consistency
  - Risk lenses reviewed: false-negative prior-review detection, decision/corpus consistency, external GitHub discussion boundary, security/spoofing guardrail preservation.
  - Finding closure required: update the plan contract and then resume Story 02 with red-first regressions proving official footer blocks such as `<!-- CURE_REVIEW_FOOTER_START -->...<!-- CURE_REVIEW_FOOTER_END -->` enable remote prior-CURe detection and corpus ingestion regardless of author, while generic CURe-looking body text without the official footer remains insufficient.
  - Evidence quality: confirmed decision artifact in the cited sandbox has `enabled=false`, `remote_events=6`, `remote_cure_markers=0`, and `no_prior_review_signals`; confirmed current code shares `_looks_cure_authored` between decision and prior corpus; inferred the PR #22 owner-authored earlier review comment contained the official footer from operator report; unknown exact GitHub source id for that earlier comment in this absorption pass; provisional exact footer helper/test names.
  - Files reviewed: `MASTER.md`; this story; sandbox `work/subsequent/decision.json`; source/test paths listed above.
  - Hypothesis triage:
    - suspicious surface: shared remote CURe marker predicate; tentative issue: author allowlisting causes false negatives when CURe publishes through the operator/owner account; next proof target: decision and prior-corpus tests with owner-authored issue comment / pull review body containing the official CURe footer.
    - suspicious surface: body marker looseness after weakening authorship; tentative issue: replacing allowlisted authorship with broad CURe text could re-open FB-002/FB-015 spoofing; next proof target: tests showing `CURe Review` / `<!-- cure -->` / generic generated-looking text without the official footer remains `remote_cure_markers=0` and excluded from corpus.
  - Key findings:
    - Remote prior-CURe review detection/ingestion misses real CURe reviews posted through the operator account because the current shared predicate requires trusted/allowlisted CURe authorship in addition to a CURe-looking body. Sources: sandbox `work/subsequent/decision.json` (`remote_events=6`, `remote_cure_markers=0`, `no_prior_review_signals`), operator report for the earlier PR #22 owner-authored issue comment with official CURe footer, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`.

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** CURe may post reviews via the operator/owner account, so author allowlists can make subsequent runs look like first runs and skip prior-review intake despite official CURe footer provenance.

      **Assumptions / Preconditions:** The PR has no local completed sessions visible to the sandbox, and the only remote prior CURe artifact is an issue comment or pull review body authored by a non-allowlisted human/operator account but containing the official CURe review footer block.

      **Downgrade Factors:** Generic body-only CURe-looking text must remain insufficient, and review-comment line comments should remain outside the positive prior-review/corpus path unless the amended plan explicitly widens event kinds.

      **Code Trail:** `decision.py` counts positive remote markers through `_looks_cure_authored`; `prior_corpus.py` uses the same helper for remote corpus admission. That helper currently combines allowlisted author login with CURe-looking body text, so official footer evidence from `grzegorznowak` is ignored.

      **Reproduction:** Use a complete remote discussion fixture with no local sessions and one issue comment by `grzegorznowak` containing `<!-- CURE_REVIEW_FOOTER_START -->` / `<!-- CURE_REVIEW_FOOTER_END -->`; the current decision path can record `remote_cure_markers=0`, `enabled=false`, and `no_prior_review_signals` instead of enabling intake and admitting the comment to the prior corpus.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-plan-resume cure-subsequent-pr-review 02` to blend the footer-only marker policy through the Story 02 contract/proof sections, then run `/epic-story-plan-review cure-subsequent-pr-review 02` before implementation resume.

- 2026-06-07T08:05:15Z Review run after TAP quality-lens contract approval
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, focused `tests/_subsequent_review_*_unittest.py` suites, `projects/CURe/tests/test_subsequent_review.py`, Story 02 and MASTER coordination docs.
  - Checks run: `python -m pytest tests/test_subsequent_review.py -q` ✅ (49 tests, 13 subtests); `python -m pytest tests/_subsequent_review_unit_contracts_cli_unittest.py tests/_subsequent_review_unit_decision_unittest.py tests/_subsequent_review_unit_github_history_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` ✅ (35 tests, 13 subtests); `python -m pytest tests/test_reviewflow_unittest.py -q` ✅ (442 tests, 14 subtests); `ruff check . && mypy && git diff --check` ✅.
  - Test Architecture Plan alignment: TAP-01 through TAP-07 remain represented by the split/public suites; parser/catalog proof covers default `auto`, explicit disabled, obsolete force flag rejection, and exact `trusted|untrusted`; decision/GitHub/corpus proofs cover local, trusted remote, no-marker, true degraded, metadata-only degraded, review-comment, spoofed-author, and body-only false-positive boundaries; control-plane/PR-flow proofs cover decision/meta/artifact visibility, historical exits, enabled-only intake, and post-init error persistence.
  - Risk lenses reviewed: command routing/backwards compatibility; state/artifact ambiguity; external-service incomplete data; false-positive/trusted remote marker boundary; evidence-policy confusion; resource lifecycle/fail-open persistence; large-file/DDD extraction. Dirty product worktree and preserved untracked SVG were noted as operational risks, not blockers.
  - Acceptance review: amended A4/A14 degraded-boundary wording matches implementation (`discussion_incomplete` / `thread_state_unavailable` metadata-only probes can auto-disable with degraded reasons; true unavailable/failing probes remain degraded-enabled); A13 false-positive marker boundaries remain enforced; A15 post-`SessionProgress.init` failure injection remains covered; historical `--if-reviewed` exits remain no-new-sandbox/no-artifact paths; disabled and auto-disabled new-sandbox runs write decision metadata.
  - Finding closure: prior FB-002, FB-003, FB-012, and FB-015 remain closed under the approved TAP contract; no new material findings.
  - Debt Friction: none.

- 2026-06-04T12:16:23Z Review run by fresh maintainer session
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/cure_commands.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/tests/test_subsequent_review.py`, Story 02 and MASTER coordination docs.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (14 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings observed); `ruff check . && mypy` ✅. A focused ChunkHound `code_research` attempt timed out, so review used direct reads/diffs plus targeted runtime probes.
  - Risk lenses reviewed: command routing/backwards compatibility, state/artifact ambiguity, external service/incomplete data, false positives, evidence-policy confusion, and large-file coupling.
  - Acceptance review: A1-A12 verified by code inspection, committed focused tests, command help/catalog inspection, and targeted runtime probes for remote-marker and degraded-auto enabled decisions. Default mode is `auto`; `--no-subsequent-review` is explicit disabled; `--subsequent-review` is hidden from help as a force flag and rejected with migration guidance; evidence policy remains exactly `trusted|untrusted`; historical list/latest/prompt-selected exits remain before sandbox/artifact creation; all new-sandbox decisions persist `work/subsequent/decision.json` and `meta.json.subsequent_review`, with Story 01 intake called only for enabled decisions.
  - Finding closure: no prior implementation-review findings for Story 02; no new material findings.
  - Debt Friction: none.

- 2026-06-04T13:12:11Z Review feedback absorbed from PR
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac/review.md`
  - Feedback ID: FB-002
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `✅ DONE`
  - Sections reviewed: Acceptance A2/A3/A4, Input Boundary Shape Risk, Fail-open Checks
  - Original intent checked: FB-001 command-state decision, Story 02 Scope and Acceptance, PR #22 latest review
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/github_history.py`
  - Risk / miss category: security/semantic invariant naming
  - Risk lenses reviewed: false positives, external-service incomplete data, evidence-policy confusion
  - Finding closure required: resume Story 02; add regression proof that generic human discussion or missing thread-state metadata cannot count as CURe prior-review evidence, while unavailable/incomplete probes remain explicit degraded-enabled uncertainty.
  - Evidence quality: confirmed PR review finding; inferred direct Story 02 auto-signal boundary; unknown exact production remote payload prevalence; provisional source line anchors from review output.
  - Files reviewed: sandbox `review.md`; Story 02 spec; PR review cited source paths
  - Hypothesis triage:
    - suspicious surface: remote PR discussion marker detection; tentative issue: untrusted/generic discussion can enable auto intake as if it were prior CURe review evidence; next proof target: decision-service marker tests and corpus authorship checks
  - Key findings:
    - Auto mode can enable subsequent-review intake from ordinary GitHub discussion that is not proven to be a prior CURe review. Sources: sandbox `review.md` In Scope Issues citing `cure_subsequent_review/prior_corpus.py:19`, `cure_subsequent_review/decision.py:137`, `cure_subsequent_review/decision.py:144`, `cure_subsequent_review/github_history.py:38`, `cure_subsequent_review/github_history.py:104`, `cure_subsequent_review/decision.py:153`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A first-run PR can appear subsequent because a human writes CURe-looking text or a review-comment payload lacks trusted thread-state shape, causing behavior and artifacts to change without proof of prior CURe review history.

      **Assumptions / Preconditions:** No local completed CURe sessions exist, and the remote probe returns a human-authored CURe-looking body or a review-comment payload without expected thread-state metadata.

      **Downgrade Factors:** Impact is lower if production CURe comments always come from trusted bot accounts and operators intentionally accept degraded-enabled behavior for incomplete remote probes.

      **Code Trail:** Review output traces body/author heuristics into decision signal counts and enabled decisions; Story 02 intended generic comments not to enable auto mode.

      **Reproduction:** First-run PR with no local sessions plus a human issue comment containing `CURe review` or review-comment payload without thread-state fields can produce positive/degraded remote signals and enable intake.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 02`

- 2026-06-04T13:12:11Z Review feedback absorbed from PR
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac/review.md`
  - Feedback ID: FB-003
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: not_assessed
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `✅ DONE`
  - Sections reviewed: runtime integration, metadata/artifacts persistence, fail-open checks
  - Original intent checked: Story 02 new-sandbox decision persistence and branch-safe runtime placement
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure.py`, `projects/CURe/meta.py`, `projects/CURe/cure_subsequent_review/decision.py`
  - Risk / miss category: persistence/resource lifecycle
  - Risk lenses reviewed: state/artifact ambiguity, resource lifecycle, fail-open persistence
  - Finding closure required: resume Story 02; move or guard decision/intake preflight so exceptions after session init mark `meta.json.status = error` instead of leaving `running`.
  - Evidence quality: confirmed PR review finding; inferred lifecycle boundary from cited code trail; unknown exact filesystem failure likelihood; provisional no local reproduction run.
  - Files reviewed: sandbox `review.md`; Story 02 spec; PR review cited source paths
  - Hypothesis triage:
    - suspicious surface: new decision/intake preflight before broad guarded review flow; tentative issue: write/fetch exception exits after `progress.init()` without `progress.error(...)`; next proof target: failure-injection test around `decision.json`/intake artifact write
  - Key findings:
    - Failures in the new decision/intake preflight can leave a new session recorded as `running` instead of `error`. Sources: sandbox `review.md` In Scope Issues citing `cure.py:2852`, `cure.py:9603`, `cure.py:9610`, `cure.py:9621`, `cure.py:9735`, `cure.py:10615`, `meta.py:82`

      <details open>
      <summary><b>Medium</b> severity · <b>Low</b> likelihood</summary>

      **Why:** Operators and status tooling can see an orphaned running session if the new preflight artifact writes or decision code fail before the existing broad exception handler updates session metadata.

      **Assumptions / Preconditions:** `decide_subsequent_review`, `write_decision_artifact`, or enabled intake raises after `ReviewProgress.init` writes `status: running` and before the main guarded review flow starts.

      **Downgrade Factors:** Filesystem failures are uncommon, and many GitHub failures are converted into degraded artifacts rather than raised.

      **Code Trail:** Review output traces session init before the new decision/intake block and the broad `progress.error(...)` handler after it.

      **Reproduction:** Force the decision artifact or subsequent intake artifact write to fail during a new PR sandbox; inspect `meta.json.status` after process exit.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 02`

- 2026-06-04T16:02:00Z Review run after FB-002/FB-003 hardening
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/tests/test_subsequent_review.py`, Story 02 and MASTER coordination docs.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (22 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `ruff check .` ✅; `mypy` ✅.
  - Risk lenses reviewed: false-positive auto-mode prior-review markers; external-service unavailable/incomplete degraded behavior; post-`SessionProgress.init` lifecycle/error persistence; command-state/evidence-policy regression.
  - Acceptance review: false-positive marker boundaries now require both CURe-like author and CURe/review body before `remote_cure_markers` increments or `cure_pr_discussion_found` appears; generic human comments, CURe-looking human text, missing author, resolved/unresolved thread metadata, and missing thread-state metadata record zero positive markers, while missing thread-state/unavailable/incomplete remote state stays degraded-enabled with reasons. Preflight failures from decision, decision artifact/meta writes, and enabled intake/artifact writes are guarded so `meta.json.status = "error"` plus `error.message` persists before re-raise. Existing default `auto`, explicit `--no-subsequent-review`, rejected force-enable, historical `--if-reviewed` branch safety, and `trusted|untrusted` evidence policy remain intact.
  - Finding closure: FB-002 closed; FB-003 closed; no new material findings.
  - Debt Friction: none.

- 2026-06-06T05:28:59Z Review feedback absorbed from sandbox 5864
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-050435-5864/review.md`
  - Feedback IDs: FB-012, FB-015
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `🔄 IN PROGRESS`
  - Sections reviewed: A2/A3/A13/A14, remote marker classifier, decision/intake consistency with Story 01 corpus scope, locked `auto|disabled` mode and `trusted|untrusted` policy.
  - Original intent checked: Story 02 auto-inference contract, prior FB-002 false-positive boundary, Story 01 FB-008 decision that review comments remain discussion metadata rather than corpus entries, sandbox 5864 review findings.
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`.
  - Risk / miss category: cross-module consistency; security/authority.
  - Risk lenses reviewed: remote marker false positives, spoofable authorship, decision/corpus consistency, external GitHub discussion boundary.
  - Finding closure required: resume Story 02 with red-first regressions ensuring `review_comment` events cannot be positive auto-enable markers while remaining excluded from prior corpus, and broad/spoofable CURe-looking login/body regex matches do not create trusted remote markers or corpus entries without configured durable CURe authorship.
  - Evidence quality: confirmed sandbox 5864 review cites concrete paths/reproductions; inferred routing to Story 02 because the primary user-visible failure is auto mode enabling from invalid remote markers; unknown final allowlist/config source for durable CURe authorship.
  - Files reviewed: sandbox `review.md`; Story 02 spec; prior Story 01 FB-008/FB-009 closure notes.
  - Hypothesis triage:
    - suspicious surface: auto-decision marker classifier; tentative issue: `review_comment` event bodies count as prior-CURe evidence although Story 01 intentionally excludes them from corpus; next proof target: decision-service test with only a CURe-looking review comment.
    - suspicious surface: `_looks_cure_authored` shared predicate; tentative issue: broad login/body regex lets `cure-fake` create positive remote markers/corpus entries; next proof target: marker/corpus tests for spoofed author and configured trusted author.
  - Key findings:
    - [FB-012] CURe-looking pull-request line comments can enable subsequent review but contribute no prior-review corpus entry. Sources: sandbox 5864 `review.md` citing `cure_subsequent_review/decision.py:137`, `github_history.py:165`, `prior_corpus.py:87`, `prior_corpus.py:93`.
    - [FB-015] CURe-authored remote discussion trust is regex-based and spoofable. Sources: sandbox 5864 `review.md` citing `cure_subsequent_review/prior_corpus.py:15`, `:16`, `:26`, `:105`.
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 02`

- 2026-06-06T05:50:08Z Review run after FB-012/FB-015 hardening
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Files reviewed: `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/tests/test_subsequent_review.py`, `projects/CURe/cure.py`, Story 02 and MASTER coordination docs.
  - Checks run: focused 10-test Story 01/02 regression slice ✅; `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (30 tests; expected gh fallback log noise); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `ruff check . && mypy && git diff --check` ✅.
  - Risk lenses reviewed: FB-012 review-comment line comment marker/corpus boundary; FB-015 spoofed CURe-looking login/body trust boundary; default `auto` / explicit `disabled` command surface; degraded remote uncertainty; generic/body-only/missing-author/thread metadata marker negatives; exact `trusted|untrusted` evidence policy; Story 01 FB-013/014/016 parser/session/reconciliation regressions.
  - Acceptance review: `review_comment` events remain normalized discussion metadata but are excluded from positive auto markers and remote prior corpus; complete trusted-author line-comment-only probes auto-disable with `remote_cure_markers=0` and no `cure_pr_discussion_found`. Trusted remote markers and corpus entries now require exact durable CURe author allowlist plus CURe/review body marker for issue comments or pull reviews, blocking `cure-fake` and body-only spoofing while preserving `cure-bot` issue comment / pull review behavior. Unavailable/incomplete remote probes remain degraded-enabled uncertainty; command mode and evidence-policy surfaces are unchanged; Story 01 FB-013/014/016 regression tests still pass.
  - Finding closure: FB-012 closed; FB-015 closed; no new material findings.
  - Debt Friction: none.
