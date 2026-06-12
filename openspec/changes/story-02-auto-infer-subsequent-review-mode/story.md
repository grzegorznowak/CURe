# Story 02 — Auto-infer Subsequent Review Mode

Plan: 🟢 PLAN APPROVED
Status: ✅ DONE

> Migrated from legacy `agent_coordination` into this OpenSpec change workspace on 2026-06-12.
> Runtime progress/history lives in `progress.md`; implementation review history lives in `reviews.md`.

## Purpose

Make fresh `cure pr <PR_URL>` runs decide subsequent-review intake automatically instead of requiring the operator to know whether the PR is subsequent. The command surface has exactly two states: default `auto`, which infers whether Story 01 intake should run from PR/session evidence and records the decision, and explicit `disabled`, which opts out and never runs intake. No force-enable state is introduced.

## Actors

- Primary: CURe operator running `cure pr` on a PR that may or may not have prior CURe review history.
- Secondary: implementation agent.
- System: CURe PR command routing, subsequent-review decision service, Story 01 intake control plane, session metadata writer.
- Reviewer: story-review agent.

## Triggering Need

Story 01 implemented `--subsequent-review` as an explicit opt-in for intake artifacts. A local PR #22 run then produced normal review artifacts but no `work/subsequent/*` artifacts because the operator did not pass the opt-in flag. The operator decision for FB-001 is that CURe should infer subsequent-review mode from PR/session state, while retaining a single explicit opt-out.

## Expected Prerequisites

- DEPENDS = 01.
- Story 01 intake artifacts and split tests exist under `projects/CURe/cure_subsequent_review/`, private `projects/CURe/tests/_subsequent_review_*_unittest.py` modules, and the public `projects/CURe/tests/test_subsequent_review.py` wrapper.

## Scope

- Replace the top-level `cure pr` subsequent-review command decision with exactly two states:
  - `auto` — default when no opt-out flag is present.
  - `disabled` — explicit opt-out via `--no-subsequent-review`.
- Remove or reject `--subsequent-review` as a force-enable command state. The parser/help/tests must not expose an enabled/force state; if compatibility handling is needed, it must fail loudly with migration guidance rather than silently forcing intake.
- Add a small decision service in `cure_subsequent_review` rather than growing `cure.py`. The service accepts PR identity, completed local sessions, an optional remote-discussion probe/fetcher, and the selected command mode; it returns a typed decision object with `mode`, `enabled`, reasons, signal counts, degraded reasons, and evidence-policy value.
- Define deterministic auto inference:
  - Auto enables intake when completed local CURe sessions exist for the PR.
  - Auto enables intake when completed local sessions include prior subsequent-review artifacts for the PR.
  - Auto enables intake when a remote PR discussion probe finds an issue comment or pull review body containing the official CURe review footer block (`<!-- CURE_REVIEW_FOOTER_START -->` ... `<!-- CURE_REVIEW_FOOTER_END -->`) for the PR, regardless of author/login. The footer block is the durable machine marker; generic body text, `CURe review` headings, `<!-- cure -->`, or author/login allowlists alone are insufficient without the official footer.
  - Auto enables intake in conservative degraded mode when the remote PR discussion probe is truly unavailable, raises, or returns an enabling fetch/pagination failure and local evidence is absent, because the run cannot prove that prior CURe PR comments do not exist.
  - Auto disables intake only when local completed-session evidence is absent and the remote probe completes enough to find no official CURe footer markers in issue comments or pull review bodies, or when the only remote uncertainty is non-enabling metadata such as `discussion_incomplete` / `thread_state_unavailable` with zero official footer markers; the disabled decision still records degraded reasons.
  - Auto must not enable as positive prior-CURe-review evidence solely from generic human comments, CURe-looking body text without the official footer, spoofed or allowlisted author/login text without the footer, review-comment line comments, resolved-thread markers, missing thread-state metadata, branch names, PR age, or evidence-policy selection. Missing thread-state metadata may only contribute to non-enabling degraded reasons unless paired with a broader probe failure; it must never be counted as a prior-CURe-review marker.
- Preserve existing `--if-reviewed prompt|new|list|latest` branch semantics. Historical exits (`list`, `latest`, and prompt-selected historical review) must still return before new sandbox/work artifacts are created. Auto decisions and decision artifacts are required only once the command proceeds to a new sandbox.
- Persist visible decision metadata for every new-sandbox `cure pr` run, including auto-disabled and explicit-disabled runs, so absence of Story 01 intake artifacts is never ambiguous.
- Write a decision artifact for every new-sandbox run at `work/subsequent/decision.json`. Enabled runs also write the Story 01 intake artifacts; disabled or auto-disabled runs do not run intake but still write the decision artifact.
- Extend `meta.json` with an explicit `subsequent_review` block for every new-sandbox run. The block records `schema_version`, `mode`, `enabled`, `evidence_policy`, `decision.reasons`, `decision.signal_counts`, `decision.degraded_reasons`, `decision_path`, `artifact_dir`, and `manifest_path` (`null` when intake did not run). `paths.subsequent_review_decision` is always set for new-sandbox runs; `paths.subsequent_review_manifest` is set only when intake ran.
- Ensure enabled auto decisions pass `SubsequentReviewConfig(enabled=True, evidence_policy=...)` to the Story 01 control plane and preserve existing Story 01 artifact names/schemas unless explicitly versioned.
- Guard the decision/intake preflight after `SessionProgress.init(...)`: exceptions raised by `decide_subsequent_review`, `write_decision_artifact`, or enabled Story 01 intake/artifact writes must update `meta.json.status = "error"` through the same session lifecycle semantics used by the main review flow before re-raising.
- Update command catalog/help and focused tests so recommended `cure pr` usage no longer teaches `--subsequent-review` and does document `--no-subsequent-review` as the opt-out.

## Out of Scope

- Source verification, source-state labels, discussion authority semantics, disposition actions, prompt/context packaging, report governor/output validation, memory reuse, and full landmark trace behavior. Those remain later-story scope.
- Adding evidence-policy modes beyond `trusted` and `untrusted`.
- Treating discussion comments as proof of source resolution.
- Redesigning or polishing the SVG landmark.
- Running live GitHub PR #21 as required automated proof; deterministic local fixtures/mocks are required.

## Scenarios / Behavior Examples

- S1: Given `cure pr <PR_URL> --if-reviewed new` is invoked with no subsequent-review flag and completed local CURe sessions exist for the PR, when a new sandbox is selected, then auto mode records `enabled=true`, reason `completed_sessions_found`, signal counts, and runs Story 01 intake after the work directory exists. Covers: A1.
- S2: Given no completed local sessions exist but the remote PR discussion probe finds an issue comment or pull review body with the official CURe review footer, even when authored by a human/operator account, when a new sandbox is selected, then auto mode records `enabled=true`, reason `cure_pr_discussion_found`, and runs Story 01 intake. Covers: A2.
- S3: Given no completed local sessions exist and the remote PR discussion probe completes with no official CURe footer markers in issue comments or pull review bodies, when a new sandbox is selected, then auto mode records `enabled=false`, reason `no_prior_review_signals`, writes `work/subsequent/decision.json`, sets decision metadata, leaves the manifest path absent or null, and does not run intake. Covers: A3.
- S4: Given no completed local sessions exist and the remote PR discussion probe raises or is truly unavailable, when a new sandbox is selected, then auto mode records `enabled=true`, reason `remote_probe_degraded`, includes degraded reasons, and runs intake so unavailable remote history is visible in subsequent-review artifacts. Covers: A4.
- S5: Given `--no-subsequent-review` is passed, when a new sandbox is selected, then mode is `disabled`, enabled is false, reason `operator_disabled`, selected/default evidence policy is recorded, and Story 01 intake is never invoked regardless of prior signals. Covers: A5.
- S6: Given `--subsequent-review` is passed, when arguments are parsed, then the command fails loudly or is rejected with guidance to omit the flag for auto mode; it must not become a force-enable state. Covers: A6.
- S7: Given an auto-enabled decision is made from local completed sessions, official-footer remote markers, or true/enabling degraded remote uncertainty, when the new sandbox artifacts are inspected, then `work/subsequent/decision.json`, `run_manifest.json`, `pr_discussion.json`, `prior_review_corpus.json`, `prior_findings.json`, and `reconciled_findings.json` exist and `meta.json.paths` includes both decision and manifest paths. Covers: A7.
- S8: Given an auto-disabled decision is made from no local sessions and a complete no-marker remote probe, when the new sandbox artifacts are inspected, then the decision artifact and `meta.json.subsequent_review` explain the disabled decision and Story 01 intake artifacts are absent. Covers: A8.
- S9: Given `--no-subsequent-review` is passed with prior local sessions or official-footer remote markers available, when the new sandbox artifacts are inspected, then explicit-disabled decision metadata/artifact exist and no Story 01 intake artifacts are written. Covers: A9.
- S10: Given `--if-reviewed list`, `--if-reviewed latest`, or prompt-selected historical review is used, when the command exits via existing historical behavior, then no new sandbox and no new decision/intake artifacts are created; when prompt falls back to a new review, the auto/disabled decision occurs only after the new work directory exists. Covers: A10.
- S11: Given evidence-policy arguments are parsed and passed through the decision/intake flow, when command mode is default auto or explicit disabled, then evidence policy remains exactly `trusted` or `untrusted` and is not conflated with command mode. Covers: A11.
- S12: Given any new-sandbox subsequent-review decision completes, when console/log output is captured, then it summarizes the decision as auto enabled, auto disabled, or disabled with key reasons. Covers: A12.
- S13: Given no local sessions and a complete remote probe containing only generic human discussion, CURe-looking body text without the official footer, missing authors, review-comment line comments even if CURe-looking, spoofed or allowlisted CURe-looking logins without the official footer, or resolved/unresolved/missing thread-state metadata, when a new sandbox is selected, then auto mode records zero positive prior-CURe-review markers and does not set `cure_pr_discussion_found`. Covers: A13.
- S14: Given no local sessions and remote discussion is unavailable, fetch/pagination incomplete, or has only metadata-level uncertainty such as uninterpretable thread-state shapes, when a new sandbox is selected, then the decision records degraded reasons, enables intake only for true/enabling probe failures, and may auto-disable with `no_prior_review_signals` for metadata-only `discussion_incomplete` / `thread_state_unavailable` with zero official-footer markers. Covers: A14.
- S15: Given session initialization has already written `meta.json.status = running` and `decide_subsequent_review`, `write_decision_artifact`, or enabled intake/artifact writes raise, when the command exits, then `meta.json.status = error` with the exception cause is persisted before re-raising. Covers: A15.

