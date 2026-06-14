# Story 03 — Evidence Semantics and Disposition Engine

Plan: 🟢 PLAN APPROVED
Status: ✅ DONE

> Migrated from legacy `agent_coordination` into this OpenSpec change workspace on 2026-06-12.
> Runtime progress/history lives in `progress.md`; implementation review history lives in `reviews.md`.

## Purpose

Turn Story 01 subsequent-review ledgers into auditable semantic dispositions before final-report packaging begins. CURe must verify prior findings against current source evidence only, classify PR discussion/scope/authority as a separate signal stream under the existing `trusted|untrusted` evidence policy, and arbitrate explicit actions that later review/report stages can cite without re-deciding whether a prior finding was resolved, duplicated, out of scope, still reportable, partially reworded, or unsafe to suppress.

## Actors

- Primary: CURe operator running a subsequent-aware `cure pr` review that has prior CURe findings and PR discussion.
- Secondary: implementation agent.
- System: Story 01 intake control plane, source truth verifier, discussion signal resolver, disposition arbiter, persisted `work/subsequent/*` ledgers, deterministic simulation fixtures.
- Reviewer: plan-review and story-review agents validating source/discussion separation and conservative degraded behavior.

## Triggering Need

Stories 01 and 02 now gather prior CURe review material, PR discussion, prior finding candidates, reconciliation groups, and an auto/disabled decision artifact. The epic's next unsolved behavior is semantic: current CURe can remember prior findings but cannot yet prove from source whether they are fixed, interpret discussion and authority without conflating it with source truth, or emit durable disposition actions for downstream prompt packaging and report governance.

## Expected Prerequisites

- DEPENDS = 01, 02.
- Story 01 ledgers exist under `projects/CURe/cure_subsequent_review/` and `work/subsequent/`: `pr_discussion.json`, `prior_review_corpus.json`, `prior_findings.json`, `reconciled_findings.json`, and `run_manifest.json`.
- Story 02 decision metadata exists for new-sandbox runs at `work/subsequent/decision.json` and `meta.json.subsequent_review`.

## Scope

- Implement functional modules 6-8 from the epic outline: Source Truth Verifier, Discussion Signal Resolver, and Disposition Arbiter.
- Extend the subsequent-review contracts with typed, schema-versioned semantic ledgers and module-run records for:
  - `source_verification.json`
  - `discussion_signals.json`
  - `disposition_ledger.json`
- Run the new modules after Story 01 reconciliation when subsequent review is enabled and their module toggles are enabled.
- Source Truth Verifier consumes reconciled prior finding groups and prior finding source evidence, passes safe source-reference/path-range context to an injected `FindingVerifier` provider for current source/diff verification, and emits source-state labels only from provider-returned current source evidence.
- Discussion Signal Resolver consumes Story 01 PR discussion and prior-corpus provenance, links discussion events to finding IDs/groups/topics, classifies discussion/scope/authority signals under exactly the configured `trusted` or `untrusted` evidence policy, and records incomplete/unknown authority as explicit degraded or untrusted signals.
- Disposition Arbiter consumes reconciliation, source verification, and discussion signals and emits exactly five actions: `confirm_resolved`, `re_report`, `suppress_duplicate`, `move_out_of_scope`, and `reword_partial`. Every source-open finding without a trusted discussion override becomes `re_report` with discussion provenance. The downstream Report Governor decides formatting and severity emphasis from the provenance.
- Preserve safe behavior for disabled/degraded modules: missing upstream dependencies block dependent modules. Findings blocked by degradation are listed in a separate `degraded_findings` section of the disposition ledger with explicit reasons. No `ask_human` pseudo-action exists — blocked means absent from dispositions.
- Add deterministic tests and fixture/golden coverage derived from `docs/examples/subsequent-review-simulation.md` and existing `tests/fixtures/subsequent_review/*`; live PR #21 remains optional/manual only.

## Out of Scope

- Final prompt/context injection, final `review.md` formatting, GitHub publication behavior, report-governor validation, memory-store reuse across future runs, and full landmark trace packaging. Those belong to the later Review Runtime Integration / Guardrails / Memory story.
- Introducing any evidence-policy mode beyond `trusted` and `untrusted`.
- Treating PR comments, resolved thread state, review bodies, developer claims, branch names, or human assertions as proof of `resolved_from_source`.
- Reworking Story 02 auto-decision/intake discussion evidence reproducibility. Story 03 consumes the persisted intake ledgers it is given and records degraded/missing provenance; FB-010 remains a later runtime/packaging consistency candidate.
- Polishing or redesigning the SVG landmark.
- Live GitHub-dependent automated tests.

## Scenarios / Behavior Examples

- S1: Given reconciled prior findings include A-01/A-05-style findings whose original complaints are fixed in current source, when Source Truth Verifier runs, then it emits `resolved_from_source` with current source citations and no discussion-derived proof. Covers: A2.
- S2: Given a developer says a finding is fixed but current source still exhibits the defect, when all semantic modules run, then discussion records the developer claim separately and the arbiter emits `re_report` with provenance noting the claim was rejected by source, not `confirm_resolved`. Covers: A5.
- S3: Given product or maintainer discussion retargets a finding to a compatibility or external-ticket scope, when source satisfies the retargeted rule or the remaining work is outside this PR, then the arbiter emits `confirm_resolved` or `move_out_of_scope` with both source/discussion provenance. Covers: A4.
- S4: Given duplicate/superseded prior findings such as A-03/B-03 are reconciled and discussion identifies the canonical successor, when source shows the successor remains open, then the arbiter emits `suppress_duplicate` for the older finding and `re_report` for the canonical one. Covers: A4.
- S5: Given low-authority or stale pushback says not to block on a high-severity finding, when source remains open and stronger security/maintainer authority is absent or contradictory, then the arbiter emits `re_report` with provenance noting the weak pushback and authority context. Covers: A6.
- S6: Given PR discussion, review-thread state, pagination, authority, or source path/range inputs are missing or malformed, when semantic modules run, then module statuses/degraded reasons are persisted. Findings whose required upstream data is absent are listed in a separate `degraded_findings` section of the disposition ledger; they are not silently suppressed or resolved. Covers: A7.
- S7: Given current source evidence supports only part of a prior finding, when arbitration runs, then the disposition ledger emits `reword_partial` with a pointer to the source verifier row that contains the narrowed evidence. The downstream Review Context Packager produces the human-readable reworded text. Covers: A3.
- S8: Given a resolved GitHub thread is linked to a prior finding, when Source Truth Verifier runs, then the thread state is not accepted as source proof; only current source inspection can produce `resolved_from_source`. Covers: A5.
- S9: Given semantic modules are explicitly disabled through module overrides, when intake runs, then manifest module records show disabled statuses and no downstream action claims source resolution or duplicate/out-of-scope suppression. Covers: A7.
- S10: Given the local simulation fixture is evaluated, when focused tests inspect `source_verification.json`, `discussion_signals.json`, and `disposition_ledger.json`, then expected source states, discussion classifications, actions, and provenance match the simulation outcomes. Covers: A9.

