# Story 05 — Subsequent Review Runtime Hardening After Live Audit

Plan: 🟢 PLAN APPROVED
Status: 🔄 IN PROGRESS

> Story candidate scaffolded from the 2026-06-13 PR #22 live-audit ingestion. It captures feedback that should not re-expand completed Story 01-04 contracts without a fresh plan/review loop.

## Purpose

Harden the subsequent-review runtime after the latest PR #22 live audit by separating audit/provenance output from ordinary consumer-facing review text, tightening memory and linker identity boundaries, and closing source/provenance/trust fail-open paths found in sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739` at head `372b4a753099c4b6e077d98551da51039222a16b`.

## Actors

- Primary: CURe operator and PR review consumer reading `review.md`.
- Secondary: implementation agent maintaining subsequent-review runtime modules.
- Reviewer: plan-review and story-review agents validating live-audit feedback absorption.
- System: review runtime prompt renderer, report governor, review memory store, discussion linker, source verifier, session artifact selectors, and prior-finding extractor.

## Triggering Need

The 2026-06-13 PR #22 live review completed successfully and closed the prior strict multipass `### Step Result:` regression, A19/`DA-0006` footer-policy gate, A17 warn-only governor behavior, and the narrow FB-028/FB-029 fixes. The same live review still returned **REQUEST CHANGES** with new or broader hardening issues: top-level `### Internal DA coverage` exposes audit-only DA rows to ordinary consumers; memory/linker cache identity remains too weak for repeated IDs and ordinal groups; untrusted discussion body text can affect authority; source/citation/path boundaries remain fail-open; concise generated reviews can disappear from prior-finding identity; and a multipass planner abort can bypass final-output guardrails.

## Expected Prerequisites

- Story 01, Story 02, and Story 03 are `✅ DONE`.
- Story 04 is implemented/pushed on PR #22 and has a latest live audit at sandbox `grzegorznowak-cure-pr22-20260613-080828-d739`.
- OpenSpec feedback records FB-030 through FB-038 are accepted as the planning input for this story.

## Scope

- Adjust final-output prompt/governor contracts so `### Internal DA coverage` is no longer a prominent ordinary `review.md` section; DA row coverage remains mandatory for audit/governor/provenance via artifact, appendix, hidden/collapsible section, or explicitly audit-only surface.
- Strengthen review-memory replay identity beyond ordinal `group_id` plus display `finding_ids`, using stable origin/fingerprint/source-reference evidence where available.
- Prevent untrusted PR comment body text from escalating product/security/maintainer authority.
- Constrain cached discussion linker results to current reconciliation group identity and runtime context.
- Enforce session-boundary checks for zip/source artifact selection paths read from historical metadata.
- Constrain LLM verifier citations to inspected repo-local source contexts before allowing `resolved_from_source`.
- Route discussion linker LLM calls through the same prepared runtime policy/add-dir/config environment as the main review/verifier/governor calls.
- Preserve prior-finding identity for supported concise generated reviews.
- Ensure multipass planner-abort output cannot bypass required prior-review history/governor guardrails when a prior-review brief exists.

## Out of Scope

- Re-opening Story 01-04 accepted behavior except where explicitly listed above.
- Changing the two evidence-policy modes (`trusted`, `untrusted`) or adding a third policy mode.
- Making PR discussion or memory a source-truth proof; current source evidence remains required for `resolved_from_source`.
- Live-GitHub-required automated tests; live PR #22 artifacts are audit inputs, not routine CI dependencies.

## Scenarios / Behavior Examples