## Acceptance

- A1: Default `cure pr <PR_URL>` / `--if-reviewed new` with completed local sessions records `subsequent_review.mode = "auto"`, `enabled = true`, a `completed_sessions_found` reason with signal counts, and runs Story 01 intake after the work directory exists.
- A2: Default auto mode with no local sessions but mocked issue-comment or pull-review-body PR discussion events containing the official CURe review footer records `enabled = true`, a remote-discussion reason, and runs Story 01 intake regardless of the event author/login.
- A3: Default auto mode with no local sessions and a complete remote probe showing no official CURe footer markers in issue comments or pull review bodies records `enabled = false`, reason `no_prior_review_signals`, writes `work/subsequent/decision.json`, sets `paths.subsequent_review_decision`, leaves `paths.subsequent_review_manifest` absent or null, and does not create Story 01 intake artifacts beyond the decision artifact.
- A4: Default auto mode with no local sessions and a truly unavailable remote probe or remote fetch exception records `enabled = true`, a degraded reason, runs Story 01 intake, and exposes uncertainty in decision metadata; metadata-only incomplete/thread-state reasons are governed by A14.
- A5: Explicit `--no-subsequent-review` records `mode = "disabled"`, `enabled = false`, reason `operator_disabled`, selected/default `evidence_policy`, and never calls `run_subsequent_review_intake` even when prior sessions or remote markers exist.
- A6: `--subsequent-review` is not a supported force-enable state. Parser/help/catalog/tests either omit it entirely or reject it with a clear message telling users to omit the flag for auto mode or pass `--no-subsequent-review` to opt out.
- A7: Auto-enabled runs write both decision metadata and existing Story 01 intake artifacts: `work/subsequent/decision.json`, `run_manifest.json`, `pr_discussion.json`, `prior_review_corpus.json`, `prior_findings.json`, and `reconciled_findings.json`; `meta.json.paths` includes both decision and manifest paths.
- A8: Auto-disabled runs write explicit decision metadata/artifact and no Story 01 intake artifacts. The absence of `run_manifest.json`, `prior_findings.json`, and related intake files is explained by `decision.json` and `meta.json.subsequent_review`.
- A9: Explicit-disabled runs write explicit decision metadata/artifact and no Story 01 intake artifacts, with the same non-ambiguous artifact absence guarantees as A8.
- A10: Existing historical `--if-reviewed` exits remain branch-safe: list/latest/prompt-selected-history paths create no new sandbox and no subsequent-review decision/intake artifacts; new/fallback-new paths make the auto/disabled decision only after the new work directory exists.
- A11: Evidence policy remains exactly `trusted` or `untrusted`; command mode values `auto|disabled` do not add a third evidence policy or alter Story 01 module policy semantics.
- A12: Console/log output for new-sandbox runs summarizes the subsequent-review decision (`auto enabled`, `auto disabled`, or `disabled`) and key reasons so users do not need to infer behavior from file presence.
- A13: Complete remote probes containing only generic human discussion, CURe-looking body text without the official footer, missing-author body-only text, review-comment line comments, spoofed or allowlisted author/login text without the footer, resolved/unresolved thread-state fields, or missing thread-state metadata record zero positive prior-CURe-review markers. They must not set `cure_pr_discussion_found` or enable intake as positive evidence.
- A14: Remote degraded states are explicit in `decision.json`/`meta.json` and are never positive prior-CURe markers. True unavailable/enabling fetch or pagination failures are degraded-enabled and run intake; metadata-only `discussion_incomplete` or `thread_state_unavailable` with zero official-footer markers are non-enabling degraded reasons that may auto-disable with `no_prior_review_signals` while remaining visible.
- A15: Exceptions after session initialization in `decide_subsequent_review`, `write_decision_artifact`, or enabled `run_subsequent_review_intake`/artifact writes persist `meta.json.status = "error"` and an error block before the command exits.

## Verification

### Verification Commands

