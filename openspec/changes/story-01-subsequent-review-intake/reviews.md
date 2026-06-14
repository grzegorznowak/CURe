# Reviews: story-01-subsequent-review-intake

> Implementation review artifact migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite.
> Canonical story contract: `story.md`. Legacy source remains under `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`.

## Review Log

- 2026-06-04T10:17:19Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Status transition: `🟣 IN REVIEW` -> `🔄 IN PROGRESS`
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/pyproject.toml`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/tests/test_subsequent_review.py`, `projects/CURe/tests/fixtures/subsequent_review/simulation_raw.json`, `projects/CURe/docs/examples/subsequent-review-simulation.md`, coordination MASTER/story files.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅; `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings observed); `ruff check .` ✅; `mypy` ✅. ChunkHound daemon was query-ready but degraded; `code_research` attempt timed out, so review proceeded with direct targeted reads/rg.
  - Risk lenses reviewed: GitHub external I/O/degraded paths, parsing/malformed input, module lifecycle/toggles, branch compatibility, filesystem artifact placement, packaging/typecheck visibility, naming-sensitive enums/fixtures, Story 02/03 semantic bleed.
  - Story 02/03 boundary: no material implementation of source verification, discussion authority/disposition, prompt packaging, report governor, memory reuse, or full landmark trace found. Contract enum names for later modules exist as required, with later modules manifest-disabled.
  - Key findings:
    - [request_changes] [A7/A11/A14; parsing + naming-sensitive fixtures] The extractor and fixture do not actually prove or support the simulation-derived prior CURe review artifact shape. `projects/CURe/docs/examples/subsequent-review-simulation.md:160-184` and `:191-216` define prior review A/B findings as bullet items like `- [A-01][Medium] ...` with indented `Evidence:` lines, but `projects/CURe/cure_subsequent_review/prior_findings.py:18` only recognizes heading-style IDs (`### A-01: ...`) and `_extract_from_entry()` only starts candidates on those headings (`prior_findings.py:107-119`). A direct probe over the simulation bullet shape produced `finding_count=0` with `parse_degraded`, so Story 01 would write no canonical candidates for its own landmark prior reviews. The committed fixture under `projects/CURe/tests/fixtures/subsequent_review/simulation_raw.json:3-45` contains only compact ID/title/path summaries and degraded-path names, not raw review markdown/comments/source facts or executable degraded inputs, so A11's deterministic raw A/B/C/S fixture coverage is not met.
    - [request_changes] [A3/A4; GitHub external I/O/degraded paths] The enabled runtime discussion fetch can silently mark a paginated public-fallback response complete. `_pr_flow_impl` passes `allow_public_fallback=True` into `gh_api_list` for all discussion endpoints (`projects/CURe/cure.py:9581-9587`). On auth fallback, `gh_api_list()` returns `_github_public_api_list()` (`cure.py:7451-7459`), which performs a single public API request and returns a bare list without pagination/link completeness metadata (`cure.py:7423-7428`). `collect_pr_discussion()` treats any bare list as complete (`projects/CURe/cure_subsequent_review/github_history.py:24-33`). For PRs with more comments/reviews than the first public page, this violates A4's requirement to record `discussion_incomplete` instead of treating missing discussion as complete.
  - Positive notes: package inclusion and plain mypy scope are present in `pyproject.toml`; historical `--if-reviewed list/latest/prompt` exits remain before sandbox/intake by code inspection, and `new`/non-interactive fallback integration is after `work_dir`/`pr_context` creation; disabled top-level mode creates no `work/subsequent` directory.
  - Finding closure: none closed; two material findings open.
  - Debt Friction: none.
  - Next action: resume implementation to (1) add raw simulation-derived fixture files/goldens and teach/test the extractor against the `[A-01][Medium]` CURe markdown shape while preserving parse-degraded partial recovery, and (2) make list-endpoint public fallback either fully paginate with completeness markers or degrade/disable fallback rather than reporting bare-list success.

- 2026-06-04T10:28:42Z Review run by fresh maintainer session after corrective resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/pyproject.toml`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/tests/test_subsequent_review.py`, `projects/CURe/tests/fixtures/subsequent_review/simulation_raw.json`, coordination MASTER/story files.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (9 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings observed); `ruff check .` ✅; `mypy` ✅; temporary-venv package install/import smoke ✅. ChunkHound daemon query-ready but realtime indexing degraded; ChunkHound search plus direct targeted reads/rg were used.
  - Risk lenses reviewed: Story 01 A1-A19 acceptance, GitHub external I/O/degraded paths, parser/malformed input, module lifecycle/toggles, branch compatibility, filesystem artifact placement, packaging/typecheck visibility, naming-sensitive enum/fixture invariants, and Story 02/03 semantic bleed.
  - Prior finding closure:
    - Closed [A7/A11/A14]: raw simulation fixture now includes A-01..A-05/B-01..B-06 bullet prior-review markdown, C-01..C-10 discussion, S-01..S-08 source facts, degraded inputs, and `test_simulation_bullet_prior_reviews_extract_and_degrade_partially` proves bullet parsing plus parse-degraded partial recovery.
    - Closed [A3/A4]: `gh_api_list` public fallback now returns `{items, complete: false, status: discussion_incomplete, detail: ...}` and `test_public_fallback_list_payload_marks_discussion_incomplete` proves unauthenticated single-page public fallback is degraded rather than silently complete.
  - New findings: none material. Story 01 remains intake/ledger only; no source-state/disposition/suppression/prompt-packaging/report-governor/memory-reuse semantics found beyond contract enum names for later modules.
  - Debt Friction: none.
  - Next action: proceed to dependent Story 02 when ready.