## Acceptance

- A1: Story 03 modules are first-class subsequent-review modules with typed contracts, schema-versioned JSON artifacts, manifest records, and module override support for `source_truth_verifier`, `discussion_signal_resolver`, and `disposition_arbiter`.
- A2: Source Truth Verifier emits source-state records only from current source/diff evidence and persists source citations, inspected source ranges or explicit unavailable reasons, and provenance back to prior finding/group IDs.
- A3: Source Truth Verifier distinguishes `resolved_from_source`, `still_open`, `partially_resolved`, `source_unknown`, and `not_verifiable` without using discussion claims as proof.
- A4: Discussion Signal Resolver links discussion events to finding IDs/groups/topics, classifies scope/authority/discussion effects under exactly `trusted` or `untrusted`, and records normalized signal classes such as developer fixed claims, resolved-thread hints, by-design/product retargeting, external-work scoping, duplicate/superseded discussion, unresolved-thread hints, pushback, and authority conflicts.
- A5: Discussion signals never set source-state labels. Developer fixed claims, resolved-thread state, maintainer/product/security comments, and human assertions may retarget scope or influence actions only after source verification remains separate and cited.
- A6: Disposition Arbiter emits only five actions: `confirm_resolved`, `re_report`, `suppress_duplicate`, `move_out_of_scope`, and `reword_partial`. Every action cites the source ledger row, discussion signal row, and reconciliation group that caused it. Findings with degraded upstream dependencies are listed separately in `degraded_findings` rather than receiving a pseudo-action.
- A7: Disabled, missing, malformed, or degraded upstream data produces explicit module statuses/reasons. Findings whose required module dependencies are absent are listed in a separate `degraded_findings` section of the disposition ledger with blocking reasons. CURe must not silently suppress, move out of scope, or claim `resolved_from_source` when the relevant dependency is disabled or degraded.
- A8: High-severity or security-sensitive findings become `re_report` with discussion provenance when source remains open and discussion authority is insufficient, unknown, stale, or contradicted by stronger authority. The downstream Report Governor uses the provenance to decide formatting emphasis.
- A9: Deterministic simulation-derived fixtures prove representative outcomes: source-confirmed resolution, still-open re-report (including weak pushback and authority conflict cases), partial rewording with verifier-row pointer, duplicate suppression, external-scope movement, developer fixed claim accepted only after source proof, developer fixed claim rejected by source, resolved-thread hint ignored as source proof, and degraded findings listed separately when upstream data is absent.
- A10: Existing Story 01/02 behavior remains backward compatible: disabled subsequent-review mode still writes only decision metadata, enabled intake still writes existing Story 01 artifacts, evidence policy remains exactly `trusted|untrusted`, and no final report/prompt behavior changes are required by this story.

## Verification

### Verification Commands