- `cd projects/CURe && python -m pytest tests/test_subsequent_review.py -q` — public subsequent-review wrapper covering the split unit/functional/integration modules.
- `cd projects/CURe && python -m pytest tests/_subsequent_review_unit_contracts_cli_unittest.py tests/_subsequent_review_unit_decision_unittest.py tests/_subsequent_review_unit_github_history_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` — focused Story 02 seams for command mode, decision service, remote marker boundaries, metadata/artifacts, routing, and failure lifecycle.
- `cd projects/CURe && python -m pytest tests/test_reviewflow_unittest.py -q` — existing reviewflow regression tests, including command catalog/help expectations.
- `cd projects/CURe && ruff check . && mypy` — lint/type checks after source changes.
- File-read: inspect sandbox `meta.json` plus `work/subsequent/decision.json` for auto-enabled, auto-disabled, explicit-disabled, false-positive remote, degraded remote, and decision/intake failure-injection fixture runs.

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|---|---|---|---|---|---|---|---|---|---|
| TAP-01 | unit/CLI contract | A5/A6/A11 command states, obsolete force-enable rejection, evidence-policy separation, command catalog expectations | `tests/_subsequent_review_unit_contracts_cli_unittest.py`; `tests/test_reviewflow_unittest.py` command catalog coverage | argparse/help/catalog output crossing into normalized command mode/evidence policy | Parser/help assertions show default auto or disabled-only states, obsolete force-enable rejection/absence, evidence policy remains trusted/untrusted, and command catalog text is consistent. | Parser args and captured stderr/help text only; no sandbox/network/db/filesystem writes; ordering risk limited to shared parser globals, reset per test. | `python -m pytest tests/_subsequent_review_unit_contracts_cli_unittest.py -q`; `python -m pytest tests/test_reviewflow_unittest.py -q` | If CLI ownership moves out of `cure.py`, keep parser contract tests at the new builder seam and update catalog regression ownership explicitly. | CLI contract stays unit/static; existing reviewflow suite remains the owner for broad command catalog regressions. |
| TAP-02 | unit/domain decision service | A1/A2/A3/A4/A13/A14 local-session, official-footer remote marker, complete no-marker, true degraded/unavailable, metadata-only non-enabling degraded reasons, false-positive marker boundaries | `tests/_subsequent_review_unit_decision_unittest.py` | PR identity, completed-session list, and remote probe payloads crossing into typed decision object | Decision assertions show mode/enabled/reasons/counts/degraded flags, accept official CURe footer blocks in issue comments or pull review bodies regardless of author, reject generic human or body-only `CURe review` text without the footer as markers, distinguish complete negative from true unavailable/enabling failures, and assert metadata-only `discussion_incomplete` / `thread_state_unavailable` can auto-disable with degraded reasons. | In-memory PR/session fixtures and fake fetchers; no live network/db/filesystem; deterministic marker payload order; no cleanup beyond object scope. | `python -m pytest tests/_subsequent_review_unit_decision_unittest.py -q` | If marker normalization becomes a separate adapter, keep typed decision rules here and add adapter boundary tests rather than moving domain assertions into PR-flow integration. | Auto-inference rules are pure domain decisions and should not require PR-flow/filesystem setup. |
| TAP-03 | unit/domain GitHub marker/corpus boundary | A2/A13/A14 official-footer discussion evidence and degraded discussion metadata stays metadata-only | `tests/_subsequent_review_unit_github_history_unittest.py`; `tests/_subsequent_review_unit_prior_corpus_unittest.py` | GitHub comments/reviews/review-comments and author provenance crossing into discussion/corpus inputs consumed by decision/intake | Boundary assertions show issue comments and pull review bodies with official CURe footer blocks enter the prior corpus regardless of author, review comments are not positive markers/corpus entries, body-only/missing-author cases without the footer are explicit rejects, and thread-state absence remains metadata or degraded reason only. | Mocked remote payloads; no live network/db; fixture order deterministic; any filesystem use limited to temp/fixture reads with cleanup. | `python -m pytest tests/_subsequent_review_unit_github_history_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py -q` | If the remote probe bypasses Story 01 collectors, create a narrow marker-probe unit seam and keep corpus trust assertions separate. | Keeps remote data normalization/corpus trust rules separate from decision-service orchestration while still proving the shared boundary. |
| TAP-04 | functional/component decision artifacts + metadata | A7/A8/A9/A12 enabled, auto-disabled, and explicit-disabled new-sandbox artifact/meta visibility | `tests/_subsequent_review_functional_control_plane_unittest.py` plus relevant PR-flow artifact assertions in `tests/_subsequent_review_integration_pr_flow_unittest.py` | decision object and intake result crossing into `work/subsequent/decision.json`, manifest paths, and `meta.json.subsequent_review` | File-read assertions show decision JSON/meta mode, enabled state, reason summary, manifest/intake paths when enabled, and explicit absence of intake artifacts when disabled. | Temporary work dirs/sandboxes with cleanup; mocked intake; no live network/db; avoid exact timestamps to reduce flakiness. | `python -m pytest tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` | If metadata writing moves fully into session progress, retain component-level decision artifact assertions and add only a routing check at the new session seam. | Artifact semantics are component/integration behavior because they require filesystem and session metadata, but each assertion remains deterministic. |
| TAP-05 | integration/routing PR flow | A1/A3/A4/A5/A7/A8/A9/A10 new/fallback-new decisions, historical exits, intake called only when enabled, branch-safe artifact creation | `tests/_subsequent_review_integration_pr_flow_unittest.py` | `_pr_flow_impl` branch decisions after session/work-dir initialization crossing into decision/intake calls | Routing assertions show historical exits create no sandbox/artifacts, new/fallback branches decide after `work_dir` exists, intake is called only when the decision is enabled, degraded-enabled runs call intake, and auto/explicit disabled runs still record decision metadata. | Temporary sandbox/cache roots with cleanup; mock GitHub/config/chunkhound; no live network/db; isolate prompt/input state per branch test. | `python -m pytest tests/_subsequent_review_integration_pr_flow_unittest.py -q` | If `_pr_flow_impl` is decomposed, preserve one public orchestration proof at the new route and return material lifecycle/routing drift to planning. | Branch-safety requires real orchestration seams and belongs in integration-style tests, not in decision unit tests. |
| TAP-06 | integration/resource lifecycle failure injection | A15 post-session-init failures from decision, decision artifact write, and enabled intake/artifact write persist `meta.json.status = "error"` | `tests/_subsequent_review_integration_pr_flow_unittest.py` | exceptions crossing the `SessionProgress.init` -> preflight decision/intake lifecycle boundary | Failure-injection assertions show `meta.json.status = "error"`, cause/detail persists, common session artifacts remain inspectable when expected, and no run is left stale/running. | Temporary sessions with cleanup; patched failing seams; no live network/db; filesystem assertions scoped to sandbox root; each failure case isolated to avoid ordering flake. | `python -m pytest tests/_subsequent_review_integration_pr_flow_unittest.py -q` | If preflight lifecycle handling becomes a shared helper, move the same post-init error-status proof to that helper plus one `_pr_flow_impl` routing smoke test. | Failure lifecycle is routing/filesystem integration and must stay separate from pure decision tests. |
| TAP-07 | public wrapper + broad regression | Public discovery compatibility and adjacent reviewflow regressions after the two-state command decision | `tests/test_subsequent_review.py`; `tests/_subsequent_review_unittest.py`; `tests/test_reviewflow_unittest.py` | pytest/unittest discovery and existing reviewflow runtime behavior | Wrapper run discovers all private Story 01/02 split modules; reviewflow regression still passes; broad full-suite run is optional safety, not the only proof for any acceptance row. | Thin wrapper imports private split modules; no extra live network/db/filesystem fixtures; broad suite relies on existing test isolation; order/flakiness failures indicate wrapper or global-state regression. | `python -m pytest tests/test_subsequent_review.py -q`; `python -m pytest tests/test_reviewflow_unittest.py -q`; full `python -m pytest -q` when practical | If repo discovery convention changes, record the new public discovery surface and keep lower-layer TAP rows as behavior owners. | Existing repo convention keeps a public wrapper while private modules split unit/functional/integration concerns. |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|---|---|---|---|---|---|---|
| A1 | provisional | automated + file-read | Run `_pr_flow_impl` fixture with completed sessions and default args | Auto decision enabled with completed-session counts; intake called after `work_dir` exists; meta/decision/manifest paths recorded | TAP-02/TAP-04/TAP-05; `cure.py:_pr_flow_impl`, new decision service, `tests/test_subsequent_review.py` | Exact test helper names set red-first |
| A2 | provisional | automated + file-read | Mock remote issue-comment and pull-review-body probes with official CURe footer blocks, human/operator authors, and no local sessions | Auto decision enabled with remote marker reason; intake called; prior corpus admits the footer-bearing remote event regardless of author | TAP-02/TAP-03/TAP-05; decision service, GitHub list/probe seam, prior corpus seam | Exact footer-helper/function name set during implementation |
| A3 | provisional | automated + file-read | Mock no local sessions and complete remote probe with no markers | Auto decision disabled; decision artifact/meta written; no intake files beyond decision | TAP-02/TAP-04/TAP-05; decision service, `SessionProgress` meta | Exact null vs absent manifest-path representation to be locked red-first |
| A4 | provisional | automated + file-read | Mock no local sessions and remote fetch exception / truly unavailable probe | Auto decision enabled in degraded mode; intake called; degraded reason visible | TAP-02/TAP-04/TAP-05; decision service, Story 01 degraded intake | Remote unavailable/degraded reason spelling to be locked red-first |
| A5 | provisional | automated + file-read | Run with `--no-subsequent-review` and positive prior signals | Mode disabled; decision artifact/meta; intake mock not called | TAP-01/TAP-04/TAP-05; parser, `_pr_flow_impl`, decision service | Exact disabled-mode namespace and decision schema keys to lock red-first |
| A6 | provisional | automated + CLI/help inspection | Parse/help/catalog tests around `--subsequent-review` | No supported force-enable state; clear rejection or absence; catalog points to default auto / opt-out | TAP-01; `cure.py:build_parser`, command catalog tests | Implementation chooses remove vs explicit parser error |
| A7 | provisional | automated + file-read | Inspect enabled fixture sandbox files | Decision plus Story 01 artifacts exist; paths recorded | TAP-04/TAP-05; `work/subsequent/*`, `meta.json` | Existing manifest schema may be extended but must stay readable |
| A8 | provisional | automated + file-read | Inspect auto-disabled fixture sandbox files | Decision artifact/meta explain disabled; no intake artifacts | TAP-04/TAP-05; decision writer, meta writer | Exact auto-disabled decision artifact schema and manifest-path nullability to lock red-first |
| A9 | provisional | automated + file-read | Inspect explicit-disabled fixture sandbox files | Decision artifact/meta explain operator opt-out; intake not called | TAP-04/TAP-05; parser, decision writer, meta writer | Exact explicit-disabled reason string/schema keys to lock red-first |
| A10 | provisional | automated | Re-run list/latest/prompt-selected/new/fallback branch tests | Historical exits create no sandbox/artifacts; new/fallback branches decide after work dir | TAP-05; `_pr_flow_impl`, historical session branch tests | Prompt-selected test may reuse Story 01 harness |
| A11 | final | automated | Contract/parser tests inspect evidence policy choices | Only `trusted`/`untrusted`; mode is separate `auto`/`disabled` metadata | TAP-01/TAP-02; `EvidencePolicy`, parser choices, decision schema | — |
| A12 | provisional | automated + log capture | Capture stderr/log summary in enabled/disabled runs | User-visible line includes mode, enabled state, and reason summary | TAP-04/TAP-05; `_pr_flow_impl`, decision service summary | Exact wording not important; fields are |
| A13 | provisional | automated + file-read | Mock complete remote payloads with generic human comments, human/allowlisted `CURe review` text without the footer, missing-author body-only text, review-comment line comments, spoofed logins, resolved/unresolved thread state, and missing thread-state metadata | `remote_cure_markers=0`; no `cure_pr_discussion_found`; no remote corpus entry; complete no-marker probes auto-disable with decision metadata only | TAP-02/TAP-03; decision service marker classifier, `github_history` normalization, corpus admission seam | Official footer matcher set red-first; broad/body-only text without the footer is not sufficient |
| A14 | provisional | automated + file-read | Mock remote exceptions/enabling incomplete payloads plus metadata-only `discussion_incomplete` / `thread_state_unavailable` shapes | True unavailable/enabling failures are degraded-enabled; metadata-only reasons with zero official-footer markers auto-disable with `no_prior_review_signals`; all variants record degraded reasons and no footer-marker reason | TAP-02/TAP-03/TAP-05; decision service, GitHub list/probe seam, Story 01 degraded intake | Distinguish true unavailable/enabling incomplete from non-enabling metadata-only degraded probes |
| A15 | provisional | automated + file-read | Inject exceptions from `decide_subsequent_review`, `write_decision_artifact`, and enabled intake/artifact write seams after `SessionProgress.init` | `meta.json.status = "error"` and error cause persisted; no orphaned `running` session | TAP-06; `_pr_flow_impl`, `SessionProgress.error`, `meta.write_json`, intake control plane | May require moving guard earlier or wrapping preflight in shared lifecycle helper |