- S1: Given a subsequent-aware final review has prior DA rows, when the ordinary `review.md` is produced, then the reader-facing top section is human issue history and row-level DA coverage is absent from the normal body or clearly demoted to an audit/provenance appendix/artifact/collapsible block. Covers: A1.
- S2: Given two prior findings share the same display finding ID under different origins, when memory replay is considered at the same head, then replay is accepted only if stable origin/fingerprint/source-reference identity matches the current group. Covers: A2.
- S3: Given a non-maintainer writes body text such as "product scope" or "maintainer duplicate", when authority is classified, then body text alone cannot grant trusted product/security/maintainer authority. Covers: A3.
- S4: Given historical session metadata contains an absolute path or `..` traversal for zip source selection, when artifacts are selected, then paths outside the session boundary are rejected/degraded. Covers: A4.
- S5: Given cached discussion linker output references ordinal group `G-0001`, when current reconciliation groups differ, then cached links are validated against current group identity or discarded. Covers: A5.
- S6: Given the verifier LLM returns a citation outside the inspected source contexts, when source truth is normalized, then the row cannot become `resolved_from_source` from that unsupported citation. Covers: A6.
- S7: Given runtime policy/add-dir/config overrides are required for review LLM calls, when discussion linker classification runs, then it receives the same prepared runtime policy boundary as sibling LLM calls. Covers: A7.
- S8: Given a prior CURe review was generated in concise `--wtf off` mode with issue bullets and `Sources:`, when prior findings are extracted, then supported concise findings become candidates instead of disappearing for missing verbose severity markup. Covers: A8.
- S9: Given a prior-review brief exists and multipass planning aborts, when the synthetic abort review is written, then required prior-review history/governor handling is preserved or publication is safely degraded with explicit audit evidence. Covers: A9.

## Acceptance

- A1: Ordinary consumer-facing `review.md` must not require or prominently show a top-level `### Internal DA coverage` row list. Complete DA coverage remains required for report-governor/audit/provenance, but it must live in an audit artifact, metadata, comment, appendix, hidden/collapsible block, or otherwise clearly demoted audit-only surface.
- A2: Review-memory replay identity uses more than ordinal `group_id` and display `finding_ids`; replay of `resolved_from_source` requires a stable current-group identity match using origin key, fingerprint, corpus entry, source-reference digest, or an equivalent persisted identity proof.
- A3: Discussion authority classification separates authenticated author/role metadata from untrusted body text. Untrusted comment content cannot grant product/security/maintainer authority by containing role words.
- A4: Zip/source artifact selection rejects or degrades historical metadata paths that resolve outside the owning session directory, including absolute paths and `..` traversals.
- A5: Cached discussion linker results are replayed only when the current reconciliation group identity matches the cached identity; stale ordinal group IDs are discarded or degraded before disposition.
- A6: LLM verifier citations are code-constrained to inspected repo-local source contexts. Unsupported returned paths/lines are rejected, downgraded, or force `not_verifiable` / `still_open`; they cannot drive `resolved_from_source`.
- A7: Discussion linker LLM calls use the prepared review runtime policy, config overrides, add-dir access, cwd/environment constraints, and model settings consistently with verifier/review/governor calls.
- A8: Supported concise generated reviews are parsed into prior finding candidates when they contain recognizable issue bullets and source evidence, even without verbose details-card severity markup; missing severity degrades with provenance rather than dropping identity silently.
- A9: Multipass planner abort paths preserve prior-review final-output guardrails when a prior-review brief exists, either by emitting required issue-history context and running/recording governor audit, or by explicitly degrading/aborting before publication.

## Verification

### Verification Commands