- 2026-06-04T13:12:11Z Review feedback absorbed from PR
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac/review.md`
  - Feedback ID: FB-004
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `✅ DONE`
  - Sections reviewed: Acceptance A8, Finding Reconciler scope, Input Boundary Shape Risk
  - Original intent checked: Story 01 finding reconciliation ledger requirements and PR #22 latest review
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`
  - Risk / miss category: persistence
  - Risk lenses reviewed: finding identity, provenance preservation, supersedes chains
  - Finding closure required: resume Story 01; add regression proof that reconciliation preserves all provenance for duplicate local IDs and handles chained supersedes without splitting origin graph.
  - Evidence quality: confirmed PR review finding; inferred direct A8 gap; unknown exact frequency of duplicate IDs in real histories; provisional source line anchors from review output.
  - Files reviewed: sandbox `review.md`; Story 01 spec; PR review cited source paths
  - Hypothesis triage:
    - suspicious surface: reconciler identity maps keyed by display ID; tentative issue: duplicate local IDs or transitive supersedes can drop provenance or split groups; next proof target: `reconcile_findings` unit fixtures with duplicate `A-01` and `CURE-03 -> CURE-02 -> CURE-01` chains
  - Key findings:
    - Reconciliation does not retain the full prior-finding origin graph and can split chained supersedes relationships. Sources: sandbox `review.md` Technical In Scope Issues citing `cure_subsequent_review/prior_corpus.py:36`, `cure_subsequent_review/prior_corpus.py:65`, `cure_subsequent_review/prior_findings.py:34`, `cure_subsequent_review/finding_identity.py:35`, `cure_subsequent_review/finding_identity.py:49`, `cure_subsequent_review/finding_identity.py:64`, `cure.py:13457`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** The ledger is meant to make prior findings auditable. Dropping duplicate provenance or splitting supersedes chains can make stale findings appear unrelated or lose their historical source.

      **Assumptions / Preconditions:** The same display finding ID appears from multiple corpus sources, or completed sessions arrive newest-first with a supersedes chain.

      **Downgrade Factors:** Impact is lower if finding IDs are globally unique and supersedes links remain one-hop only.

      **Code Trail:** Review output traces corpus entries to single-provenance candidates and reconciliation maps/deduplication keyed by display `finding_id`.

      **Reproduction:** Feed duplicate `A-01` candidates plus `B-01 Supersedes: A-01`, or a `CURE-03 -> CURE-02 -> CURE-01` chain with title drift; inspect group membership/provenance.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01`

- 2026-06-04T13:12:11Z Review feedback absorbed from PR
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac/work/subsequent/pr_discussion.json`
  - Feedback ID: FB-005
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `✅ DONE`
  - Sections reviewed: Acceptance A3/A4, PR History Collector scope, Input Boundary Shape Risk, Fail-open Checks
  - Original intent checked: Story 01 degraded discussion requirements and latest local PR #22 sandbox artifacts
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure.py` GitHub list helper, `projects/CURe/cure_subsequent_review/github_history.py`, sandbox `pr_discussion.json`
  - Risk / miss category: platform/API failure
  - Risk lenses reviewed: external GitHub I/O, pagination/completeness, degraded artifact quality
  - Finding closure required: resume Story 01; harden list collection/fallback around `gh api --paginate --slurp` failures and preserve enough failure cause to distinguish compatibility/auth/transport problems.
  - Evidence quality: confirmed sandbox artifact status and command details; inferred `gh --slurp` compatibility/failure mode from artifact detail and prior review; unknown stderr because artifact omits it; provisional exact fallback fix.
  - Files reviewed: sandbox `work/subsequent/pr_discussion.json`; Story 01 spec; PR review cited source paths
  - Hypothesis triage:
    - suspicious surface: GitHub list endpoint collection; tentative issue: all remote discussion endpoints degrade to unavailable due CLI command failure; next proof target: tests for non-auth `gh api --paginate --slurp` failure and fallback/degraded detail preservation
  - Key findings:
    - GitHub discussion capture degraded completely in the latest PR #22 run, leaving zero issue comments, reviews, or review comments. Sources: `work/subsequent/pr_discussion.json` has `status: degraded`, `status_reasons: ["discussion_unavailable"]`, `events: []`, and pagination failures for issue comments, reviews, and review comments via `gh api --hostname github.com ... --paginate --slurp`.

      <details open>
      <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** Story 01 is supposed to preserve PR discussion history with completeness/degraded markers. This run correctly marks degradation but functionally captures no remote evidence, so later modules have no PR-comment corpus to consume.

      **Assumptions / Preconditions:** The operator environment's `gh api --paginate --slurp` call fails for compatibility or non-auth transport reasons, and recoverable public/list fallback is not used.

      **Downgrade Factors:** The artifact is degraded rather than falsely successful; local session corpus still exists.

      **Code Trail:** The artifact records each endpoint command failure and no normalized events; prior review output ties this path to `gh_api_list`/collector behavior.

      **Reproduction:** Run enabled/auto subsequent review in an environment where `gh api --paginate --slurp` fails; inspect `work/subsequent/pr_discussion.json` for three unavailable endpoints and empty events.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01`