### Surface / Branch Proof Matrix

| Surface | Supported Variant | Internal Execution Branch | Proof Class | Owning Proof Seam | Why This Seam Is Sufficient | Out of Scope Notes |
|---|---|---|---|---|---|---|
| CLI parser | default omitted flag | `subsequent_review_mode="auto"` or equivalent typed state | routing | A1/A3 parser assertions | Proves command-state routing defaults to auto, not false/off | Naming may differ if namespace avoids new enum |
| CLI parser | `--no-subsequent-review` | explicit disabled state | routing | A5 parser/runtime test | Proves opt-out routing remains | Not an evidence-policy toggle |
| CLI parser | `--subsequent-review` | rejected/unsupported | behavior | A6 parser/help/catalog tests | Proves no force-enable state | Compatibility is explicit error, not silent alias |
| Decision service | local completed sessions | auto-enabled | behavior | A1 | Fast local signal proves subsequent run | Later source verification deferred |
| Decision service | official-footer remote CURe PR marker in issue comment / pull review body | auto-enabled | behavior | A2 | Covers PR-comment-only prior history, including operator-authored CURe reviews, without accepting body-only human text | Marker is only intake trigger, not source truth |
| Decision service | no local sessions + complete no-marker remote probe | auto-disabled | behavior | A3/A13 | Proves first-run path is not over-eager, including generic comments and CURe-looking body text without the official footer | No Story 01 intake needed; decision artifact remains |
| Decision service | remote probe unavailable / transport exception / enabling fetch failure | auto-enabled degraded | behavior | A4/A14 | Avoids silently missing prior remote CURe comments when the probe cannot run or fails materially, while keeping uncertainty explicit; this is the conservative/fail-closed branch | Degraded semantics remain Story 01 intake status |
| Decision service | metadata-only `discussion_incomplete` / `thread_state_unavailable` without official-footer marker | no positive marker; auto-disabled with degraded reasons | behavior | A13/A14 | Proves metadata absence is not evidence of prior CURe review and that non-enabling degraded metadata does not force intake | Thread-state semantics remain later-story discussion analysis |
| Runtime integration | auto-enabled new sandbox | decision then Story 01 intake | routing | A7 | Proves old intake still runs with config enabled | Semantic modules still disabled per Story 01 |
| Runtime integration | auto-disabled / explicit-disabled new sandbox | decision only | routing | A8/A9 | Proves artifact absence is explicit | No intake module execution |
| Runtime integration | historical exits | no new artifacts | routing | A10 | Preserves `--if-reviewed` compatibility | No decision file because no new run exists |
| Metadata/artifacts | all new-sandbox runs | `meta.json` + `decision.json` | behavior | A7-A9 | Prevents ambiguous absence of `work/subsequent` files; persistence assertions are the observable behavior | Exact schema locked in tests |
| Runtime lifecycle | post-init decision/intake preflight exceptions | `meta.json.status = "error"` before exit | behavior | A15 | Prevents orphaned running sessions from preflight failures; lifecycle persistence is the observable behavior | Does not require swallowing exceptions or continuing review |

### Input Boundary Shape Risk

| Boundary | Raw Input Source | Strict Assumption | Variant / Case | Evidence | Mitigation / Exclusion |
|---|---|---|---|---|---|
| Args namespace -> command mode | argparse output | Exactly `auto` or `disabled` reaches runtime | omitted flag, opt-out flag, obsolete force flag | A5/A6 parser tests | Unknown/obsolete force flag rejects loudly |
| Completed sessions -> local signal | `scan_completed_sessions_for_pr` result | Countable completed sessions are a positive signal | none, one, many, session with prior subsequent artifacts | A1/A3 tests | Session content does not prove source state; it only enables intake |
| Remote discussion probe -> marker signal | GitHub list/probe payloads | Only official CURe footer blocks in issue comments or pull review bodies are positive remote prior-CURe markers | issue comment with footer, pull review body with footer, review comment, generic human comment, CURe-looking body without footer, missing author, malformed payload, transport exception, incomplete pagination | A2/A3/A13/A14 tests | Generic comments, body-only CURe-looking text, and author/login identity without the official footer never enable; true unavailable/enabling incomplete is degraded-enabled, while metadata-only `discussion_incomplete` can auto-disable with degraded reasons |
| Review thread metadata -> marker/degraded state | GitHub review-comment payload fields | Thread state is metadata, not authorship/provenance | resolved, unresolved, unknown, missing thread_state/threadState/thread.state | A13/A14 tests | Missing thread state may be a non-enabling degraded reason; it is never a positive prior-review marker |
| Decision object -> JSON artifact | dataclass/dict serialization | Stable JSON with mode/enabled/reasons/counts/degraded | auto-enabled, auto-disabled, explicit-disabled, degraded uncertainty, false-positive negative | A7-A9/A13-A14 file reads | Avoid exact timestamp assertions; assert required keys and values |
| Decision metadata -> session meta | `SessionProgress`/JSON writer | Meta records decision for every new sandbox and marks post-init failures as error | enabled, disabled, auto-disabled, intake failure before/after decision, decision write failure | A7-A9/A15 tests | If intake later fails, decision remains inspectable when written; if decision write fails, status still becomes error |
| Existing intake config -> Story 01 control plane | `SubsequentReviewConfig` | Intake only runs when decision enabled | enabled, disabled, degraded-enabled, intake artifact write exception | A4/A5/A7/A15 tests | Does not alter module evidence semantics |
| Post-init preflight lifecycle | `_pr_flow_impl` after `progress.init` | Any exception after session metadata exists is recorded through `progress.error` | decision failure, decision artifact write failure, enabled intake/artifact write failure | A15 tests | Preserve failure cause; do not leave stale `running` |

### Fail-open Checks