- `python -m pytest tests/_subsequent_review_unit_report_governor_unittest.py tests/test_reviewflow_prompts_unittest.py -q`
- `python -m pytest tests/_subsequent_review_unit_memory_store_unittest.py tests/_subsequent_review_unit_reconciliation_unittest.py tests/_subsequent_review_unit_source_truth_unittest.py -q`
- `python -m pytest tests/_subsequent_review_unit_discussion_linker_unittest.py tests/_subsequent_review_unit_discussion_signals_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q`
- `python -m pytest tests/_subsequent_review_unit_llm_verifier_unittest.py tests/_subsequent_review_unit_prior_findings_unittest.py -q`
- `python -m pytest tests/test_subsequent_review.py -q`
- `ruff check . && git diff --check && mypy`
- Manual/file-read proof against a fresh PR #22 rerun: final `review.md`, `work/subsequent/report_governor_result.json`, `source_verification.json`, `disposition_ledger.json`, `discussion_signals.json`, and `cure_memory.json`.

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|---|---|---|---|---|---|---|---|---|---|
| TAP-1 | prompt/report-governor UX | A1 DA coverage demotion from ordinary review body while preserving audit coverage | report-governor + prompt tests | governor brief + prompt guidance + final review audit | Human issue history remains first; top-level Internal DA coverage is absent/demoted; audit artifact still covers every DA row | In-memory DA ledger and rendered prompt fixtures | focused report-governor/prompt command | If final output must remain markdown-only, use an appendix/collapsible block with explicit audit-only framing | Separates reader UX from provenance completeness |
| TAP-2 | memory/finding identity | A2 stable replay identity | memory/reconciliation/source tests | `cure_memory.json` + current reconciliation groups | Same display ID but different origin/fingerprint/source digest does not replay resolved row | Fixtures with repeated `CURE-002` and shifted ordinal groups | memory/reconciliation command | If full digest unavailable, require no replay rather than unsafe replay | Covers broader FB-029 variant |
| TAP-3 | discussion authority | A3 trusted authority boundary | discussion signals tests | PR comment event metadata/body → authority | Body role words do not grant trusted authority without authenticated metadata | Events from unknown author containing role keywords | discussion-signals command | Conservative untrusted fallback | Prevents policy escalation |
| TAP-4 | artifact path boundary | A4 session path containment | session artifact/zip tests | `meta.json` paths → zip/source selection | Absolute and traversal paths outside session are rejected/degraded | tmp sessions with malicious metadata paths | focused session tests | Skip unsafe artifact with warning | Security/provenance boundary |
| TAP-5 | linker cache identity/runtime | A5/A7 linker cache and runtime policy | linker + PR-flow integration tests | cached linker result + prepared runtime | Stale ordinal cached links discarded; linker receives prepared runtime policy/add_dirs/config | Fake runtime policy and changed group layout | linker/PR-flow command | Disable cache when identity proof absent | Keeps linker cache advisory |
| TAP-6 | verifier citation constraint | A6 inspected-context citation enforcement | LLM verifier/source-truth tests | LLM JSON citations → source-state normalization | Unsupported citations cannot produce `resolved_from_source` | Mock LLM returns outside-context citation | llm-verifier/source-truth command | Force `not_verifiable` with unavailable reason | Source truth must be code-enforced |
| TAP-7 | prior finding extraction | A8 concise generated review parser | prior-findings tests | concise markdown → candidates | Concise issue bullets with `Sources:` produce candidates or degraded rows, not silent disappearance | Concise `--wtf off` fixture | prior-findings command | Degrade missing severity with default/unknown severity | Preserves supported output modes |
| TAP-8 | abort path | A9 multipass planner abort guardrail | PR-flow/multipass tests | plan abort + prior brief → review/governor output | Abort output includes prior history or records explicit degraded/no-publication path | Fake multipass planner abort fixture | PR-flow/multipass command | Abort before publication if guardrail cannot be met | Prevents runtime bypass |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|---|---|---|---|---|---|---|
| A1 | planned | automated + live audit | Run TAP-1 and inspect fresh `review.md` | No prominent top-level `### Internal DA coverage` in ordinary body; complete DA coverage still in audit output | prompts, runtime.py, report governor | Choose appendix vs artifact-only shape |
| A2 | planned | automated | Run TAP-2 | Repeated display-ID/origin mismatch does not replay cache | memory_store.py, finding_identity.py, source_truth.py | Pick persisted identity digest fields |
| A3 | planned | automated | Run TAP-3 | Untrusted body role words remain untrusted | discussion_signals.py, disposition.py | Author role metadata source may need config |
| A4 | planned | automated | Run TAP-4 | Metadata paths outside session rejected/degraded | cure_sessions.py, cure.py | Duplicate resolver cleanup likely needed |
| A5 | planned | automated | Run TAP-5 | Cached linker groups validated against current identity | discussion_linker.py, memory_store.py | Digest shape shared with A2 if possible |
| A6 | planned | automated | Run TAP-6 | Outside-context citation cannot confirm resolution | llm_verifier.py, source_truth.py | Need inspected-context provenance in result |
| A7 | planned | integration | Run TAP-5 runtime-policy branch | Linker uses prepared runtime/env/add-dir/config | cure.py, discussion_linker.py | Avoid duplicating provider wiring |
| A8 | planned | automated | Run TAP-7 | Concise prior reviews produce candidates/degraded identity | prior_findings.py | Severity fallback wording |
| A9 | planned | integration | Run TAP-8 | Planner abort cannot publish guardrail-free review | cure.py multipass path, runtime.py | Decide abort vs synthetic issue-history output |