- `cd projects/CURe && python -m pytest tests/test_subsequent_review.py -q` — public subsequent-review wrapper covering split unit/functional/integration modules, including new Story 03 tests.
- `cd projects/CURe && python -m pytest tests/_subsequent_review_unit_source_truth_unittest.py tests/_subsequent_review_unit_discussion_signals_unittest.py tests/_subsequent_review_unit_disposition_arbiter_unittest.py -q` — focused semantic module unit tests.
- `cd projects/CURe && python -m pytest tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` — artifact, manifest, module-toggle, and enabled-runtime integration coverage.
- `cd projects/CURe && python -m pytest tests/_subsequent_review_unit_contracts_cli_unittest.py tests/_subsequent_review_unit_prior_findings_unittest.py tests/_subsequent_review_unit_github_history_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py -q` — regression coverage around prior ledgers and discussion boundary shapes consumed by Story 03.
- `cd projects/CURe && ruff check . && mypy` — static/lint/type checks after source changes.
- File-read: inspect fixture sandbox `work/subsequent/source_verification.json`, `discussion_signals.json`, `disposition_ledger.json`, and `run_manifest.json` for enabled, disabled-module, degraded-source, degraded-discussion, and simulation-golden cases.

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|---|---|---|---|---|---|---|---|---|---|
| TAP-01 | unit/contracts | A1/A10 typed semantic contracts, schema versions, module names, action/source-state enumerations, evidence-policy separation | `tests/_subsequent_review_unit_contracts_cli_unittest.py`; new contract assertions near Story 03 tests | Python contract objects crossing into JSON serialization and manifest records | Assertions show module enum entries are runnable/toggleable, JSON has `schema_version`, source-state/action values are constrained, and `EvidencePolicy` remains `trusted|untrusted` only. | In-memory dataclasses/enums; no filesystem/network; deterministic serialization ordering. | `python -m pytest tests/_subsequent_review_unit_contracts_cli_unittest.py -q` plus focused semantic unit command | If contracts move into per-module files, keep public import/serialization assertions at package boundary and update exact owning file in implementation notes. | Contract behavior is cheap unit proof and should not wait for control-plane integration. |
| TAP-02 | unit/domain source verifier | A2/A3/A5 source-only states, path/range safety, missing/malformed evidence, current source citations | `tests/_subsequent_review_unit_source_truth_unittest.py` (new) | Prior finding source snippets/reconciled groups plus injected `FindingVerifier` provider output crossing into verifier ledger rows | RED assertions cover `resolved_from_source`, `still_open`, `partially_resolved`, `source_unknown`, `not_verifiable`; developer comments/resolved-thread fields are ignored; invalid paths/ranges are unavailable/degraded, not success. | In-memory verifier responses and source-reference fixtures derived from simulation; no live GitHub; cleanup via tmp_path only for path-containment/source-ref smoke cases; avoid exact timestamps. | `python -m pytest tests/_subsequent_review_unit_source_truth_unittest.py -q` | If production chunkhound+LLM integration is too broad initially, keep the injectable `FindingVerifier` provider seam and prove provider input/output boundaries; planning must record any narrower verifier contract. | Source truth is independent domain logic and needs fast red-first coverage separate from orchestration. |
| TAP-03 | unit/domain discussion resolver | A4/A5/A8 discussion linking, authority, scope, policy classification, degraded discussion handling | `tests/_subsequent_review_unit_discussion_signals_unittest.py` (new); existing `tests/_subsequent_review_unit_github_history_unittest.py` as boundary regression | Story 01 `DiscussionArtifact` events and corpus provenance crossing into normalized discussion signals | Assertions show linked finding/group IDs, signal classes, authority levels/reasons, `trusted|untrusted` classification, resolved thread as hint only, author claim as claim only, unknown authority as untrusted/degraded, and pagination/thread gaps visible. | In-memory discussion events and simulation transcript rows C-01..C-10; no live network; event order deterministic; malformed/missing author variants included. | `python -m pytest tests/_subsequent_review_unit_discussion_signals_unittest.py tests/_subsequent_review_unit_github_history_unittest.py -q` | If authority rules need config, introduce a minimal injectable authority map fixture and record defaults; unknown config must degrade to untrusted. | Discussion semantics are separate from source truth and should be proven without filesystem/source inspection. |
| TAP-04 | unit/domain arbiter | A5/A6/A7/A8 action selection and provenance for source/discussion/status combinations | `tests/_subsequent_review_unit_disposition_arbiter_unittest.py` (new) | Source verification rows, discussion signals, reconciliation groups, and module statuses crossing into action rows | Assertions cover all five allowed actions, no unsupported values, cited source/discussion/reconciliation provenance per action, source-open with fixed claim re-reports, high-severity weak pushback re-reports with authority provenance, missing dependencies block the arbiter and findings go to `degraded_findings`. | In-memory ledgers, group fixtures, and simulation matrix; no filesystem/network; severity/authority fixtures deterministic. | `python -m pytest tests/_subsequent_review_unit_disposition_arbiter_unittest.py -q` | If final action granularity changes materially, return to planning; do not add hidden extra actions in implementation. | Arbiter is pure semantic decision logic and should be exhausted before integration tests. |
| TAP-05 | functional/component control plane artifacts | A1/A6/A7/A10 enabled module orchestration, manifest records, artifact paths/statuses, disabled-module behavior | `tests/_subsequent_review_functional_control_plane_unittest.py` | Story 01 intake result crossing into new Story 03 module execution and `work/subsequent/*` writes | File-read assertions show `source_verification.json`, `discussion_signals.json`, `disposition_ledger.json`, artifact paths in manifest, disabled overrides recorded, upstream degraded reasons propagated, and existing Story 01 artifacts unchanged. | Temporary work dirs/sandboxes; fake fetcher; injectable source verifier/source-fact provider; no live network/db; cleanup via tmp_path. | `python -m pytest tests/_subsequent_review_functional_control_plane_unittest.py -q` | If control plane is split, keep component artifact proof at the new orchestrator and retain compatibility assertions for existing Story 01 artifact names. | Artifact/manifest behavior needs real filesystem proof but not full PR-flow routing. |
| TAP-06 | integration/routing PR flow | A1/A7/A10 Story 03 modules run only for enabled subsequent-review intake and do not alter disabled/new-first-run behavior | `tests/_subsequent_review_integration_pr_flow_unittest.py` | `_pr_flow_impl` new-sandbox enabled/disabled branches crossing into subsequent-review control plane | Routing assertions show auto-enabled runs create semantic artifacts after Story 01 ledgers, auto/explicit disabled runs do not create intake/semantic artifacts beyond decision, and historical exits remain artifact-free. | Temporary sandbox/cache roots, mocked GitHub/config/chunkhound/source provider; no live network; branch tests isolated. | `python -m pytest tests/_subsequent_review_integration_pr_flow_unittest.py -q` | If `_pr_flow_impl` delegates to a smaller service, preserve one public orchestration proof at the new route and keep branch-safe behavior observable in sandbox files. | Branch safety belongs at integration/routing layer because helpers alone cannot prove call order or artifact absence. |
| TAP-07 | acceptance/golden simulation | A2-A9 representative simulated dispositions and provenance | Existing `tests/fixtures/subsequent_review/simulation_raw.json`; `tests/fixtures/subsequent_review/story_01_regression_goldens.json`; add Story 03 golden fixture as needed | Simulation landmark facts/discussion/current-source matrix crossing into generated semantic ledgers | Golden assertions show expected source states, discussion classes, actions, citations, degraded fallbacks, and no discussion-derived source resolution for C-01/C-02/C-10. | Local fixture/golden only; derive from `docs/examples/subsequent-review-simulation.md`; no live PR #21; stable IDs A/B/C/S; explicit update required if landmark drifts. | `python -m pytest tests/test_subsequent_review.py -q` plus focused semantic unit command | If fixture shape differs from current Story 01 goldens, add a narrow adapter fixture and document mapping; do not depend on live GitHub. | Golden coverage validates epic landmark behavior after lower-layer modules are already unit-proven. |
| TAP-08 | static/packaging/regression | A10 package import, type safety, lint, existing Story 01/02 tests remain green | `pyproject.toml`; public wrapper `tests/test_subsequent_review.py`; existing Story 01/02 split tests | Package/test discovery and static analysis boundaries | Ruff/mypy pass; public wrapper discovers new tests; existing auto-mode/intake tests pass unchanged except expected artifact additions when enabled. | No live services; standard repo commands; failures indicate packaging/type/API drift. | `ruff check . && mypy`; `python -m pytest tests/test_subsequent_review.py -q` | If mypy config changes, record the new command before implementation review; do not skip static proof silently. | Static/regression proof guards small-module packaging and existing behavior. |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|---|---|---|---|---|---|---|
| A1 | provisional | automated + file-read | Run contract and control-plane tests for enabled and disabled module overrides | New modules serialize with schema version; manifest records artifact paths/statuses; overrides disable modules | TAP-01/TAP-05; `contracts.py`, `control_plane.py`, new semantic modules | Exact dataclass/module filenames set during implementation |
| A2 | provisional | automated + file-read | Run source verifier fixtures with current source facts and valid/invalid source snippets | Source rows cite current source ranges or unavailable reasons and map to finding/group provenance | TAP-02/TAP-07; source verifier, prior findings/reconciliation ledgers | Exact source-fact provider seam to lock red-first |
| A3 | provisional | automated | Inspect source verifier unit cases for every source-state value | Each allowed source state appears; no discussion input is required or accepted for source proof | TAP-02; source verifier enums/contracts | Exact `source_unknown` vs `not_verifiable` reason strings set red-first |
| A4 | provisional | automated | Run discussion resolver fixtures over C-01..C-10-like events | Linked signal rows contain finding/group IDs, authority/scope classes, `trusted|untrusted`, and degraded metadata where applicable | TAP-03/TAP-07; discussion resolver, GitHub history event shapes | Exact authority taxonomy may be minimal but must be explicit |
| A5 | provisional | automated | Run combined source/discussion fixtures with resolved threads and developer fixed claims | Discussion rows are hints/claims only; source rows decide source state; arbiter re-reports when source rejects a claim | TAP-02/TAP-03/TAP-04/TAP-07 | None beyond naming signal classes |
| A6 | provisional | automated + file-read | Run arbiter action matrix and inspect disposition JSON | Only five allowed actions appear; every action cites source/discussion/reconciliation provenance; findings with degraded upstream deps appear only in `degraded_findings` | TAP-04/TAP-05/TAP-07; disposition ledger | Exact JSON field names to lock red-first |
| A7 | provisional | automated + file-read | Disable/degrade source/discussion modules and malformed upstream fixtures | Manifest records disabled/degraded reasons; findings appear in `degraded_findings` with blocking reasons; no source resolution/suppression from missing data | TAP-04/TAP-05/TAP-06 | Exact degraded_findings schema fields to lock red-first |
| A8 | provisional | automated | Run high-severity authority conflict and weak-pushback arbiter cases | Source-open high/critical findings with insufficient authority emit `re_report` with authority provenance | TAP-03/TAP-04/TAP-07 | Severity normalization should reuse prior finding severity strings unless source inspection disproves |
| A9 | provisional | automated/golden | Run simulation-derived golden test and inspect semantic ledgers | Golden includes all representative expected outcomes listed in A9 with stable IDs/citations | TAP-07; simulation fixtures/goldens | Exact golden filename and fixture adapter set during implementation |
| A10 | final | automated + file-read | Run Story 01/02 focused tests plus disabled-mode fixture reads | Existing decision/intake behavior remains; evidence policy values unchanged; no final report/prompt tests require updates | TAP-01/TAP-06/TAP-08; existing split suites | — |