| Check | Proof Method | Expected Evidence |
|---|---|---|
| Default omitted flag accidentally remains disabled with no meta | Automated + file-read | Every new-sandbox run has `meta.json.subsequent_review.mode = "auto"` unless explicit disabled |
| Obsolete `--subsequent-review` silently acts as force-enable | Parser/help/catalog tests | Flag absent/rejected; no runtime force-enable path |
| No local sessions + remote unavailable/exception silently auto-disables | Automated degraded test | Decision is enabled with degraded reason and intake artifacts expose true probe unavailability |
| Auto-disabled path leaves ambiguous missing artifacts | File-read | `work/subsequent/decision.json` and `meta.json.subsequent_review` explain why intake files are absent |
| Explicit disabled still calls intake | Mocked intake assertion | `run_subsequent_review_intake` is not called |
| Historical exits create decision artifacts | Branch tests | No sandbox/work/decision artifacts for list/latest/prompt-selected history |
| Evidence policy accidentally gains mode-like value | Contract/parser tests | `EvidencePolicy` remains exactly `trusted`, `untrusted` |
| Generic PR discussion enables intake | Automated marker-negative test | Complete probe with generic comments records auto-disabled/no markers |
| CURe-looking body text without the official footer becomes a positive marker | Automated marker-negative test | Complete probe with human-authored, allowlisted-author, spoofed-author, or missing-author `CURe review` body without `<!-- CURE_REVIEW_FOOTER_START -->` / `<!-- CURE_REVIEW_FOOTER_END -->` records `remote_cure_markers=0`, no `cure_pr_discussion_found`, no remote corpus entry, and auto-disabled/no markers |
| Missing thread-state metadata becomes a positive marker or force-enables intake | Automated marker-negative/degraded test | Missing thread-state records no positive marker; if it is the only degraded reason, decision may auto-disable with `no_prior_review_signals` while preserving the degraded reason |
| Post-init preflight exception leaves session running | Failure-injection file-read | Forced failures in decision, decision artifact write, and enabled intake/artifact write persist `meta.json.status = "error"` with cause |

### Risk Lens Inventory

| Risk Lens | Activated By | Planning / Proof Obligation | Owner Surface | Exclusion / Rationale |
|---|---|---|---|---|
| Command routing / backwards compatibility | Replacing explicit opt-in with default auto and opt-out | Prove parser/help/catalog and all `--if-reviewed` branches | `cure.py:build_parser`, `_pr_flow_impl`, command catalog | Covered by A5/A6/A10 |
| State / artifact ambiguity | Disabled paths previously created no subsequent artifacts | Persist decision artifact/meta for every new-sandbox run | decision service, `SessionProgress` meta | Covered by A7-A9 |
| External service / incomplete data | Remote PR discussion may be needed to infer PR-comment-only history | Prove complete/no-marker, marker, true unavailable/enabling incomplete, and metadata-only non-enabling variants such as `discussion_incomplete` / `thread_state_unavailable` | remote probe/fetcher seam | Covered by A2-A4/A13-A14; live GitHub not required |
| False positives | Generic comments, CURe-looking body text without the official footer, author/login identity, review-comment line comments, or thread-state metadata could be mistaken for prior CURe review | Marker-negative tests; exact positive trigger is the official footer block on issue-comment / pull-review bodies | decision service marker logic; prior corpus admission | Discussion semantics remain later scope |
| False negatives | Real CURe reviews may be posted by a human/operator account rather than a bot account | Footer-positive tests with human/operator authors for both decision enablement and prior-corpus ingestion | shared remote marker predicate; prior corpus admission | Official footer block is the durable CURe provenance marker |
| Evidence policy confusion | Command mode might be conflated with `trusted`/`untrusted` | Contract tests keep policy values fixed; schema separates mode | `EvidencePolicy`, parser, decision schema | Covered by A11 |
| Large-file coupling | `_pr_flow_impl` and parser are in `cure.py` | Extract decision logic to focused package module; keep `cure.py` as orchestrator | `cure_subsequent_review/decision.py` | DDD/small-module obligation |
| Resource lifecycle / fail-open persistence | Decision/intake preflight runs after session init but before the main guarded review flow | Wrap or move preflight so failures call `progress.error(...)` and leave auditable `meta.json.status = "error"` | `_pr_flow_impl`, `SessionProgress`, decision/intake writers | Covered by A15 |

## Discovery Notes

- Source recon found `build_parser` currently defines a mutually exclusive `--subsequent-review` / `--no-subsequent-review` group with `dest="subsequent_review"` and default `False` in `projects/CURe/cure.py:15455-15485`.
- `_subsequent_review_enabled(args)` currently returns a bool from `args.subsequent_review` and defaults false in `projects/CURe/cure.py:7471-7479`.
- `_pr_flow_impl` currently invokes `run_subsequent_review_intake` only under the boolean opt-in and records `subsequent_review` meta only when an intake result exists in `projects/CURe/cure.py:9544-9606`.
- Story 01 control-plane disabled mode deliberately returns `None` and creates no `work/subsequent` directory in `projects/CURe/cure_subsequent_review/control_plane.py:93-119`; Story 02 should write decision metadata outside disabled intake.
- Existing tests in `projects/CURe/tests/test_subsequent_review.py` cover Story 01 artifacts, historical list exits, and enabled new-run intake but currently use `--subsequent-review`; they are natural red-first update points for default auto.
- FB-002 replan source recon: current `decide_subsequent_review` counts `remote_cure_markers` with `_looks_cure_authored(...)` and enables on `cure_pr_discussion_found` in `projects/CURe/cure_subsequent_review/decision.py:135-151`; historical `_looks_cure_authored` body/login behavior left CURe-looking human text and missing thread-state metadata unproven.
- FB-002 replan source recon: `collect_pr_discussion` treats missing/unknown thread-state shapes as `thread_state_unavailable` in `projects/CURe/cure_subsequent_review/github_history.py:38-47` and appends that reason for review comments in `projects/CURe/cure_subsequent_review/github_history.py:103-106`; Story 02 proof must ensure metadata absence is not a positive prior-review marker and remains a non-enabling degraded reason unless paired with broader remote probe unavailability.
- FB-003 replan source recon: `_pr_flow_impl` writes `meta.json.status = running` through `SessionProgress.init` in `projects/CURe/cure.py:9530-9589` / `:2839-2855`, then calls `decide_subsequent_review`, `write_decision_artifact`, and enabled `run_subsequent_review_intake` at `projects/CURe/cure.py:9602-9628`; the broad `progress.error(...)` handler is later at `projects/CURe/cure.py:10615-10624`, so failure-injection proof must cover the post-init preflight block explicitly.
- FB-026 source recon: `cure_output.py:1547-1549` writes the official review footer markers; current `decision.py:82-85` only counts issue comments and pull review bodies through `_looks_cure_authored`; current `prior_corpus.py:28-41` requires an allowlisted CURe author plus CURe-looking body and `prior_corpus.py:107-123` uses the same predicate for issue-comment / pull-review corpus admission. The amended plan makes the official footer block the shared positive marker regardless of author while preserving review-comment exclusion and body-only spoof rejection.

## Critical Files