- 2026-06-04T13:12:11Z Review feedback absorbed from PR
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac/work/subsequent/prior_findings.json`
  - Feedback ID: FB-006
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `✅ DONE`
  - Sections reviewed: Acceptance A7/A14, Prior Finding Extractor scope, Verification fixture/proof rows
  - Original intent checked: Story 01 prior-finding extraction requirements and latest local PR #22 sandbox artifacts
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure_subsequent_review/prior_findings.py`, sandbox `prior_review_corpus.json`, sandbox `prior_findings.json`, prior local `review.md` artifacts
  - Risk / miss category: behavior-vs-mechanics proof
  - Risk lenses reviewed: parser/malformed input, real generated artifact shape, product-value proof
  - Finding closure required: resume Story 01; teach extraction to handle CURe's actual generated human-review issue format or emit a machine-readable finding ledger for future runs, with regression coverage over real generated `review.md` samples.
  - Evidence quality: confirmed zero extracted findings and per-artifact parse degradation; confirmed prior corpus captured two real review bodies with visible findings; inferred current parser contract mismatch; unknown desired canonical schema for future generated ledgers.
  - Files reviewed: sandbox `work/subsequent/prior_review_corpus.json`; sandbox `work/subsequent/prior_findings.json`; prior session `review.md` files; `projects/CURe/cure_subsequent_review/prior_findings.py`
  - Hypothesis triage:
    - suspicious surface: prior-finding parser accepts canonical fixture markdown but not CURe's actual final review issue format; tentative issue: subsequent-review memory is mechanically present but semantically empty; next proof target: extractor tests using `review.md` details-summary findings from completed CURe sessions
  - Key findings:
    - Real CURe prior review reports produced zero prior-finding candidates in the latest PR #22 run. Sources: `work/subsequent/prior_findings.json` has `status: degraded`, `status_reasons: ["parse_degraded"]`, `findings: []`, and `finding_id_without_parseable_heading` for both local prior session entries; `prior_review_corpus.json` contains two `session_review` bodies with clear findings.

      <details open>
      <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** The core product value of Story 01 is a usable prior-finding ledger. If normal CURe-generated `review.md` files are captured but yield no candidates, subsequent reviews are prior-review-aware in mechanics only, not in behavior.

      **Assumptions / Preconditions:** Prior reviews use CURe's generated human-review format with bullet finding text and `<details><summary><b>Severity</b>...` blocks rather than canonical `### CURE-01`/`- [A-01][Medium]` plus `Severity:` fields.

      **Downgrade Factors:** The extractor correctly reports `parse_degraded` rather than success-empty, and the current strict parser behaves as coded.

      **Code Trail:** `prior_findings.py` recognizes canonical headings/bullets and field labels; the sandbox corpus bodies are ordinary CURe final reviews whose finding headings do not match that strict shape.

      **Reproduction:** Feed the two captured prior session `review.md` bodies from the sandbox corpus into `extract_prior_findings`; inspect the empty findings and per-artifact degraded statuses.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01`

- 2026-06-04T15:38:00Z Review run by fresh maintainer session after FB-004/FB-005/FB-006 hardening resume
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Status transition: `🟣 IN REVIEW` -> `🔄 IN PROGRESS`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: S19-S21, A20-A22, FB-004/FB-005/FB-006 risk lenses, implementation diff, focused tests.
  - Original intent checked: re-approved Story 01 plan, `plan-research-cure-subsequent-pr-review-01`, `cure-pr22-local-run-analysis`, Story 01 implementation notes, direct code/tests.
  - Traceability: FB-004 appears closed; FB-006 appears closed; FB-005 remains partially open because cause taxonomy is not reliable.
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/tests/test_subsequent_review.py`, prior sandbox `prior_review_corpus.json`.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (17 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `ruff check .` ✅; `mypy` ✅; ad-hoc classifier probe ❌ showed HTTP/rate-limit/transport stderr all classified as `cli_unsupported_flag`.
  - Risk lenses reviewed: FB-004 finding identity/provenance graph preservation; FB-005 GitHub CLI/API compatibility and degraded cause quality; FB-006 generated prior-review parser compatibility; Story 02/03 semantic boundary.
  - Finding closure:
    - Closed [FB-004/A20]: reconciler now keys ordinary duplicate local display IDs by `corpus_entry_id:finding_id`, serializes `local_findings`, `supersedes_edges`, and `ambiguous_supersedes`, and tests cover duplicate IDs, ambiguous target markers, and a transitive `CURE-03 -> CURE-02` edge without provenance overwrite.
    - Closed [FB-006/A22]: extractor now parses actual CURe generated `### In Scope Issues` bullet + `<summary><b>Severity</b> severity` reports; direct probe over PR #22 prior corpus now emits non-empty findings, and unsupported generated reports degrade with `generated_review_without_parseable_findings`.
    - Open [FB-005/A21]: cause taxonomy records stderr/stdout/exit/endpoint, but the classifier includes the command string in its pattern search and treats the mere presence of `--slurp` in `gh api --paginate --slurp` as a CLI-flag incompatibility.
  - Key findings:
    - [request_changes] [FB-005 / A21 / GitHub list failure taxonomy] `cure.py:_classify_gh_list_error()` and `cure_subsequent_review.github_history:_classify_fetch_error()` classify any `ReviewflowSubprocessError` whose command includes `--slurp` as `cli_unsupported_flag`, because both search `str(error)`/`str(exc)` and `ReviewflowSubprocessError.__str__` is `Command failed (...): gh api ... --paginate --slurp`. An ad-hoc probe with stderr values `HTTP 500 Internal Server Error`, `API rate limit exceeded`, and `connection timed out` all returned `cli_unsupported_flag` instead of `api_status`, `api_rate_limit`, or `transport`. This violates A21/D15's requirement to preserve a useful auth/transport/CLI-flag/API cause taxonomy and can send operators toward the wrong remediation while artifacts appear fully cause-classified. Sources: `projects/CURe/cure.py:7445-7454`, `projects/CURe/cure.py:7515-7522`, `projects/CURe/cure_subsequent_review/github_history.py:17-29`, `projects/CURe/run.py:14-29`.
  - Positive notes: focused and regression suites pass; no Story 02/03 source-resolution, authority/disposition, suppression, prompt-packaging, report-governor, or memory-reuse behavior was added beyond existing disabled contracts.
  - Debt Friction: none.
  - Next action: resume implementation to make taxonomy inspect stderr/stdout/error message without treating the expected command flag itself as an unsupported-flag signal; add tests for non-auth API status/rate-limit/transport failures plus the existing true `unknown flag: --slurp` case.

- 2026-06-04T15:45:39Z Review run by fresh maintainer session after FB-005/A21 corrective resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: S19-S21, A20-A22, FB-004/FB-005/FB-006 risk lenses, implementation diff, focused regression tests, Story 02/03 semantic boundary.
  - Original intent checked: re-approved Story 01 plan, `research-cure-subsequent-pr-review-01`, `babysit-cure-subsequent-pr-review-01`, `plan-research-cure-subsequent-pr-review-01`, `cure-pr22-local-run-analysis`, direct code/tests.
  - Traceability: FB-004 closed; FB-005 closed after A21 cause-taxonomy correction; FB-006 closed.
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/tests/test_subsequent_review.py`, coordination MASTER/story files.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review.SubsequentReviewTests.test_github_list_slurp_command_does_not_mask_api_rate_or_transport_failures tests.test_subsequent_review.SubsequentReviewTests.test_github_list_slurp_failure_public_fallback_preserves_cause_detail` ✅; `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (18 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `ruff check .` ✅; `mypy` ✅; ad-hoc classifier probe ✅ for HTTP status, rate-limit, transport, true `unknown flag: --slurp`, and `invalid option: --slurp` cases.
  - Risk lenses reviewed: FB-004 finding identity/provenance graph preservation; FB-005 GitHub CLI/API compatibility and degraded cause quality; FB-006 generated prior-review parser compatibility; Story 02/03 semantic boundary; preserved untracked `docs/examples/subsequent-pr-run-flow.svg`.
  - Finding closure:
    - Closed [FB-004/A20]: prior closure still holds; ledger preserves duplicate local display IDs by origin, ambiguity markers, transitive supersedes edges, local findings, and provenance with regression coverage.
    - Closed [FB-005/A21]: classifiers now build taxonomy from stderr/stdout instead of `ReviewflowSubprocessError.__str__`; expected command text containing `--slurp` no longer masks API status/rate-limit/transport causes, while stderr/stdout with true `unknown flag`/`invalid option` remains `cli_unsupported_flag`.
    - Closed [FB-006/A22]: prior closure still holds; generated CURe `### In Scope Issues` review markdown produces non-empty extracted candidates, and unsupported generated-review formats degrade explicitly rather than silently emptying memory.
  - Key findings: none material.
  - Positive notes: no Story 02/03 source-resolution, authority/disposition, suppression, prompt-packaging, report-governor, or memory-reuse behavior was added beyond existing disabled contract enum/status records; evidence policy remains `trusted`/`untrusted` only.
  - Debt Friction: none.
  - Next action: Story 01 implementation can be finalized/committed; preserve pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` unless intentionally bundling that separate epic artifact.

- 2026-06-05T16:04:44Z Review run by fresh maintainer session after FB-008/A13 hardening resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: A13, FB-008/A13, FB-002 authorship/thread-metadata invariant, PR History Collector/Prior Review Corpus Builder/Prior Finding Extractor cross-module flow, implementation diff, focused and regression tests.
  - Original intent checked: PR #22 local review f750 finding, Story 01 A13 scope, direct code/tests in `prior_corpus.py`, `decision.py`, `github_history.py`, `prior_findings.py`, and `tests/test_subsequent_review.py`.
  - Traceability: FB-008 closed; trusted pull review bodies counted by auto decision now enter the prior-review corpus and finding extractor with review provenance.
  - Files reviewed: `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/tests/test_subsequent_review.py`, coordination MASTER/story files.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review.SubsequentReviewTests.test_trusted_pull_review_body_enables_and_enters_prior_corpus tests.test_subsequent_review.SubsequentReviewTests.test_prior_corpus_rejects_untrusted_pull_review_bodies` ✅; `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (24 tests); `ruff check . && mypy` ✅; `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise).
  - Risk lenses reviewed: FB-008/A13 cross-module consistency, FB-002 body-only/missing-author trust boundary, review-comment/thread metadata exclusion from prior corpus, Story 02/03 semantic boundary, preserved untracked `docs/examples/subsequent-pr-run-flow.svg`.
  - Finding closure:
    - Closed [FB-008/A13]: `build_prior_review_corpus` now accepts `DiscussionEvent.kind == "review"` through the same `_looks_cure_authored(author, body)` predicate used by `decision.py`, writes `source_type="pr_review"` / `entry_id="pr_review:<id>"`, and preserves review ID, URL, author, submitted timestamp, and review state provenance for extraction.
    - Closed [FB-002 invariant]: human-authored or missing-author pull review bodies that only contain CURe-like body text are ignored with `cure_authorship_not_established`; body text alone remains insufficient.
    - Closed [review-comment exclusion]: `review_comment`/thread events are still normalized as discussion metadata by `github_history.py` but are not in `remote_corpus_sources`, so review-comment bodies do not become prior-review corpus entries.
  - Key findings: none material.
  - Positive notes: no Story 02/03 source-resolution, authority/disposition, suppression, prompt-packaging, report-governor, or memory-reuse behavior was added; evidence policy remains `trusted`/`untrusted` only.
  - Debt Friction: none.
  - Next action: Story 01 FB-008/A13 can be finalized/committed; preserve pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` unless intentionally bundling that separate epic artifact.

- 2026-06-05T16:27:17Z Review run by fresh maintainer child after FB-009 status-semantics hardening resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: A6/A13, FB-009 status semantics, FB-008 pull-review-body corpus consistency, FB-002 authorship/thread-metadata invariant, implementation diff, focused and regression tests.
  - Traceability: FB-009 closed; trusted remote-only PR comments and pull review bodies now create successful corpus/finding ledgers without stale `no_prior_reviews` degradation. 7efb finding 2 routed as FB-010 new-story candidate because it spans decision evidence and intake persistence/reuse.
  - Files reviewed: `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/tests/test_subsequent_review.py`, coordination MASTER/story files.
  - Checks run: red-first focused status tests failed before fix; focused regression after fix ✅; `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (25 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `ruff check . && mypy` ✅; review child also ran focused subsequent-review tests, focused ruff, and `mypy` ✅.
  - Risk lenses reviewed: remote-only status semantics, body-only/missing-author trust boundary, review-comment/thread metadata exclusion, Story 02/03 decision/intake evidence boundary, preserved untracked `docs/examples/subsequent-pr-run-flow.svg`.
  - Finding closure:
    - Closed [FB-009/A6/A13]: `build_prior_review_corpus` delays `no_prior_reviews` until after remote discussion processing and only emits it when both local sessions and trusted remote corpus entries are absent.
    - Closed [prior-findings propagation]: successful remote-only corpora no longer propagate `no_prior_reviews` into `prior_findings.status_reasons`, so parseable trusted remote findings produce `ModuleStatus.SUCCESS`.
    - Preserved [FB-002 invariant]: untrusted pull review bodies, missing authors, and review-comment/thread bodies remain ignored rather than becoming corpus entries.
  - Key findings: none material.
  - Positive notes: no Story 02/03 source-resolution, authority/disposition, suppression, prompt-packaging, report-governor, or memory-reuse behavior was added.
  - Debt Friction: FB-010 remains as a future story candidate for decision/intake discussion-evidence reproducibility.
  - Next action: commit/push FB-009 hardening; preserve pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` unless intentionally bundling that separate epic artifact.

- 2026-06-06T04:35:36Z Review feedback absorbed from PR
  - Source: https://github.com/grzegorznowak/CURe/pull/22#issuecomment-4621524265
  - Feedback ID: FB-011
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `✅ DONE`
  - Sections reviewed: Acceptance A5, Prior Review Corpus Builder scope, completed-session metadata/provenance intake
  - Original intent checked: Story 01 prior-session selection and corpus provenance requirements; PR #22 review feedback source
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure.py` session review path resolution, `projects/CURe/cure_subsequent_review/prior_corpus.py`, completed-session metadata handling
  - Risk / miss category: security / persistence
  - Risk lenses reviewed: persisted metadata trust boundary, local artifact containment, prior-review provenance integrity
  - Finding closure required: resume Story 01; constrain completed-session review artifact resolution to the session artifact boundary or record skipped/missing/out-of-bound artifacts as degraded provenance instead of silently trusting arbitrary paths.
  - Evidence quality: confirmed PR feedback and current Story 01 scope; confirmed code path accepts resolved session review paths for corpus intake; inferred exploitability from persisted local metadata shape; unknown intended compatibility for historical absolute paths.
  - Files reviewed: PR comment `IC_kwDORnlli88AAAABE3bdKQ`; `projects/CURe/cure.py`; `projects/CURe/cure_subsequent_review/prior_corpus.py`; Story 01 spec
  - Hypothesis triage:
    - suspicious surface: completed-session `paths.review_md` metadata; tentative issue: stale or malformed metadata can redirect prior-review loading outside the session directory or disappear before corpus degradation; next proof target: completed-session scan/corpus tests with absolute out-of-session paths and missing review artifacts
  - Key findings:
    - Historical session metadata can redirect prior-review loading outside the session artifact boundary. Sources: PR comment `IC_kwDORnlli88AAAABE3bdKQ` citing `cure.py:13291` and related session scanning/corpus paths.

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** Prior-review corpus provenance should represent completed CURe session artifacts. If persisted metadata can point to unrelated local markdown, subsequent-review memory can ingest the wrong artifact or silently omit a broken prior review before the corpus records degraded evidence.

      **Assumptions / Preconditions:** A completed session `meta.json` has an absolute or escaping `paths.review_md`, or its expected review artifact is missing.

      **Downgrade Factors:** Impact is lower if all historical sandbox metadata is fully trusted and never user-editable; current runs already preserve reviewed-head provenance for accepted session entries.

      **Code Trail:** The PR feedback traces `_resolve_session_review_md_path` / completed-session scanning to `paths.review_md` resolution and notes that the corpus builder only reports unavailable artifacts for sessions it receives.

      **Reproduction:** Create a completed session whose metadata points `paths.review_md` to an existing markdown file outside the session; then run subsequent-review intake and inspect whether the unrelated file is admitted as that session's prior review. Repeat with a missing artifact and inspect whether corpus degradation records the skipped session.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01`

- 2026-06-06T04:53:22Z Review run by fresh maintainer child after FB-011 completed-session artifact-boundary hardening resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: FB-011, A5 prior-review corpus provenance, completed-session metadata path resolution, local historical `--if-reviewed` compatibility, remote corpus/status invariants, Story 02/03 semantic boundary.
  - Original intent checked: PR feedback `IC_kwDORnlli88AAAABE3bdKQ`, `research-cure-subsequent-pr-review-01`, `babysit-cure-subsequent-pr-review-01`, Story 01 spec, direct code/tests.
  - Traceability: FB-011 closed; completed-session `paths.review_md` can no longer redirect prior-review corpus intake outside its session boundary, and missing/out-of-bound artifacts reach corpus degradation with session/path/reason provenance.
  - Files reviewed: `projects/CURe/cure.py`, `projects/CURe/cure_sessions.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/tests/test_subsequent_review.py`, coordination MASTER/story files.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review.SubsequentReviewTests.test_completed_session_artifact_boundary_and_missing_reviews_are_degraded_corpus_inputs tests.test_subsequent_review.SubsequentReviewTests.test_new_sandbox_intake_receives_unavailable_completed_sessions_for_degradation tests.test_subsequent_review.SubsequentReviewTests.test_prior_corpus_rejects_untrusted_pull_review_bodies tests.test_subsequent_review.SubsequentReviewTests.test_trusted_pull_review_body_enables_and_enters_prior_corpus` ✅; `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (27 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `ruff check . && mypy` ✅; `git diff --check` ✅.
  - Risk lenses reviewed: persisted completed-session metadata trust boundary, local artifact containment including absolute/escaping paths, prior-corpus degradation/provenance, FB-002 authorship trust boundary, FB-008/FB-009 remote corpus/status behavior, legacy historical list/latest/prompt behavior, evidence policy enum boundary, and Story 02/03 semantic bleed.
  - Finding closure:
    - Closed [FB-011]: `cure_sessions._resolve_session_review_md_candidate` resolves metadata paths through `Path.resolve()` and rejects candidates outside `session_dir.resolve()` as `review_md_outside_session`; missing in-bound review artifacts are marked `review_md_missing`.
    - Closed [degraded provenance]: `_pr_flow_impl` scans completed sessions with `include_unavailable=True` for decision/intake while filtering unavailable records out of legacy historical display/print paths; `build_prior_review_corpus` records `prior_review_artifact_unavailable` ignored-session provenance and does not read the redirected/missing artifact as corpus content.
    - Preserved [Story 01 invariants]: FB-002 body-only/missing-author trust boundary still holds; trusted pull-review/issue-comment remote corpora and remote-only success status remain intact; review comments remain discussion metadata; no source-resolution, authority/disposition, suppression, prompt-packaging, report-governor, or memory-reuse semantics were added; evidence policy remains exactly `trusted`/`untrusted`.
  - Key findings: none material.
  - Positive notes: pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` remains untracked and untouched.
  - Debt Friction: none for Story 01; FB-007 and FB-010 remain future-story candidates.
  - Next action: Story 01 can be finalized/committed; preserve pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` unless intentionally bundling that separate epic artifact.

- 2026-06-06T05:28:59Z Review feedback absorbed from sandbox 5864
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-050435-5864/review.md`
  - Feedback IDs: FB-013, FB-014, FB-016
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `🔄 IN PROGRESS`
  - Sections reviewed: A5/A7/A8/A14/A20/A22, Prior Review Corpus Builder, Prior Finding Extractor, Finding Reconciler, completed-session containment and provenance.
  - Original intent checked: Story 01 intake-only contract, prior FB-011 artifact-boundary closure, sandbox 5864 review findings.
  - Traceability: forward gaps; backward complete
  - Code surfaces searched: `projects/CURe/cure_sessions.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`.
  - Risk / miss category: parsing/malformed input; security/persistence; finding-identity/provenance.
  - Risk lenses reviewed: generated markdown input boundary, symlink/session filesystem containment, provenance graph completeness, Story 02/03 semantic boundary.
  - Finding closure required: resume Story 01 with red-first regressions for malformed sibling generated-review cards, symlinked child session directories escaping the sandbox root, and same-entry duplicate display IDs; preserve review-comment corpus exclusion and evidence policy enum.
  - Evidence quality: confirmed sandbox 5864 review cites concrete paths/reproductions; inferred Story 01 ownership from A5/A7/A8/A14/A20/A22; unknown exact production frequency of malformed generated cards and duplicate IDs.
  - Files reviewed: sandbox `review.md`; Story 01 spec; prior research/babysitter notes.
  - Hypothesis triage:
    - suspicious surface: generated-review card parser; tentative issue: parseable siblings can mask malformed sibling drops; next proof target: extractor test with one valid card plus one malformed card and artifact status.
    - suspicious surface: completed-session scanner; tentative issue: `sandbox_root/session-a -> /tmp/outside-session` can shift the containment boundary before `review_md` validation; next proof target: scan/intake test rejecting or degrading symlink session entries whose resolved path escapes sandbox root.
    - suspicious surface: reconciler origin-key map; tentative issue: duplicate `finding_id` within one corpus entry overwrites provenance before grouping; next proof target: reconciliation test preserving/degrading both same-entry origins.
  - Key findings:
    - [FB-013] Generated-review parsing can silently drop malformed sibling issues after at least one issue parses. Sources: sandbox 5864 `review.md` citing `cure_subsequent_review/prior_findings.py:114`, `:125`, `:137`, `:163`.
    - [FB-014] Symlinked session directories can move the completed-session containment boundary outside the sandbox root. Sources: sandbox 5864 `review.md` citing `cure_sessions.py:1056`, `:1057`, `:1059`, `:865`, `:867`, `cure_subsequent_review/prior_corpus.py:57`.
    - [FB-016] Same-entry duplicate finding IDs are overwritten during reconciliation. Sources: sandbox 5864 `review.md` citing `cure_subsequent_review/prior_findings.py:189`, `cure_subsequent_review/finding_identity.py:30`, `:72`, `:120`.
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01`

- 2026-06-06T05:40:31Z Review run by focused child after sandbox 5864 FB-013/FB-014/FB-016 hardening resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: FB-013, FB-014, FB-016; A5/A7/A8/A14/A20/A22; Prior Review Corpus Builder, Prior Finding Extractor, Finding Reconciler, completed-session sandbox containment and provenance.
  - Original intent checked: Story 01 intake/ledger-only contract, sandbox 5864 review findings, `research-cure-subsequent-pr-review-01`, `babysit-cure-subsequent-pr-review-01`, `cure-pr22-5864-review-triage`, direct code/tests.
  - Traceability: FB-013 closed; FB-014 closed; FB-016 closed. Story 02 feedback FB-012/FB-015 was not required for this Story 01 review and remains out of scope.
  - Files reviewed: `projects/CURe/cure_sessions.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/tests/test_subsequent_review.py`, sandbox 5864 `review.md`, coordination MASTER/story files.
  - Checks run: focused FB-013/FB-014/FB-016 and invariant tests ✅; `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (30 tests); `ruff check . && mypy` ✅; `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `git diff --check` ✅.
  - Risk lenses reviewed: generated-review malformed sibling card degradation and clean `- None.` success-empty behavior; symlinked child session directories escaping `sandbox_root.resolve()` before metadata/review reads; FB-011 artifact-boundary preservation; same-entry duplicate finding IDs and complete reconciliation provenance; Story 01 remote corpus/authorship/status invariants; Story 02/03 semantic boundary.
  - Finding closure:
    - Closed [FB-013/A7/A14/A22]: `_extract_generated_review_issues` now records per-card `parse_degraded` artifact statuses with `missing_generated_severity`, entry/source/artifact/title/section/evidence provenance when a generated in-scope issue card lacks severity, even when sibling cards parse; clean generated `### In Scope Issues` / `- None.` sections remain success-empty.
    - Closed [FB-014/A5/FB-011]: `scan_completed_sessions_for_pr` resolves `sandbox_root` and rejects any child entry whose resolved path is outside the sandbox before reading `meta.json` or review artifacts; prior FB-011 `paths.review_md` session-boundary handling and unavailable-artifact degradation remain intact, and historical display compatibility was not broadened.
    - Closed [FB-016/A8/A20]: `reconcile_findings` indexes duplicate same-entry `corpus_entry_id:finding_id` origin keys (`#1`, `#2`, ...) instead of overwriting them, preserves all local findings/provenance in the ledger, and marks `duplicate_origin_keys` degradation.
    - Preserved [Story 01 invariants]: evidence policy enum remains exactly `trusted`/`untrusted`; trusted issue-comment and pull-review bodies still enter corpus only with CURe authorship heuristic; review comments remain discussion metadata only; remote-only trusted corpus/status behavior remains intact; no Story 02 source-truth, authority/disposition, prompt packaging, report governor, or memory-reuse closure was required or added.
  - Key findings: none material.
  - Positive notes: pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` remains untracked and untouched.
  - Debt Friction: none for Story 01; FB-007/FB-010 and Story 02 FB-012/FB-015 remain future/out-of-scope work.
  - Next action: Story 01 can be finalized/committed; preserve pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` unless intentionally bundling that separate epic artifact.

- 2026-06-06T07:12:40Z Review feedback absorbed from sandbox 59e0
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-061114-59e0/review.md`
  - Feedback IDs: FB-017, FB-018, FB-019, FB-020
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: not_assessable
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `✅ DONE` -> `🔄 IN PROGRESS`
  - Sections reviewed: A3/A4/A7/A8/A9/A14/A20/A21 and persisted Story 01 artifact contracts for PR History Collector, Prior Review Corpus Builder, Prior Finding Extractor, and Finding Reconciler.
  - Original intent checked: Story 01 intake/ledger-only contract, sandbox 59e0 review findings, prior sandbox 5864 closure notes.
  - Traceability: forward gaps; backward complete.
  - Code surfaces searched: `projects/CURe/cure_subsequent_review/github_history.py`, `prior_corpus.py`, `prior_findings.py`, `finding_identity.py`, `control_plane.py`, `contracts.py`.
  - Risk / miss category: status semantics/cross-module consistency; parsing/metadata preservation; finding-identity status semantics; persistence/schema contract.
  - Finding closure required: resume Story 01 with red-first regressions for degraded discussion status propagation, heading-style prior finding section inheritance, ambiguous/missing supersedes degraded status reasons, and top-level schema versions on module artifacts.
  - Evidence quality: confirmed sandbox 59e0 artifacts show `pr_discussion.json` degraded with `discussion_incomplete` while downstream corpus/finding/reconciler artifacts were success; review supplies concrete reproduction sketches and source trails; additive schema-version change appears within Story 01 persisted artifact ownership.
  - Key findings:
    - [FB-017] Degraded PR discussion history can be hidden by downstream `success` statuses when degraded discussion still yields usable CURe entries. Sources: sandbox 59e0 `review.md` citing `github_history.py:179`, `prior_corpus.py:140`, `prior_corpus.py:143`; artifacts show degraded `pr_discussion.json` but success corpus/finding/reconciler ledgers.
    - [FB-018] Heading-style prior findings lose surrounding section unless they repeat `Section:`. Sources: sandbox 59e0 `review.md` citing `prior_findings.py:223`, `:227`, `:231`; reproduction uses `## Technical Assessment` then `### A-01: ...`.
    - [FB-019] Ambiguous or missing `Supersedes` links serialize markers but leave reconciler status `success`. Sources: sandbox 59e0 `review.md` citing `finding_identity.py:113`, `:123`, `:166`.
    - [FB-020] `pr_discussion.json`, `prior_review_corpus.json`, `prior_findings.json`, and `reconciled_findings.json` lack top-level `schema_version`; manifest and decision are already versioned. Sources: sandbox 59e0 `review.md` citing `control_plane.py:124`, `contracts.py:129`, `contracts.py:167`.
  - Debt Friction: none.
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01`

- 2026-06-06T08:20:39Z Review feedback absorbed from sandbox 095b
  - Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-074120-095b/review.md`
  - Feedback IDs: FB-021, FB-022, FB-023, FB-024, FB-025
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: done
  - Prior review concerns: request_changes at PR head `ee51ce1`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none; all findings are Story 01 intake/ledger hardening.
  - Status transition: `✅ DONE` -> `🔄 IN PROGRESS`
  - Sections reviewed: A3/A5/A7/A8/A13/A14/A20/A22 and Story 01 completed-session, parser, corpus provenance contracts.
  - Original intent checked: Story 01 intake/ledger-only contract, sandbox 095b review findings, prior sandbox 59e0 closure notes.
  - Traceability: forward gaps; backward complete.
  - Code surfaces cited by review: `cure_sessions.py`, `cure.py`, `cure_subsequent_review/prior_findings.py`, `cure_subsequent_review/contracts.py`, `cure_subsequent_review/github_history.py`, `cure_subsequent_review/prior_corpus.py`.
  - Risk / miss category: security/persistence boundary; parsing/evidence contract; parser provenance; remote provenance/schema.
  - Finding closure required: resume Story 01 with red-first regressions for resolve-failure `paths.review_md` degradation, symlinked `meta.json` rejection, generated-review missing-source degradation, authored parse-degraded evidence/provenance retention, and pull-review `commit_id`/reviewed-head propagation.
  - Key findings:
    - [FB-021] Malformed historical `paths.review_md` can abort a new `cure pr` before prior-corpus degradation. Sources: sandbox 095b `review.md` citing `cure_sessions.py:865`, `cure_sessions.py:1073`, `cure.py:9532`.
    - [FB-022] Generated-review bullets with severity but no valid `Sources:` are promoted as successful prior findings with empty evidence. Sources: sandbox 095b `review.md` citing `prior_findings.py:140`, `:143`, `:150`, `:85`, `cure_flows.py:1360`.
    - [FB-023] `meta.json` symlinks can escape the sandbox/session boundary and seed metadata from outside the session dir. Sources: sandbox 095b `review.md` citing `cure_sessions.py:190`, `:194`, `:1063`, `:1067`, `:1069`.
    - [FB-024] Malformed authored finding statuses drop provenance and scanned evidence needed to audit degraded prior-review artifacts. Sources: sandbox 095b `review.md` citing `prior_findings.py:55`, `:68`, `:72`, `:73`, `contracts.py:232`.
    - [FB-025] Remote pull-review corpus entries lose reviewed-head provenance. Sources: sandbox 095b `review.md` citing `contracts.py:97`, `:107`, `github_history.py:144`, `:153`, `prior_corpus.py:128`.
  - Debt Friction: none.
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01`

- 2026-06-06T08:31:32Z Review run by focused child after sandbox 095b FB-021/FB-022/FB-023/FB-024/FB-025 hardening resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🔄 IN PROGRESS` -> `✅ DONE`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: FB-021, FB-022, FB-023, FB-024, FB-025; A3/A5/A7/A8/A13/A14/A20/A22; completed-session artifact/metadata containment; prior finding parser provenance; pull-review corpus/finding reviewed-head provenance.
  - Original intent checked: Story 01 intake/ledger-only contract, sandbox 095b review findings, direct code/tests.
  - Traceability: FB-021 closed; FB-022 closed; FB-023 closed; FB-024 closed; FB-025 closed.
  - Files reviewed: `projects/CURe/cure_sessions.py`, `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/tests/test_subsequent_review.py`.
  - Checks run: `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (35 tests); `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests; pre-existing ResourceWarnings/log noise); `ruff check . && mypy`; `git diff --check` ✅.
  - Finding closure:
    - Closed [FB-021/A5]: `paths.review_md` resolve/is-file failures such as symlink loops now degrade as `review_md_unresolvable` and reach corpus unavailable-artifact status instead of aborting scan/intake.
    - Closed [FB-022/A7/A14/A22]: generated-review cards with severity but no source refs now degrade as `missing_generated_sources` and do not emit source-empty success findings.
    - Closed [FB-023/A5/security]: `scan_completed_sessions_for_pr` rejects `meta.json` symlinks whose resolved path leaves the resolved session directory before metadata is loaded.
    - Closed [FB-024/A14]: authored parse-degraded statuses preserve source type, artifact/comment URL, reviewed head, section/title, and scanned source evidence.
    - Closed [FB-025/A13]: trusted pull-review `commit_id`/head SHA propagates through `DiscussionEvent.reviewed_head`, corpus entry/provenance, and extracted finding provenance.
    - Preserved [Story 01 invariants]: `EvidencePolicy` remains exactly `trusted`/`untrusted`; review comments remain discussion metadata only; no Story 02 source-truth, authority/disposition, prompt packaging, report-governor, or memory-reuse behavior was added.
  - Key findings: none material.
  - Positive notes: pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` remains untracked and untouched.
  - Debt Friction: none for Story 01.
  - Next action: commit/push product closure for PR #22; preserve pre-existing untracked SVG.

- 2026-06-06T07:21:09Z Review run by focused child after sandbox 59e0 FB-017/FB-018/FB-019/FB-020 hardening resume
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Sections reviewed: FB-017, FB-018, FB-019, FB-020; A3/A4/A7/A8/A9/A14/A20/A21; persisted Story 01 module artifact schema contracts; Story 01 intake-only invariants.
  - Original intent checked: Story 01 intake/ledger-only contract, sandbox 59e0 review findings, `research-cure-subsequent-pr-review-01`, `babysit-cure-subsequent-pr-review-01`, `cure-pr22-59e0-feedback-absorption`, direct code/tests.
  - Traceability: FB-017 closed; FB-018 closed; FB-019 closed; FB-020 closed.
  - Files reviewed: `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/tests/test_subsequent_review.py`, coordination MASTER/story files.
  - Checks run: focused FB-017/FB-018/FB-019/FB-020 tests ✅; `PYTHONPATH=tests python -m unittest tests.test_subsequent_review` ✅ (33 tests); `git diff --check` ✅. Parent-reported post-implementation checks verified as already run: `PYTHONPATH=tests python -m unittest tests.test_reviewflow_unittest` ✅ (442 tests), `ruff check . && mypy && git diff --check` ✅.
  - Risk lenses reviewed: degraded discussion status propagation through downstream artifacts/manifest; heading-style section inheritance; ambiguous/missing `Supersedes` status semantics; additive top-level module artifact schema versioning; review-comment corpus exclusion; evidence policy enum boundary; Story 02/03 semantic boundary.
  - Finding closure:
    - Closed [FB-017/A3/A4/A9/A21]: degraded `DiscussionArtifact.status_reasons` now propagate into prior corpus, prior finding ledger, reconciler, and manifest module reasons, so usable CURe discussion entries cannot hide incomplete/degraded collection.
    - Closed [FB-018/A7/A14]: heading-style findings now inherit the enclosing `##` section when `Section:` is absent, while explicit `Section:` remains authoritative.
    - Closed [FB-019/A8/A20]: ambiguous `Supersedes` markers and missing supersedes targets now degrade reconciliation with explicit `ambiguous_supersedes` / `supersedes_target_not_found` reasons while preserving serialized markers/edges; duplicate-origin degradation remains intact.
    - Closed [FB-020/persistence schema]: `pr_discussion.json`, `prior_review_corpus.json`, `prior_findings.json`, and `reconciled_findings.json` now emit top-level `schema_version: 1`; manifest/decision versioning remains unchanged.
    - Preserved [Story 01 invariants]: `EvidencePolicy` remains exactly `trusted`/`untrusted`; trusted issue-comment and pull-review bodies still require CURe authorship; review comments remain discussion metadata only; no source-truth, authority/disposition, prompt packaging, report governor, or memory-reuse behavior was added.
  - Key findings: none material.
  - Positive notes: pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` remains untracked and untouched.
  - Debt Friction: none for Story 01; FB-007/FB-010 and Story 02/03 work remain future/out-of-scope.
  - Next action: Story 01 can be finalized/committed; preserve pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` unless intentionally bundling that separate epic artifact.

- 2026-06-07T06:04:09Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: resolved for logged FB-017..FB-025 closures; new proof/implementation gaps found
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `🟣 IN REVIEW` -> `🔄 IN PROGRESS`
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: MASTER.md, Story 01, PR #21/#22 anchors, feedback IDs FB-001..FB-025, local git branch/history; no CONTRACT.md present
  - Traceability: forward gaps; backward gaps
  - Test architecture: gaps; TAP rows aligned in broad shape but TAP-01/TAP-02/TAP-04/TAP-06/TAP-07 proof gaps remain
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `cure_subsequent_review/contracts.py`, `__init__.py`, `control_plane.py`, `github_history.py`, `prior_corpus.py`, `prior_findings.py`, `finding_identity.py`, `cure.py` PR-flow/list helpers, `cure_sessions.py`, `pyproject.toml`, split subsequent-review test suites, fixture directory, PR #21/#22 anchors
  - Risk lenses reviewed: external GitHub I/O/pagination shape, parser/generated input, finding identity/provenance, module lifecycle/preflight status, command routing/backwards compatibility, packaging/typecheck visibility, fixture determinism, Story 02/03 semantic bleed excluded
  - Finding closure: previous FB-017..FB-025 closure claims were checked and mostly remain closed; this run opened new A1/A3/A4/A7/A10/A11/A14/A16/A17/A19/A21/A22 proof and behavior gaps
  - Evidence quality: confirmed missing plural import, fixture inventory, parser/normalizer/summary code paths, absent prompt/latest positive tests, focused split-suite pass `35 passed, 3 subtests`; inferred malformed payload and false-source-token runtime effects; unknown live frequency; provisional remediation design
  - Files reviewed: `projects/CURe/cure_subsequent_review/contracts.py`, `projects/CURe/cure_subsequent_review/__init__.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/prior_findings.py`, `projects/CURe/cure_subsequent_review/finding_identity.py`, `projects/CURe/cure.py`, `projects/CURe/cure_sessions.py`, `projects/CURe/pyproject.toml`, `projects/CURe/tests/_subsequent_review_*`, `projects/CURe/tests/fixtures/subsequent_review/simulation_raw.json`, `MASTER.md`, Story 01
  - Hypothesis triage:
    - suspicious surface: `contracts.py` public API; tentative issue: documented package smoke imports plural enum that implementation does not export; next proof target: installed `from cure_subsequent_review.contracts import SubsequentReviewModules`.
    - suspicious surface: fixture pack; tentative issue: A20-A22 deterministic fixture/golden samples live inline in tests, not the contracted fixture directory; next proof target: `tests/fixtures/subsequent_review/` inventory and TAP-01 validation.
    - suspicious surface: GitHub list payload normalization; tentative issue: malformed dict payloads and normal success provenance do not satisfy endpoint/fetch/no-zero-discussion contract; next proof target: `_normalize_source_payload` dict/list branches.
    - suspicious surface: generated review `Sources:` parser; tentative issue: incidental tokens such as `port:443` or `ratio:16` can become valid finding evidence; next proof target: generated-review parser regression.
    - suspicious surface: control-plane summary and PR-flow routing tests; tentative issue: disabled module statuses and prompt/latest variants are under-proven; next proof target: TAP-06/TAP-07 assertions.
  - Key findings:
    - A10 package contract smoke fails because the story imports `SubsequentReviewModules`, but implementation exports only singular `SubsequentReviewModule`. Sources: `projects/CURe/cure_subsequent_review/contracts.py:30`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The documented verification command and contract name cannot be imported from the installed package, so A10/A12 are not actually satisfied by the current passing unit test.

      **Assumptions / Preconditions:** A caller or package smoke follows the Story 01 documented plural import.

      **Downgrade Factors:** A singular enum with the intended 13 members exists; an alias may be a small compatibility fix.

      **Code Trail:** Story verification names `SubsequentReviewModules`; `contracts.py` defines only `SubsequentReviewModule`; `__init__.py` exports only the singular symbol; a direct import probe raised `ImportError`.

      **Reproduction:** `cd projects/CURe && python - <<'PY'\nfrom cure_subsequent_review.contracts import SubsequentReviewModules\nPY`

      </details>
    - A11 fixture contract is incomplete for A20-A22 regression cases; the required duplicate/supersedes, `--slurp` taxonomy, and real generated-review samples are inline tests rather than deterministic fixture/golden artifacts. Sources: `projects/CURe/tests/fixtures/subsequent_review/simulation_raw.json:1`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** Story 01 requires reusable deterministic fixtures/goldens, not only inline literals, so fixture inventory can drift while behavior tests still pass.

      **Assumptions / Preconditions:** Reviewers and later stories rely on `tests/fixtures/subsequent_review/` as the stable landmark fixture pack.

      **Downgrade Factors:** Inline unit tests do cover much of A20-A22 behavior today.

      **Code Trail:** The fixture directory contains only `simulation_raw.json` with A/B/C/S basics and limited goldens; A20/A21/A22 inputs are embedded in split unit tests instead of persisted fixture files/entries.

      **Reproduction:** List `tests/fixtures/subsequent_review/` and compare it with A11/TAP-01 required fixture samples for duplicate IDs/supersedes, `gh api --paginate --slurp` taxonomy, and generated `review.md` samples.

      </details>
    - GitHub discussion normalization can still produce incomplete provenance or success-empty discussion for malformed list payload shapes. Sources: `projects/CURe/cure_subsequent_review/github_history.py:60`

      <details open>
      <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A3/A4/A21 require endpoint/fetch provenance and no failed/malformed data path being interpreted as complete zero discussion.

      **Assumptions / Preconditions:** The list helper or a future REST/GraphQL seam returns a dict without list-valued `items`/`data`, or normal success needs fetch provenance for audit.

      **Downgrade Factors:** Explicit degraded payloads and subprocess failures are handled better than earlier runs.

      **Code Trail:** `_normalize_source_payload()` wraps bare list success with no fetch provenance and accepts dict payloads with non-list/missing `items`/`data` as empty items, default `complete=True`, `status=complete`, and no reason.

      **Reproduction:** Feed `{}` or `{"data": {"nodes": []}}` through the discussion fetch seam and inspect `pr_discussion.json` for a complete zero-event endpoint instead of degraded pagination-shape status.

      </details>
    - Generated CURe review parsing accepts incidental `Sources:` tokens such as `port:443` or `ratio:16` as valid source evidence. Sources: `projects/CURe/cure_subsequent_review/prior_findings.py:123`

      <details open>
      <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A7/A14/A22 require usable source evidence or explicit parse degradation; bogus non-file tokens make prior-finding memory look auditable when it is not.

      **Assumptions / Preconditions:** A generated review issue has severity and a `Sources:` line containing incidental `word:number` tokens but no real file citation.

      **Downgrade Factors:** Truly missing generated sources degrade, and valid extensionless root paths such as `LICENSE:1` are intentionally supported.

      **Code Trail:** Generated `Sources:` parsing enables extensionless-root paths, and `_looks_like_source_ref()` accepts any reference when that flag is set, so `port:443`/`ratio:16` pass as source snippets.

      **Reproduction:** Feed a generated `### In Scope Issues` card with severity and `Sources: port:443, ratio:16`; current extractor returns a success finding with those snippets instead of `missing_generated_sources`.

      </details>
    - A1 preflight summary omits disabled later-module statuses even though the manifest records them. Sources: `projects/CURe/cure_subsequent_review/control_plane.py:86`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** A1 promises operator-visible per-module enable/disable status in the preflight summary, not only in a JSON manifest.

      **Assumptions / Preconditions:** Later Story 02/03 modules remain disabled while Story 01 intake runs.

      **Downgrade Factors:** The manifest does include disabled defaults, so persisted audit data is stronger than the summary.

      **Code Trail:** `_manifest_json()` fills every module default, but `_summary()` formats only records already present in the run records dict; later disabled modules are absent from that dict.

      **Reproduction:** Run enabled intake and inspect the summary text; `source_truth_verifier=disabled` and other disabled later modules are missing while present in `run_manifest.json`.

      </details>
    - TAP-07 branch proof is incomplete for latest/prompt variants named by A16/A17/A19. Sources: `projects/CURe/tests/_subsequent_review_integration_pr_flow_unittest.py:61`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** Story 01 specifically requires list/latest/prompt-selected historical exits to avoid sandbox/intake artifacts and non-TTY prompt fallback to run intake; missing tests leave branch-safe behavior under-proven.

      **Assumptions / Preconditions:** Future PR-flow edits affect `--if-reviewed latest` or prompt routing.

      **Downgrade Factors:** Code inspection shows intended branches, and list/new paths are tested.

      **Code Trail:** The integration suite has list tests, an unavailable-latest failure test, and new/disabled tests, but no positive latest available-session test, no interactive prompt-selected-history test, and no non-TTY prompt fallback-to-new test.

      **Reproduction:** Search the split integration suite for prompt-selected history and positive latest tests; only `test_if_reviewed_latest_unavailable_session_fails_before_new_sandbox` is present.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 01` to fix the six acceptance/proof gaps above, then rerun focused verification and review

- 2026-06-07T06:48:35Z Review run by fresh maintainer session
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Multipass review: focused fresh implementation review after TAP quality-lens resume
  - Prior review concerns: six 2026-06-07T06:04:09Z blockers verified closed; prior FB-017..FB-025 closure claims preserved; no new blockers found
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Sections reviewed: Purpose, Scope, Out of Scope, Acceptance A1/A3/A4/A7/A10/A11/A12/A14/A16/A17/A19/A20/A21/A22, Verification Commands, Test Architecture Plan, Acceptance Proof Matrix, Critical Files, Implementation Notes, Locked Decisions, MASTER Story tracker
  - Original intent checked: MASTER.md, Story 01, cached research/review grounding notebooks, prior request_changes entry, product diff; no CONTRACT.md present
  - Traceability: forward and backward trace pass for Story 01 intake/ledger scope; Story 02/03 source truth, authority/disposition, prompt packaging, report governor, memory reuse, and final landmark dispositions remain excluded
  - Test architecture: TAP-01/TAP-02/TAP-04/TAP-05/TAP-06/TAP-07/TAP-08 aligned and locally proven by direct reads plus focused/broad checks
  - Code surfaces reviewed: `projects/CURe/cure_subsequent_review/contracts.py`, `__init__.py`, `control_plane.py`, `github_history.py`, `prior_findings.py`, `finding_identity.py`, `cure.py` GitHub list/PR-flow seams, split subsequent-review test suites, fixture directory, `pyproject.toml`, MASTER/story files
  - Risk lenses reviewed: public contract/package import, fixture/golden persistence, malformed GitHub payload provenance/no success-empty fallback, generated-review false source tokens, disabled module status visibility, historical-exit/new-sandbox routing, evidence-policy boundary, Story 02/03 semantic bleed
  - Finding closure:
    - Closed [A10/A12]: `SubsequentReviewModules` is exported as an additive alias from contracts and package top level; temporary-venv installed package smoke imports it and verifies all 13 modules.
    - Closed [A11/A20/A21/A22]: deterministic regression fixture/golden files now exist under `tests/fixtures/subsequent_review/` and are read by TAP-01/TAP-04/TAP-05 tests.
    - Closed [A3/A4/A21]: normal list markers include endpoint/fetch provenance, and malformed complete dict payloads without list-valued `items`/`data` degrade as `discussion_payload_malformed` with `cause=payload_shape` rather than success-empty.
    - Closed [A7/A14/A22]: generated-review parsing rejects incidental lowercase source tokens such as `port:443` and `ratio:16`, degrades with `missing_generated_sources`, and still permits intentional uppercase root file refs such as `LICENSE:1`.
    - Closed [A1/A9]: preflight summary now lists all 13 module statuses, including disabled later modules such as `source_truth_verifier` and `landmark_trace_runner`; manifest coverage remains intact.
    - Closed [A16/A17/A19]: TAP-07 integration tests now cover positive latest historical exit, interactive prompt-selected historical exit, and non-TTY prompt fallback-to-new/intake.
  - Checks run: `PYTHONPATH=tests python -m pytest tests/_subsequent_review_unit_contracts_cli_unittest.py tests/_subsequent_review_unit_github_history_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py tests/_subsequent_review_unit_prior_findings_unittest.py tests/_subsequent_review_unit_reconciliation_unittest.py tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` ✅ (47 passed, 6 subtests); `PYTHONPATH=tests python -m pytest tests/test_subsequent_review.py -q` ✅ (49 passed, 13 subtests); `PYTHONPATH=tests python -m pytest tests/test_reviewflow_unittest.py -q` ✅ (442 passed, 14 subtests); `ruff check . && mypy` ✅; `git diff --check` ✅; temporary-venv package reinstall/import smoke ✅; targeted direct probes for plural import, malformed payload degradation, incidental generated sources rejection, and disabled summary statuses ✅
  - Key findings: none material
  - Positive notes: pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` remains untracked and untouched; no product commit made
  - Debt Friction: none for Story 01; later-story candidates FB-007/FB-010 and Story 02/03 semantics remain out-of-scope
  - Next action: Story 01 can be finalized/committed; preserve untracked SVG unless explicitly bundling that separate epic artifact


## Live-audit remap review note

- 2026-06-14T10:46:40Z Provenance repair review note: PR #22 live-audit feedback FB-033 and FB-037 should be reviewed against Story 01 intake/extractor/path-boundary invariants, not as an active Story 05. The change is documentation/provenance-only; implementation evidence remains in PR #22 commits `f96e7ad` and `ee7410a`.