### Surface / Branch Proof Matrix

| Surface | Supported Variant | Internal Execution Branch | Proof Class | Owning Proof Seam | Why This Seam Is Sufficient | Out of Scope Notes |
|---|---|---|---|---|---|---|
| Control plane | enabled Story 03 modules | Story 01 ledgers -> source verifier -> discussion resolver -> arbiter | routing | TAP-05/TAP-06 | Proves module order and artifact presence in real work dirs | Final prompt/report packaging deferred |
| Control plane | module override disabled | semantic module records disabled | behavior | TAP-05 | Proves disabled modules are visible and do not create silent dispositions | Top-level disabled mode still no intake/semantic artifacts beyond decision |
| Source verifier | valid current source evidence | source-state output with citations | behavior | TAP-02 | Proves source truth at the verifier boundary | Does not require LLM/prompt review |
| Source verifier | missing/malformed path/range/source snippet | unavailable/degraded source row | behavior | TAP-02/TAP-05 | Proves unsafe input cannot become resolved source state | Path containment hardening from Story 01 remains prerequisite |
| Discussion resolver | trusted authority/scope signal | linked discussion signal under `trusted` | behavior | TAP-03/TAP-07 | Proves comments affect scope/reportability only through discussion ledger | Does not prove source resolution |
| Discussion resolver | untrusted/unknown/low-authority signal | untrusted or degraded discussion signal | behavior | TAP-03/TAP-07 | Proves weak discussion cannot suppress source-open findings by itself | Repo-specific permission API integration deferred unless local config seam exists |
| Arbiter | source resolved + no conflicting degraded blocker | `confirm_resolved` | behavior | TAP-04/TAP-07 | Proves only source rows can support confirmation | Final report wording deferred |
| Arbiter | source open + duplicate/scope/high-severity discussion | suppress/move/re-report actions as appropriate | behavior | TAP-04/TAP-07 | Proves source-vs-discussion arbitration without publishing | Report governor later validates final output |
| Runtime PR flow | auto-enabled/new sandbox | existing intake plus semantic artifacts | routing | TAP-06 | Proves subsequent-review runtime reaches new modules | Live PR #21 manual only |
| Runtime PR flow | auto-disabled/explicit-disabled/historical exit | no intake/semantic artifacts beyond decision where applicable | routing | TAP-06 | Preserves Story 02 branch-safety | No semantic no-op artifact required when intake is disabled |

### Input Boundary Shape Risk

| Boundary | Raw Input Source | Strict Assumption | Variant / Case | Evidence | Mitigation / Exclusion |
|---|---|---|---|---|---|
| Prior findings -> source verifier | `prior_findings.json` source evidence snippets | Snippets can be mapped safely to current paths/ranges or marked unavailable | valid file:line, moved line, missing file, invalid path, prose-only evidence, malformed source string | A2/A3 via TAP-02 | Unsafe/unparseable evidence becomes `not_verifiable`/`source_unknown`; never `resolved_from_source` |
| Reconciled groups -> semantic rows | `reconciled_findings.json` groups and canonical IDs | Group/canonical IDs are stable enough to map actions | single finding, duplicate group, supersedes edge, ambiguous supersedes/degraded group | A6/A7 via TAP-04/TAP-05 | Ambiguity records degraded provenance and avoids duplicate suppression without support |
| PR discussion -> resolver | `pr_discussion.json` events/pagination/thread metadata | Event body/author/path/thread state can be classified without proving source truth | issue comments, reviews, review comments, resolved/unresolved/unknown thread, missing author, incomplete pagination | A4/A5/A7 via TAP-03 | Missing/incomplete discussion becomes untrusted/degraded; comments stay discussion signals only |
| Authority config/heuristics -> resolver | local config/default role map if introduced | Authority can be classified or explicitly unknown | maintainer/product/security/author/low/unknown/stale/conflicting | A4/A8 via TAP-03/TAP-04 | Unknown authority is untrusted/conservative; do not require live permission API in routine tests |
| Source verifier + discussion resolver -> arbiter | Typed semantic ledgers and module statuses | Arbiter can select one of five allowed actions per finding/group without hidden inputs | all five actions, missing dependency, source/discussion conflict | A6/A7/A8 via TAP-04 | Missing dependencies block the arbiter; findings go to `degraded_findings` rather than receiving a pseudo-action |
| Semantic ledgers -> JSON artifacts | dataclass/dict serialization | Schema is durable enough for later packager/report governor | enabled, disabled module, degraded source, degraded discussion, simulation golden | A1/A6/A7 via TAP-05/TAP-07 | Exact schema fields locked by tests; future packaging may add summaries without changing this story's actions |