| File | Role |
|---|---|
| `projects/CURe/cure.py:7471-7479` | Current `_subsequent_review_enabled` / `_subsequent_review_evidence_policy` helpers use boolean opt-in plus two evidence policies; helper behavior must change to two command modes without adding evidence policies. |
| `projects/CURe/cure.py:9544-9606` | `_pr_flow_impl` currently records common options, writes `pr_context.json`, then runs intake only when the boolean opt-in is true and records manifest/meta only on enabled runs. Story 02 changes this branch to decide+persist for every new sandbox. |
| `projects/CURe/cure.py:15455-15485` | Current parser exposes `--subsequent-review`, `--no-subsequent-review`, and evidence-policy choices; Story 02 removes/rejects force-enable and makes omitted flag mean auto. |
| `projects/CURe/cure_subsequent_review/control_plane.py:34-43` | `SubsequentReviewConfig(enabled, evidence_policy, module_overrides)` remains the enabled-intake config consumed after the new decision service says enabled. |
| `projects/CURe/cure_subsequent_review/control_plane.py:93-119` | `run_subsequent_review_intake` is currently a no-op when config is disabled and creates no `work/subsequent`; Story 02 should avoid calling it for disabled decisions and write decision metadata separately. |
| `projects/CURe/cure_subsequent_review/decision.py:88-92`, `:167-181` | Current auto decision limits positive markers to trusted issue comments/reviews and treats `discussion_incomplete` / `thread_state_unavailable` as non-enabling metadata-only degraded reasons; Story 02 proof must preserve that false-positive mitigation while keeping true unavailable/enabling degraded probes explicit. |
| `projects/CURe/cure_subsequent_review/decision.py:171-174` | `write_decision_artifact` writes `work/subsequent/decision.json`; FB-003 failure-injection must prove exceptions here mark session status `error`. |
| `projects/CURe/cure_subsequent_review/decision.py` | Focused domain service for command mode, inference signals, decision JSON, and summary text. |
| `projects/CURe/tests/_subsequent_review_unit_contracts_cli_unittest.py` | Command-mode/parser/catalog-facing contract tests for default auto, explicit disabled, obsolete force flag rejection, and evidence-policy separation. |
| `projects/CURe/tests/_subsequent_review_unit_decision_unittest.py` | Decision-service unit tests for local sessions, official-footer remote markers, complete no-marker probes, true degraded-enabled probes, metadata-only non-enabling degraded probes, and false-positive marker boundaries. |
| `projects/CURe/tests/_subsequent_review_functional_control_plane_unittest.py` | Functional artifact/control-plane coverage for decision/intake status propagation and manifest behavior. |
| `projects/CURe/tests/_subsequent_review_integration_pr_flow_unittest.py` | `_pr_flow_impl` branch, new-sandbox decision/artifact routing, historical exit, and post-init failure-injection coverage. |
| `projects/CURe/tests/_reviewflow_unittest_prompt_session_impl.py` | Command catalog JSON/human output tests may need updates so agent-facing help documents default auto and opt-out only. |
| `projects/CURe/meta.py:82-86` | Atomic JSON write helper suitable for `work/subsequent/decision.json`; failure injection should include this writer path and assert session meta is still marked `error`. |
| `projects/CURe/cure_output.py:1547-1549` | Existing review artifact writer emits the official `CURE_REVIEW_FOOTER_START` / `CURE_REVIEW_FOOTER_END` footer block; FB-026 makes that block the durable remote prior-CURe marker. |
| `projects/CURe/cure_subsequent_review/prior_corpus.py:28-41`, `:107-123` | Current `_looks_cure_authored` requires allowlisted CURe author plus CURe-looking body for issue-comment / pull-review corpus admission; FB-026 changes the shared remote predicate so official footer blocks are sufficient regardless of author while body-only text remains rejected. |
| `projects/CURe/cure_subsequent_review/github_history.py:38-47` | Thread-state normalization returns `thread_state_unavailable` for missing/unknown shapes; FB-002 requires this be degraded metadata, not positive prior-review evidence. |
| `projects/CURe/cure.py:9592-9628` | Current post-init decision/intake preflight calls `decide_subsequent_review`, `write_decision_artifact`, and enabled `run_subsequent_review_intake` before the later broad review-flow `try`; FB-003 requires lifecycle guard/error status around this block. |
| `projects/CURe/cure.py:10615-10624` | Existing broad exception handler calls `progress.error(...)` later in the run; FB-003 can reuse or move this semantics to cover post-init preflight failures. |

## Implementation Notes

Recommended red-first sequence:

1. Parser/command-mode tests: assert omitted flag parses/normalizes to auto; `--no-subsequent-review` parses/normalizes to disabled; `--subsequent-review` is rejected or absent; evidence-policy choices remain `trusted|untrusted`.
2. Decision-service unit tests: drive local-session, official-footer remote-marker, no-marker, remote-unavailable, and explicit-disabled cases without invoking `_pr_flow_impl`.
3. Runtime branch tests: update Story 01 `_pr_flow_impl` tests so default auto replaces `--subsequent-review`; assert decision is persisted before/alongside enabled intake, and explicit disabled never calls intake.
4. Artifact/meta schema tests: fixture-read `meta.json` and `work/subsequent/decision.json` for auto-enabled, auto-disabled, explicit-disabled runs.
5. Command catalog/help tests: ensure recommended invocations do not teach `--subsequent-review` and do explain `--no-subsequent-review`.
6. FB-002/FB-026 marker-boundary tests: drive complete remote probes with official-footer issue comments and pull review bodies authored by a human/operator account; assert they increment `remote_cure_markers`, set `cure_pr_discussion_found`, run intake, and enter the prior corpus. Drive generic human comments, human/allowlisted/spoofed `CURe review` body text without the official footer, missing-author/body-only markers, review-comment line comments, resolved/unresolved thread-state metadata, and missing thread-state metadata; assert zero positive markers and no remote corpus entries unless an issue comment or pull review body contains the official footer. Separately assert true remote unavailable/exceptions or enabling incomplete probes are degraded-enabled with explicit reasons, while metadata-only `discussion_incomplete` / `thread_state_unavailable` can auto-disable with degraded reasons and no markers.
7. FB-003 lifecycle tests: inject failures from `decide_subsequent_review`, `write_decision_artifact`/`meta.write_json`, and enabled `run_subsequent_review_intake`/artifact writes after `SessionProgress.init`; assert `meta.json.status = "error"`, error cause, and no stale `running` session.
8. Focused/regression/hygiene commands: `tests.test_subsequent_review`, `tests.test_reviewflow_unittest`, `ruff check .`, `mypy`.

Implementation should keep `cure.py` changes limited to parser normalization, invoking the decision service after the new sandbox work dir exists, writing meta paths, and calling the existing Story 01 intake only when the decision is enabled.

## Locked Decisions

- Subsequent-review command mode has exactly two states: `auto` and `disabled`.
- Omitted flag means `auto`.
- `--no-subsequent-review` is the only explicit command-mode override and means disabled.
- No force-enable state is introduced; `--subsequent-review` must not silently force intake.
- Auto-disabled and explicit-disabled new-sandbox runs must write explicit decision metadata/artifact.
- Auto does not alter the evidence policy model; evidence policy remains exactly `trusted` or `untrusted`.
- True remote probe unavailability, exceptions, or enabling fetch/pagination failures are conservative degraded-enabled; metadata-only `discussion_incomplete` / `thread_state_unavailable` with zero official-footer markers are non-enabling degraded reasons that may auto-disable with `no_prior_review_signals` while remaining visible.
- Official CURe review footer blocks (`<!-- CURE_REVIEW_FOOTER_START -->` ... `<!-- CURE_REVIEW_FOOTER_END -->`) in GitHub issue comments or pull review bodies are sufficient positive prior-CURe-review evidence for auto-decision and prior-corpus ingestion regardless of author/login.
- Generic/untrusted GitHub discussion, CURe-looking body text without the official footer, spoofed or allowlisted author/login text without the footer, review-comment line comments, and thread-state metadata/missing metadata are not positive prior-CURe-review evidence.
- Post-session-init decision/intake failures must leave `meta.json.status = "error"`, not `running`.

## Plan Review Log

- 2026-06-04 — plan-review decision: approved. The plan is implementable and source-grounded against current parser/runtime/control-plane/test seams; it preserves FB-001's two command states (`auto` default, explicit `disabled`, no force-enable), keeps evidence policy limited to `trusted|untrusted`, requires explicit decision metadata for all new-sandbox runs, preserves historical `--if-reviewed` exits, and excludes later semantic/report-governor source-truth scope.
- 2026-06-04 — supplemental risk-lens pass: approved; activated lenses are command routing/backwards compatibility, state/artifact ambiguity, external service/incomplete data, false positives, evidence-policy confusion, and large-file coupling. Each has an explicit proof obligation in the Risk Lens Inventory and is covered by the acceptance/proof/fail-open matrices.
- 2026-06-04T15:45:00Z Plan feedback addressed by `/epic-story-plan-resume`
  - Decision: replan complete; ready for fresh plan-review
  - Plan lane transition: 🟢 PLAN APPROVED -> 🟡 PLAN DRAFT
  - Status transition: unchanged: ✅ DONE -> ✅ DONE
  - Changes: Added explicit FB-002 obligations that generic/untrusted discussion, CURe-looking human body text, and missing thread-state metadata cannot count as positive prior-CURe-review evidence; preserved remote unavailable/incomplete as explicit degraded-enabled uncertainty. Added explicit FB-003 obligations and failure-injection proof around `decide_subsequent_review`, `write_decision_artifact`, and enabled intake/artifact writes so post-session-init exceptions mark `meta.json.status = "error"`.
  - Risk lenses activated: false positives, external-service incomplete data, evidence-policy confusion, state/artifact ambiguity, resource lifecycle / fail-open persistence.
  - Next action: run `/epic-story-plan-review cure-subsequent-pr-review 02` from a fresh session. Do not start `/epic-story-resume` implementation work until the Plan lane is approved again.