## Discovery Notes

- Latest PR #22 sandbox: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739`; head `372b4a753099c4b6e077d98551da51039222a16b`; review completed with REQUEST CHANGES.
- Strict multipass `### Step Result:` regression is closed in that sandbox: all step artifacts begin with `### Step Result:` and strict grounding has no invalid artifacts.
- A17 and A19 live gates pass in that sandbox: report-governor is warn-only/successful and `DA-0006` is `out-of-scope` / `move_out_of_scope`, not carried forward.
- `### Prior Review Issue History` rows are prior issue identities from prior corpus/comments/sessions, but their current statuses were recomputed during the run: 14 `llm_finding_verifier` rows plus one FB-026 policy override; no `memory_cache` source-verification provenance was found for the history statuses.
- `### Internal DA coverage` is audit/provenance/debug output. The consumer-facing shape decision for this story is: remove it from the ordinary visible review body; keep complete coverage in an audit surface.

## Critical Files

- `prompts/default.md` and subsequent-aware `prompts/mrereview_*.md` — final output guidance.
- `cure_subsequent_review/runtime.py` — governor brief, sanitization prompt, report-governor audit, runtime phase hooks.
- `cure_subsequent_review/memory_store.py` — source-verification and linker cache replay gates.
- `cure_subsequent_review/finding_identity.py` — stable group/origin/fingerprint identity data.
- `cure_subsequent_review/discussion_signals.py` and `discussion_linker.py` — authority and link classification/cache boundaries.
- `cure_subsequent_review/llm_verifier.py` and `source_truth.py` — inspected source context and citation normalization.
- `cure_sessions.py` and duplicated zip-selection helpers in `cure.py` — historical artifact path containment.
- `cure_subsequent_review/prior_findings.py` — generated/concise review parser.
- `_pr_flow_impl` / multipass planner paths in `cure.py` — runtime policy and planner-abort guardrails.

## Implementation Notes

1. Start with red tests for A1 because it is product-visible and changes the prompt/report contract: ordinary review consumers should see human issue history, not DA row ledgers.
2. Then harden identity/cache boundaries (A2/A5) before or alongside source-boundary fixes (A4/A6), because several findings share ordinal/group identity failure modes.
3. Treat A3 authority classification as policy-sensitive: if role metadata is unavailable, default to `untrusted` rather than inferring trust from content.
4. Preserve Story 04's successful A17/A19 behavior while moving DA coverage to an audit surface.
5. Run a fresh PR #22 live audit after implementation; the acceptance is not done until live output no longer exposes DA coverage prominently and the request-changes hardening findings are absent or explicitly out of scope.

## Locked Decisions

- Keep DA row coverage; remove/demote the visible `### Internal DA coverage` section from ordinary consumer-facing `review.md`.
- Memory and linker caches remain optimizations only; absence of stable identity proof must force re-verification/re-linking.
- Discussion body text is evidence content, not authority metadata.
- New feedback belongs in this fresh story rather than expanding completed Story 01-04 contracts in place.

## Plan Review Log

- 2026-06-13T10:05:45Z Initial plan draft scaffolded from PR #22 live-audit ingestion. Requires fresh plan review before implementation.
- 2026-06-13T10:19:08Z Plan review APPROVED. Activated risk lenses: consumer-facing output/provenance separation (A1/TAP-1), memory/cache identity (A2/A5/TAP-2/TAP-5), untrusted discussion authority (A3/TAP-3), path traversal/session containment (A4/TAP-4), verifier citation trust boundary (A6/TAP-6), runtime policy wiring (A7/TAP-5), prior finding parsing (A8/TAP-7), multipass abort guardrails (A9/TAP-8), TAP/proof adequacy, and test feasibility/overbreadth. Rationale: Story A1-A9, TAP-1..TAP-8, and the proof matrix map directly to the live-audit FB-030..FB-038 findings and verified runtime modules; no plan-blocking gaps found before implementation.