### Fail-open Checks

| Check | Proof Method | Expected Evidence |
|---|---|---|
| Discussion claim accidentally marks source resolved | Unit/golden tests | Developer fixed claims and resolved-thread hints appear only in discussion signals; source state comes from source verifier rows |
| Missing source evidence suppresses a finding | Source verifier + arbiter tests | Missing/malformed source becomes `source_unknown`/`not_verifiable`; finding goes to `degraded_findings` or becomes `re_report` depending on whether the verifier produced a degraded result or simply couldn't inspect |
| Missing or incomplete discussion silently suppresses a source-open finding | Discussion resolver + arbiter tests | Discussion degraded reasons are persisted; no suppression/out-of-scope move depends on missing discussion |
| Evidence policy gains a third semantic mode | Contract tests | Policy enum and serialized ledgers contain only `trusted` or `untrusted` |
| Arbiter invents an unplanned action | Arbiter tests + JSON file-read | Every disposition action is one of the five accepted values; `degraded_findings` entries have no `action` field |
| Disabled semantic module looks successful | Control-plane artifact tests | Manifest status is `disabled`; dependent artifacts are absent; dependent findings appear in `degraded_findings` with blocking reasons |
| High-severity weak pushback disappears | Arbiter/golden tests | Source-open high/critical findings with only weak pushback become `re_report` with authority provenance; they never disappear or degrade into suppression |
| Existing Story 01/02 disabled/new-first-run behavior changes | Integration tests/file-read | Auto/explicit disabled runs do not create intake/semantic artifacts beyond decision; existing intake ledgers remain named and readable |

### Risk Lens Inventory

| Risk Lens | Activated By | Planning / Proof Obligation | Owner Surface | Exclusion / Rationale |
|---|---|---|---|---|
| Security/semantic invariant naming | Only source may prove source resolution | Tests and contracts must keep `resolved_from_source` confined to Source Truth Verifier output | source verifier, arbiter | Covered by A2/A3/A5 |
| Persistence/schema contracts | New machine-readable ledgers and manifest paths | Schema-versioned artifacts with file-read assertions and manifest records | contracts/control plane/artifact writers | Covered by A1/A6/A7 |
| Source-reference/provider boundary | Verifier receives historical snippets/path ranges but delegates current-source assessment to an injected provider | Path/range parsing, missing/malformed evidence, provider responses, and source fact injection must be deterministic and safe | source verifier | Covered by TAP-02/Input Boundary |
| External-service/degraded data | Discussion may be incomplete or authority unknown | Resolver records degraded/untrusted signals and arbiter avoids suppression from missing data | discussion resolver/arbiter | Live GitHub excluded from routine proof |
| Prompt/report fail-open | Later prompts may consume these artifacts | Story 03 emits explicit actions/provenance but does not wire prompts; later packaging story must validate final output | disposition ledger | Final report behavior out of scope; FB-007 final surfacing deferred |
| Cross-module consistency | Story 02 decision evidence can diverge from intake discussion evidence | Story 03 consumes persisted intake ledgers and records missing/degraded inputs; reproducibility between decision and intake remains FB-010 later scope | control plane/metadata | Explicitly out of scope to avoid expanding Story 03 |
| Large-file coupling | Existing runtime lives in `cure.py`; Story 01 modules are focused package files | Implement semantic logic in small `cure_subsequent_review` modules and keep `cure.py` as routing only | new source/discussion/arbiter modules | DDD/small-module obligation from AGENTS.md |

### Design Sources

| Source Anchor | Status | Notes / Supersession |
|---|---|---|
| `projects/CURe/docs/examples/subsequent-review-simulation.md` | orientation only | Scenario landmark for fixture/golden coverage; exact markdown wording/output is not a final-report contract in this story. |
| `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` | orientation only | Epic stage-map landmark for stages 6-8; SVG visual polish and exact diagram content are out of scope. |

## Discovery Notes

- `projects/CURe/cure_subsequent_review/contracts.py:1-5` explicitly says Story 01 defines all module contracts but has no source-state or disposition labels yet.
- `projects/CURe/cure_subsequent_review/contracts.py:15-43` already defines `EvidencePolicy`, `ModuleStatus`, and enum entries for `SOURCE_TRUTH_VERIFIER`, `DISCUSSION_SIGNAL_RESOLVER`, and `DISPOSITION_ARBITER`.
- `projects/CURe/cure_subsequent_review/control_plane.py:24-43` currently limits `SubsequentReviewConfig.module_enabled()` to Story 01 modules, so Story 03 must deliberately make modules 6-8 runnable/toggleable.
- `projects/CURe/cure_subsequent_review/control_plane.py:99-189` writes Story 01 artifacts and manifest; Story 03 should extend this focused control-plane package rather than expanding `cure.py`.
- `projects/CURe/cure_subsequent_review/github_history.py:149-226` normalizes PR discussion events; thread state is available as metadata and must remain a hint, not source truth.
- `projects/CURe/cure_subsequent_review/prior_findings.py:56-128` parses prior findings and rejects non-source evidence; Story 03 should preserve that boundary when verifying source truth.
- `projects/CURe/cure_subsequent_review/finding_identity.py:95-223` owns reconciliation groups, supersedes edges, and ambiguity; the arbiter should consume this ledger instead of rematching findings from scratch.
- `projects/CURe/docs/examples/subsequent-review-simulation.md:133-154` names the intended source-verification, comment-resolution, and disposition artifacts; this story chooses JSON machine ledgers under the existing `work/subsequent/` directory while leaving human-readable final summaries to a later story.
- Existing public test entrypoint `projects/CURe/tests/test_subsequent_review.py:1-13` imports split private subsequent-review suites; new Story 03 tests should join that wrapper so focused and public commands stay aligned.