- 2026-06-04 — plan-review decision: approved after FB-002/FB-003 replan. The amended plan fully covers false-positive remote marker boundaries (generic/untrusted discussion, CURe-looking human body text, missing author, resolved/unresolved thread metadata, and missing thread-state metadata are not positive prior-CURe-review markers) while preserving unavailable/incomplete remote probes as explicit degraded-enabled uncertainty. It also adds lifecycle/failure-injection proof for post-`SessionProgress.init` exceptions from `decide_subsequent_review`, `write_decision_artifact`/`meta.write_json`, and enabled `run_subsequent_review_intake`/artifact writes so `meta.json.status = "error"` is persisted before exit.
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED
  - Status transition: unchanged: ✅ DONE -> ✅ DONE
  - Risk lenses reviewed/activated: false positives, external-service incomplete data, evidence-policy confusion, state/artifact ambiguity, resource lifecycle / fail-open persistence.
  - Next action: `/epic-story-resume cure-subsequent-pr-review 02` may proceed to implementation hardening for FB-002/FB-003.

- 2026-06-07T05:34:05Z Operator-directed plan invalidation after TAP quality-lens contract edits
  - Decision: re-review required; plan ready for fresh `/epic-story-plan-review`
  - Plan lane transition: 🟢 PLAN APPROVED -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: ✅ DONE -> 🟣 IN REVIEW
  - Changes: TAP table updated to the current quality-lens columns with assertions/observability and fallback plans; provisional APM rows A5/A8/A9 now have concrete Open Detail; Surface/Branch proof classes normalized to allowed values.
  - Next action: run `/epic-story-plan-review cure-subsequent-pr-review 02` and `/epic-story-review cure-subsequent-pr-review 02` from fresh sessions.

- 2026-06-07T07:33:13Z Plan review run by fresh maintainer session
  - Verdict: request_changes
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: unchanged: 🟣 IN REVIEW -> 🟣 IN REVIEW
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: AGENTS.md, epic MASTER.md FB-001/Story 02 row, Story 01 dependency contract, Story 02 current contract; no CONTRACT.md present
  - Traceability: forward gaps; backward complete
  - Test architecture: complete; TAP rows covered, with no new TAP quality-lens row gap found
  - Design trace: not applicable
  - Code surfaces searched: `projects/CURe/cure.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/meta.py`, focused `tests/_subsequent_review_*` suites, `tests/test_subsequent_review.py`, `tests/test_reviewflow_unittest.py`
  - Risk lenses reviewed: command routing/backwards compatibility; state/artifact ambiguity; external-service incomplete data; false positives / trusted remote marker boundary; evidence-policy confusion; resource lifecycle / fail-open persistence; dirty-worktree warning noted but not a planning blocker
  - Evidence quality: confirmed Story 02 scenario/proof-shape gap and current TAP-quality coverage; inferred no material original-intent conflict from MASTER/Story 01/Story 02; unknown external PR/ticket intent beyond recorded feedback logs; provisional live-code line numbers because product worktree currently has unrelated in-progress Story 01 changes
  - Key findings:
    - [request_changes] [Scenarios / Behavior Examples] Normative scenarios still map one scenario to multiple acceptance ids, but the current planning contract requires every normative `S<n>` scenario to include exactly one `Covers: A<n>` link. Split or reshape S1 (`A1, A7`), S2 (`A2, A7`), S3 (`A3, A8`), S4 (`A4, A7, A14`), S5 (`A5, A9`), S8 (`A1, A10`), S9 (`A3, A13`), and S10 (`A13, A14`) so each scenario has a single acceptance cover while preserving the existing APM/TAP coverage.
  - Hypothesis triage: suspicious surface: scenario-to-acceptance funnel; tentative issue: multi-acceptance scenarios make acceptance traceability unauditable despite otherwise complete TAP/APM; next proof target: Story 02 Scenarios section after plan-resume split
  - Debt Friction: none
  - Next action: `/epic-story-plan-resume cure-subsequent-pr-review 02` to split/reshape the multi-cover scenarios, then re-run `/epic-story-plan-review cure-subsequent-pr-review 02` from a fresh session

- 2026-06-07T07:37:37Z Plan feedback addressed by `/epic-story-plan-resume`
  - Decision: replan complete; ready for fresh plan-review
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Status transition: unchanged: 🟣 IN REVIEW -> 🟣 IN REVIEW
  - Changes: Split/reshaped Scenarios / Behavior Examples so each normative `S<n>` row has exactly one `Covers: A<n>` link. Added one-to-one scenario rows for A1-A15, preserving the prior local/remote/degraded/disabled/historical-exit/failure-lifecycle behavior and keeping TAP/APM coverage unchanged.
  - Risk lenses preserved: command routing/backwards compatibility; state/artifact ambiguity; external-service incomplete data; false positives / trusted remote marker boundary; evidence-policy confusion; resource lifecycle / fail-open persistence.
  - Next action: run `/epic-story-plan-review cure-subsequent-pr-review 02` from a fresh session.

- 2026-06-07T07:42:24Z Plan review run by fresh maintainer session
  - Verdict: request_changes
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: unchanged: 🟣 IN REVIEW -> 🟣 IN REVIEW
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: AGENTS.md, epic MASTER.md FB-001/Story 02 row, Story 01 dependency contract, Story 02 current contract and prior review/resume log; no CONTRACT.md present
  - Traceability: forward gaps; backward gaps
  - Test architecture: gaps; TAP rows present but A4/A14 proof expectations conflict with live decision-service/test behavior for incomplete remote probes
  - Design trace: not applicable
  - Code surfaces searched: `projects/CURe/cure.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/meta.py`, focused `tests/_subsequent_review_*` suites, `tests/test_subsequent_review.py`, `tests/test_reviewflow_unittest.py`
  - Risk lenses reviewed: command routing/backwards compatibility; state/artifact ambiguity; external-service incomplete data; false positives / trusted remote marker boundary; evidence-policy confusion; resource lifecycle / fail-open persistence; dirty-worktree warning noted but not a planning blocker
  - Evidence quality: confirmed Story 02 scenario split is now one `Covers: A<n>` per S1-S15; confirmed contract/code/test conflict around `discussion_incomplete` and `thread_state_unavailable`; inferred no material issue in the TAP quality-lens columns themselves; unknown external PR/ticket intent beyond recorded feedback logs; provisional whether implementation or contract should win because the story does not record an explicit reopen/scope-deviation decision for this behavior drift
  - Key findings:
    - [request_changes] [Acceptance / Verification / Locked Decisions] The plan still says remote unavailable/incomplete probes are conservative degraded-enabled and run intake, including A4/A14 and the A14 APM row, but the live decision service treats `discussion_incomplete` and `thread_state_unavailable` as non-enabling metadata-only degraded reasons and the focused unit test asserts a `discussion_incomplete` public-fallback-empty probe returns `enabled=false` with `no_prior_review_signals`. Align S4, A4, A14, TAP-02/TAP-05/APM A14, Fail-open Checks, Risk Lens Inventory, and Locked Decisions with the current code/test behavior, or record an explicit reopen decision to change the implementation. Sources: story S4/A4/A14 at this file:64, :82, :92, APM A14 at :134, Locked Decisions at :242; live behavior in `projects/CURe/cure_subsequent_review/decision.py:88-92`, `:167-181`; test expectation in `projects/CURe/tests/_subsequent_review_unit_decision_unittest.py:50-65`.
  - Hypothesis triage: suspicious surface: external-service degraded decision boundary; tentative issue: the plan's broad "incomplete means enabled" contract would overwrite the current false-positive mitigation for metadata-only incomplete remote probes; next proof target: revised Story 02 Acceptance/Verification wording plus decision-service tests after plan-resume
  - Debt Friction: none
  - Next action: `/epic-story-plan-resume cure-subsequent-pr-review 02` to reconcile the A4/A14 incomplete-remote contract with current decision-service behavior, then re-run `/epic-story-plan-review cure-subsequent-pr-review 02` from a fresh session