## Critical Files

| File | Role |
|---|---|
| `projects/CURe/cure_subsequent_review/contracts.py` | Extend typed contracts with source verification rows, discussion signal rows, disposition action rows, schema serialization, and constrained enums. |
| `projects/CURe/cure_subsequent_review/control_plane.py` | Call the Story 03 semantic pipeline after reconciliation, update manifest statuses, and preserve disabled/degraded behavior. |
| `projects/CURe/cure_subsequent_review/semantic_pipeline.py` (new) | Data-driven `MODULE_REGISTRY` orchestrator for Source Truth Verifier, Discussion Signal Resolver, and Disposition Arbiter; owns dependency checks and artifact writes. |
| `projects/CURe/cure_subsequent_review/prior_findings.py` | Source-evidence input shape consumed by Source Truth Verifier; existing invalid/prose evidence protections must remain. |
| `projects/CURe/cure_subsequent_review/finding_identity.py` | Reconciliation/group/supersedes input for duplicate suppression and canonical disposition decisions. |
| `projects/CURe/cure_subsequent_review/github_history.py` | Discussion event/thread metadata input consumed by Discussion Signal Resolver; thread status remains metadata only. |
| `projects/CURe/cure_subsequent_review/source_truth.py` (new) | Focused Source Truth Verifier module; delegates current-source assessment to injected `FindingVerifier` provider and never treats discussion as proof. |
| `projects/CURe/cure_subsequent_review/discussion_signals.py` (new) | Focused Discussion Signal Resolver module. |
| `projects/CURe/cure_subsequent_review/disposition.py` (new) | Focused Disposition Arbiter module. |
| `projects/CURe/tests/_subsequent_review_unit_source_truth_unittest.py` (new) | Unit tests for source states, source-only proof, and source input boundary safety. |
| `projects/CURe/tests/_subsequent_review_unit_discussion_signals_unittest.py` (new) | Unit tests for discussion linking, authority/scope classification, evidence-policy values, and degraded discussion. |
| `projects/CURe/tests/_subsequent_review_unit_disposition_arbiter_unittest.py` (new) | Unit tests for action selection, provenance, source/discussion conflicts, and conservative degraded handling. |
| `projects/CURe/tests/_subsequent_review_functional_control_plane_unittest.py` | Extend artifact/manifest/control-plane tests for Story 03 modules and disabled/degraded branches. |
| `projects/CURe/tests/_subsequent_review_integration_pr_flow_unittest.py` | Extend runtime routing proof so enabled subsequent-review runs produce semantic ledgers and disabled/historical exits do not. |
| `projects/CURe/tests/fixtures/subsequent_review/` | Existing simulation fixtures/goldens; add Story 03 golden expectations derived from the simulation landmark. |

## Implementation Notes

Recommended red-first sequence:

1. Add contract tests for allowed source-state/action values, schema-versioned JSON, module manifest records, and evidence-policy separation.
2. Implement Source Truth Verifier behind an injectable `FindingVerifier` callable so unit tests can prove source-only states from provider-returned current-source evidence without live GitHub or prompt execution.
3. Implement Discussion Signal Resolver with the same injectable-callable pattern plus heuristic authority defaults; unknown or incomplete authority must be untrusted/degraded rather than accepted as suppression authority.
4. Implement Disposition Arbiter as pure logic over typed ledgers and module statuses, with exhaustive action tests before control-plane integration.
5. Add `cure_subsequent_review/semantic_pipeline.py` as the delegated `MODULE_REGISTRY` orchestrator and call it from `run_subsequent_review_intake` after reconciliation when enabled and module overrides permit.
6. Add simulation-derived golden coverage for the expected A/B/C/S landmark outcomes without requiring live PR #21.
7. Run focused semantic tests, existing subsequent-review wrapper, adjacent prior-ledger tests, `ruff`, and `mypy`.

Keep source/discussion/arbiter logic in small `cure_subsequent_review` modules. If the injected verifier/provider contract cannot produce auditable current-source states at this story size, implementation must stop and return to planning with a narrowed provider contract rather than substituting comments or prompt conventions for source truth.

## Locked Decisions

- Story number 03 is used because actual Story 02 became Auto-infer Subsequent Review Mode; this story implements the original roadmap's Evidence Semantics and Disposition Engine as the next delivery slice.
- Evidence policy remains exactly `trusted` and `untrusted`; no third policy or semantic confidence mode is introduced.
- Only Source Truth Verifier may emit source-state labels such as `resolved_from_source`.
- Discussion Signal Resolver may classify scope, authority, retargeting, duplicate/superseded, resolved-thread hints, and claims, but discussion never proves source resolution.
- Disposition actions are limited to `confirm_resolved`, `re_report`, `suppress_duplicate`, `move_out_of_scope`, and `reword_partial`. Every source-open finding without a trusted discussion override becomes `re_report` with provenance. The downstream Report Governor decides formatting and severity emphasis. Degraded findings are listed in a separate `degraded_findings` section, not assigned a pseudo-action.
- Disabled/degraded/missing modules must be visible in manifest/artifacts and force conservative downstream behavior.
- FB-007 final report surfacing is deferred; Story 03 creates the provenance-bearing semantic ledgers that a later packager/report-governor story can surface.
- FB-010 decision-vs-intake discussion evidence reproducibility is deferred; Story 03 consumes persisted intake ledgers and records degraded/missing provenance rather than reusing remote decision fetches.

## Plan Review Log

- 2026-06-08T13:20:00Z Plan polish after pass #4
  - Verdict/lane/status unchanged: 🟢 PLAN APPROVED / ⚪ TODO
  - Edits: aligned Scope, TAP-02, Risk Lens Inventory, Critical Files, and Implementation Notes with the Grilling Session's injected `FindingVerifier` model and explicit `semantic_pipeline.py`/`MODULE_REGISTRY` orchestration.
  - Rationale: remove implementor ambiguity from older direct-source phrasing and make the authoritative orchestration file visible outside the Grilling Session section.
  - MASTER polish: older compressed-delivery roadmap wording was updated from the pre-grilling 7-action/`ask_human` sketch to the approved five-action plus `degraded_findings` model.