- 2026-06-07T07:47:37Z Plan feedback addressed by `/epic-story-plan-resume`
  - Decision: replan complete; ready for fresh plan-review
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Status transition: unchanged: 🟣 IN REVIEW -> 🟣 IN REVIEW
  - Changes: Reconciled A4/A14 degraded-remote wording with current decision-service behavior. The plan now distinguishes true remote unavailability/exceptions or enabling fetch failures, which are degraded-enabled and run intake, from metadata-only `discussion_incomplete` / `thread_state_unavailable` with zero trusted markers, which are non-enabling degraded reasons that may auto-disable with `no_prior_review_signals` while remaining visible in decision metadata. Updated Scope, S4/S14, A4/A14, TAP-02/TAP-05, APM A4/A14, Surface/Branch, Input Boundary, Fail-open Checks, Risk Lens Inventory, Implementation Notes, Locked Decisions, and Discovery Notes. No implementation reopen was recorded.
  - Risk lenses preserved: external-service incomplete data; false positives / trusted remote marker boundary; state/artifact ambiguity; command routing/backwards compatibility; evidence-policy confusion; resource lifecycle / fail-open persistence.
  - Next action: run `/epic-story-plan-review cure-subsequent-pr-review 02` from a fresh session.

- 2026-06-07T07:53:21Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED (via 🟣 PLAN IN REVIEW)
  - Status transition: unchanged: 🟣 IN REVIEW -> 🟣 IN REVIEW
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: AGENTS.md, epic MASTER.md FB-001/Story 02 row, Story 01 dependency contract, Story 02 current contract and prior plan review/resume log; no CONTRACT.md present
  - Traceability: forward complete; backward complete
  - Test architecture: complete; TAP rows TAP-01 through TAP-07 covered with current quality-lens columns, behavior-facing assertions/observability, deterministic fixtures, focused CI commands, fallback plans, and split/merge rationale
  - Design trace: not applicable
  - Code surfaces searched: `projects/CURe/cure.py`, `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_subsequent_review/control_plane.py`, `projects/CURe/meta.py`, focused `tests/_subsequent_review_*` suites, `tests/test_subsequent_review.py`, `tests/test_reviewflow_unittest.py`, `tests/_reviewflow_unittest_prompt_session_impl.py`
  - Risk lenses reviewed: command routing/backwards compatibility; state/artifact ambiguity; external-service incomplete data; false positives / trusted remote marker boundary; evidence-policy confusion; resource lifecycle / fail-open persistence; large-file coupling/DDD extraction; dirty-worktree warning noted but not a planning blocker
  - Evidence quality: confirmed S1-S15 each map to exactly one A1-A15 acceptance id; confirmed A4/A14 now match live decision behavior for true/enabling degraded probes versus metadata-only `discussion_incomplete` / `thread_state_unavailable`; confirmed TAP/APM/Surface/Input/Fail-open/Risk/Locked Decisions preserve that distinction; inferred no material original-intent conflict from MASTER/Story 01/Story 02 feedback logs; unknown external ticket intent beyond recorded feedback logs; provisional exact test helper names remain bounded by red-first APM Open Detail
  - Key findings:
    - [approve] Story 02 is reviewable and internally traceable after the scenario split and A4/A14 reconciliation: each normative scenario has one `Covers: A<n>` link, A1-A15 are each covered by APM rows, and TAP-01 through TAP-07 name concrete owning suites, behavior slices, assertions/observability, fixture isolation, CI lanes, fallback plans, and split rationale.
    - [approve] The external-service and false-positive risk contract now matches current implementation behavior: true unavailable/exceptions or enabling fetch/pagination failures remain degraded-enabled and run intake, while metadata-only `discussion_incomplete` / `thread_state_unavailable` with zero trusted markers are non-enabling degraded reasons that may auto-disable with `no_prior_review_signals` while staying visible in decision metadata.
    - [approve] Command mode remains exactly default `auto` and explicit `disabled`; evidence policy remains exactly `trusted|untrusted`; historical `--if-reviewed` exits remain no-new-sandbox/no-artifact paths; post-`SessionProgress.init` decision/artifact/intake failures are planned against `meta.json.status = "error"` proof.
  - Hypothesis triage: none material; checked suspected scenario coverage drift, A4/A14 degraded-boundary drift, TAP quality-lens omissions, force-enable/policy confusion, historical-exit artifact leaks, false-positive remote markers, and lifecycle error-status coverage
  - Debt Friction: none
  - Next action: run `/epic-story-review cure-subsequent-pr-review 02` from a fresh session; implementation status is already 🟣 IN REVIEW and planning is approved

- 2026-06-12T09:52:13Z Plan feedback addressed by `/epic-story-plan-resume`
  - Original feedback entry: 2026-06-12T09:39:53Z manual FB-026 Review Log entry
  - Decision: replan complete; ready for fresh plan-review
  - Sections edited: Scope, Scenarios / Behavior Examples, Acceptance, Verification (TAP/APM/Surface/Input/Fail-open/Risk), Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Status transition: unchanged: ✅ DONE -> ✅ DONE
  - Changes: Replaced the prior allowlisted-author-plus-CURe-looking-body remote marker contract with the FB-026 footer policy: official CURe review footer blocks in issue comments or pull review bodies are sufficient for auto-decision and prior-corpus ingestion regardless of author/login. Preserved the false-positive guardrails that generic/body-only CURe-looking text without the official footer is insufficient and review-comment line comments remain non-positive/non-corpus. Added secondary implementation/proof impact on the shared prior corpus predicate and focused decision/corpus tests.
  - Risk lenses preserved/activated: false-negative prior-review detection; decision/corpus consistency; external GitHub discussion boundary; false positives/spoofing; review-comment corpus exclusion.
  - Next action: run `/epic-story-plan-review cure-subsequent-pr-review 02` from a fresh session before any implementation-resume pass.

- 2026-06-12T10:00:23Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED (via 🟣 PLAN IN REVIEW)
  - Status transition: unchanged: ✅ DONE -> ✅ DONE
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: AGENTS.md; epic MASTER.md Story 02 row and FB-026 absorption row; Story 01 dependency notes for prior corpus/review-comment boundaries; Story 02 FB-026 Review Log and plan-resume entry; no CONTRACT.md present
  - Traceability: forward complete; backward complete
  - Design trace: not applicable
  - Code surfaces searched: `projects/CURe/cure_subsequent_review/decision.py`, `projects/CURe/cure_subsequent_review/prior_corpus.py`, `projects/CURe/cure_subsequent_review/github_history.py`, `projects/CURe/cure_output.py`, `projects/CURe/tests/_subsequent_review_unit_decision_unittest.py`, `projects/CURe/tests/_subsequent_review_unit_prior_corpus_unittest.py`, `projects/CURe/tests/_subsequent_review_unit_github_history_unittest.py`, `projects/CURe/tests/_subsequent_review_integration_pr_flow_unittest.py`, `projects/CURe/tests/test_subsequent_review.py`
  - Risk lenses reviewed: false-negative prior-review detection from non-bot/operator-authored CURe reviews; decision/corpus consistency; external GitHub discussion boundary; false positives/spoofing; review-comment corpus exclusion; metadata-only degraded discussion; evidence-policy separation; command-routing/backwards compatibility; resource lifecycle/fail-open persistence
  - Evidence quality: confirmed FB-026 plan text in Scope, S2/S13/S14, A2/A13/A14, TAP-02/TAP-03, APM A2/A13/A14, Surface/Input/Fail-open/Risk, Critical Files, Implementation Notes, Locked Decisions, and Discovery Notes; confirmed current code/test surfaces still use the prior trusted-author-plus-body predicate, so implementation follow-up is real; inferred no material conflict with Story 01 because Story 02 explicitly changes the shared prior-corpus predicate while preserving review-comment exclusion; unknown exact live GitHub source id for the operator-authored footer comment remains bounded by the manual FB-026 source
  - Finding closure: FB-026 planning gap closed; implementation/proof still pending in product code/tests
  - Key findings:
    - [approve] FB-026 is now traced through the Story 02 contract and proof plan: official CURe footer blocks in issue comments or pull review bodies are sufficient for auto-decision and prior-corpus ingestion regardless of author/login.
    - [approve] Prior false-positive/spoofing hardening is preserved: generic/body-only CURe-looking text without the official footer, spoofed or allowlisted author/login text without the footer, review-comment line comments, and thread-state metadata remain non-positive/non-corpus.
    - [approve] Verification is reviewer-runnable and targeted: TAP-02/TAP-03 plus APM A2/A13/A14 name focused decision/corpus/GitHub-history tests, red-first footer-positive cases, body-only-negative regressions, and review-comment exclusion checks.
  - Hypothesis triage: none material; checked footer-only weakening against prior FB-002/FB-012/FB-015 spoofing/body-only/review-comment boundaries, shared decision/corpus predicate ownership, and A4/A14 metadata-only degraded behavior
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 02` to implement FB-026 with red-first decision/corpus regressions, then run focused tests and `/epic-story-review cure-subsequent-pr-review 02`