- 2026-06-08T13:00:00Z Plan review (pass #4) — fresh independent validation by child plan-review session
  - Verdict: approve
  - Plan lane: unchanged: 🟢 PLAN APPROVED -> 🟢 PLAN APPROVED
  - Status: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Test Architecture Plan, Acceptance Proof Matrix, Surface / Branch Proof Matrix, Input Boundary Shape Risk, Fail-open Checks, Risk Lens Inventory, Discovery Notes, Critical Files, Implementation Notes, Locked Decisions, Grilling Session, MASTER Story tracker and epic constraints.
  - Original intent checked: AGENTS.md constraints; epic MASTER goal/modules/landmarks/FB-007/FB-010; Story 01/02 live seams; Story 03 Grilling Session as superseding authority; live product branch `cure-subsequent-pr-review/story-01-intake`; preserved untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg`.
  - Traceability: forward complete; backward complete.
  - Grilling consistency: verified source/discussion separation, exact `trusted|untrusted` policy, five arbiter actions only, `degraded_findings` instead of `ask_human`, pointer-only `reword_partial`, injectable verifier/resolver, LLM discussion linking, `MODULE_REGISTRY` dependency model, stable row-ID cross references, `semantic_pipeline.py` orchestration seam, parametrized golden tests, and same-branch PR #22 strategy. No blocking stale references inside the Story 03 authoritative plan body.
  - Live repo alignment: confirmed `contracts.py` currently has Story 03 module enum entries and exact `EvidencePolicy`/`ModuleStatus` values, but no source-state/action labels; `control_plane.py` still gates only `_STORY_01_MODULES` and writes the five Story 01 artifacts before `run_manifest.json`; `prior_findings.py` rejects findings without valid source references; `finding_identity.py` exposes groups, `supersedes_edges`, and `ambiguous_supersedes`; `github_history.py` stores `thread_state` as metadata-only; public `tests/test_subsequent_review.py` imports the 8-suite `_subsequent_review_unittest.py` umbrella, with no Story 03 suites yet.
  - Key findings:
    - [approve] Story 03 remains internally consistent and implementation-ready. Purpose/Actors/Scenarios/Acceptance/TAP/APM/risk/fail-open sections all preserve the core invariant that only current source evidence can produce source-state labels while discussion/scope/authority remain a separate signal stream.
    - [approve] The proof plan is adequate: TAP-01..TAP-08 cover typed contracts, source verifier boundaries, discussion authority/linking, action arbitration, control-plane artifacts/toggles, runtime routing, simulation goldens, and wrapper/static regression.
    - [observe] MASTER's older compressed-delivery sketch still shows the pre-grilling seven-action list and generic ask/exit degraded language. The Story 03 Grilling Session, story tracker row, and this review supersede it; no lane update required.
    - [observe] Some pre-grilling source-verifier prose still mentions direct path/range/source fixture boundaries, while the Grilling Session requires an injected `FindingVerifier` provider that never reads files directly. This is not a blocker because the Grilling Session is explicit and TAP-02/Implementation Notes already allow an injectable provider seam; implementation should follow the Grilling Session wording.
    - [observe] `semantic_pipeline.py` is still named only in the Grilling Session, not in the Critical Files table. Implementors should create/use it as authoritative orchestration target.
  - Hypothesis triage: checked and rejected as blockers — stale action vocabulary inside authoritative Story 03 body; discussion proof of source resolution; third evidence-policy mode; silent suppression on missing/degraded data; test wrapper drift; product-source seam drift.
  - Debt Friction: none.
  - Evidence quality: high — direct repo reads plus targeted exact searches; no product source edits.
  - Next action: proceed to Story 03 implementation/resume on the existing PR #22 branch.

- 2026-06-08T12:00:00Z Plan review (pass #3) — fresh independent validation by new session
  - Verdict: approve
  - Plan lane: unchanged: 🟢 PLAN APPROVED -> 🟢 PLAN APPROVED
  - Status: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Test Architecture Plan, Acceptance Proof Matrix, Surface / Branch Proof Matrix, Input Boundary Shape Risk, Fail-open Checks, Risk Lens Inventory, Design Sources, Discovery Notes, Critical Files, Implementation Notes, Locked Decisions, Grilling Session, MASTER Story tracker, prior plan-review entries
  - Original intent checked: AGENTS.md; epic MASTER constraints/modules/landmarks/FB-007/FB-010; Story 01/02 delivered ledger and decision seams; all 11 Grilling Session decisions against live repo source and plan body prose; direct product source/test reads (contracts.py, control_plane.py, prior_findings.py, finding_identity.py, github_history.py, test wrapper)
  - Traceability: forward complete; backward complete
  - Grilling consistency: all 11 Grilling Session decisions verified against plan body (Scope, S1-S10, A1-A10, TAP, APM, Surface/Branch, Fail-open, Locked Decisions). No stale 7-action references remain. The 5-action model, `degraded_findings` section, injectable verifier/resolver, LLM-based discussion linking, data-driven MODULE_REGISTRY, `semantic_pipeline.py` orchestrator, cross-referencing by row IDs, pointer-based `reword_partial`, and parametrized golden matrix are all consistently reflected.
  - Live repo alignment: confirmed `contracts.py` defines `SOURCE_TRUTH_VERIFIER`, `DISCUSSION_SIGNAL_RESOLVER`, `DISPOSITION_ARBITER` enum entries with no source-state/disposition labels; confirmed `_STORY_01_MODULES` excludes Story 03 modules and `module_enabled()` would reject them; confirmed `run_subsequent_review_intake()` writes 5 Story 01 artifacts in linear gated order, ending at `reconciled_findings.json` — a clean seam for the semantic pipeline; confirmed `github_history.py:thread_state` is metadata-only with explicit docstring warning; confirmed `prior_findings.py` rejects non-source-ref evidence; confirmed `finding_identity.py` exposes `ReconciliationLedger` with `supersedes_edges`/`ambiguous_supersedes` for arbiter consumption; confirmed schema version 1 is carried by existing artifact dataclasses; confirmed test wrapper imports 8 split subsequent-review suites (no Story 03 tests exist yet).
  - Key findings:
    - [approve] The source/discussion separation remains airtight across all contract layers. The plan's Scope, S2/S5/S8, A2/A3/A5, TAP-02/TAP-03/TAP-04, Fail-open Checks, Risk Lens, and Locked Decisions all converge on the same invariant: only current source can emit `resolved_from_source`; discussion claims stay in `discussion_signals.json`.
    - [approve] Deferred scope boundaries are enforced and correct: FB-007 (final report surfacing) and FB-010 (decision/intake reproducibility) are excluded from Story 03 scope and only re-surface by producing provenance-bearing ledgers that downstream stories can cite.
    - [observe] Minor documentation polish: `semantic_pipeline.py` is named in the Grilling Session as the orchestrator but is absent from the Critical Files table. Implementation Notes step 5 says "Extend `run_subsequent_review_intake` or a small delegated semantic orchestrator" without naming the module. Not a planning defect — the Grilling Session clarifies the target.
    - [observe] `_STORY_01_MODULES` set-based gating (control_plane.py:module_enabled) and Grilling Session's data-driven `MODULE_REGISTRY` are two separate mechanisms that must be reconciled during implementation. The plan acknowledges both (Scope references module toggles; Grilling Session defines the registry) but does not prescribe how they coexist. This is a bounded implementation seam, not a contract gap.
    - [observe] Epic MASTER `## Compressed delivery stories` table still lists the original 7-action set for the Evidence Semantics story. The Grilling Session and this plan-review entry supersede that older informal sketch; no MASTER update required since the story tracker row is correct.
  - Hypothesis triage: checked and rejected — stale 7-action references (none found after second-pass fixes), discussion-proof confusion (S8/A5/TAP-02 bound), degraded silent success (S6/A7/TAP-04/TAP-05 bound), evidence-policy drift (A4/A10/Locked Decisions/Fail-open bound), missing orchestrator module (Grilling Session resolves to `semantic_pipeline.py`), live artifact shape drift (verified against current contracts.py dataclasses).
  - Debt Friction: none
  - Evidence quality: high — all live-repo claims confirmed via direct source reads; all grilling decisions traced back to plan body prose; all epic constraints verified against plan boundaries. No unsourced product behavior claims.
  - Next action: run `/epic-story-plan-converge cure-subsequent-pr-review 03` or proceed directly to implementation with `/epic-story-resume cure-subsequent-pr-review 03`.

- 2026-06-07T10:11:26Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED (via 🟣 PLAN IN REVIEW)
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Test Architecture Plan, Acceptance Proof Matrix, Surface / Branch Proof Matrix, Input Boundary Shape Risk, Fail-open Checks, Risk Lens Inventory, Design Sources, Discovery Notes, Critical Files, Implementation Notes, Locked Decisions, MASTER Story tracker
  - Original intent checked: AGENTS.md, epic MASTER constraints/modules/landmarks/FB-007/FB-010, Story 01/02 delivered ledger and decision seams, Story 03 draft, direct product source/test reads
  - Traceability: forward complete; backward complete
  - Test architecture: complete; TAP-01 through TAP-08 name concrete owning suites, behavior/assertion boundaries, deterministic fixture strategies, CI commands, fallback plans, and split/merge rationale for contracts, source verification, discussion resolution, arbitration, control-plane artifacts, PR-flow routing, golden simulation, and static/regression proof
  - Risk lenses reviewed: source-vs-discussion semantic invariant; exact `trusted|untrusted` policy; disabled/degraded fail-open behavior; source path/range boundary; authority/incomplete discussion handling; module override/routing compatibility; final-report surfacing and decision/intake reproducibility deferrals; large-file/DDD extraction; dirty-worktree warning noted but not a planning blocker
  - Evidence quality: confirmed Story 03 scope aligns to current epic modules 6-8 and preserves final report/memory/runtime guardrails for later work; confirmed live contracts already enumerate Story 03 module names while current control plane only runs Story 01 modules; confirmed current Story 01 ledgers expose discussion events/thread metadata, prior finding source snippets, reconciliation groups/supersedes/ambiguity, schema versions, and status reasons for Story 03 consumption; inferred exact semantic dataclass field names and authority taxonomy can remain provisional because TAP/APM rows bind them red-first; no material unsourced product behavior claims found
  - Key findings:
    - [approve] Story 03 is reviewable and internally traceable: Acceptance A1-A10 map to TAP/APM rows, fail-open checks cover the semantic hazards, and Critical Files/Implementation Notes point implementation toward small `cure_subsequent_review` modules rather than expanding `cure.py`.
    - [approve] The source/discussion separation is explicit and repeated across Scope, Out of Scope, Scenarios, Acceptance, TAP-02/TAP-03/TAP-04, Fail-open Checks, Risk Lens Inventory, and Locked Decisions; discussion claims, resolved thread state, and human assertions cannot prove `resolved_from_source` under the plan.
    - [approve] Deferred scope is bounded: FB-007 final report surfacing and FB-010 decision-vs-intake evidence reproducibility are recorded as later-story concerns, while this story produces provenance-bearing semantic ledgers and conservative degraded dispositions for downstream consumers.
  - Hypothesis triage: none material; checked suspected scenario/acceptance coverage gaps, Story 02 numbering/roadmap drift, evidence-policy expansion, disabled-module silent success, unresolved source-fact provider seam, authority unknown handling, fixture/golden coverage, and public wrapper/static proof coverage
  - Debt Friction: none
  - Next action: run `/epic-story-resume cure-subsequent-pr-review 03` from a fresh session; implementation status remains ⚪ TODO and planning is approved


## Live-audit remap addendum — FB-032 and FB-035 source-truth side

Status remains `✅ DONE`: this addendum records authoritative ownership for PR #22 live-audit feedback that was initially staged in the former synthetic Story 05 scaffold. Product/test code is unchanged by the remap.

### Ownership

- FB-032: Story 03 owns the discussion-authority invariant. Trusted product/security/maintainer authority comes from authenticated author/role metadata or explicit configuration, never from untrusted comment body words alone.
- FB-035: Story 03 owns the source-truth invariant that source-state labels must be grounded in inspected current repo-local source contexts. Story 04 owns the runtime LLM verifier enforcement surface for this invariant.

### Acceptance addenda

- LA-01 / FB-032: Discussion Signal Resolver separates authenticated metadata/config authority from untrusted body content. Role words such as `product`, `security`, or `maintainer` inside an untrusted body are recorded as body claims or rationale only; they cannot elevate the event to trusted authority.
- LA-02 / FB-035: Source Truth Verifier and Disposition Arbiter accept `resolved_from_source` only from inspected current-source evidence with repo-local citations or explicit unavailable/degraded reasons. Arbitrary LLM-returned paths or line numbers outside inspected context cannot become source truth.

Implementation evidence for the remapped feedback is on PR #22 in commits `f96e7ad` and `ee7410a`; the remaining fresh live audit is tracked by Story 04.
