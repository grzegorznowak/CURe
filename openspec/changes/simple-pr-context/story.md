Plan: 🟢 PLAN APPROVED
Status: ✅ DONE

## Purpose

Deliver an opt-in pilot that gives supported built-in `cure pr` reviews a bounded orientation brief from the selected pull request's remote discussion. Preserve the complete normalized same-PR remote corpus unchanged for audit, but send only a deterministic bounded subset to the orientation model and inject only a bounded brief. If enrichment fails, warn and continue through the ordinary context-free review without swallowing unrelated review/process failures.

This amendment supersedes the prior automatic, unbounded, local-plus-remote, fail-hard contract. Completing this story enables only an opt-in pilot; default-on/general release requires a separate operator-approved follow-up based on evidence.

## Actors

- **Primary:** CURe operator, who explicitly enables or disables PR context.
- **Secondary:** review LLM, which consumes bounded context only in supported reconciliation/synthesis stages.
- **Affected:** PR authors/reviewers, whose same-PR remote discussion may influence the pilot review.
- **Reviewer/operator:** evaluates context-on/context-off evidence before any broader rollout.

## Triggering Need

Blind reviews can duplicate already-discussed concerns or ignore decisions recorded in PR discussion. The earlier plan overreached by coupling the MVP to local session history, feeding every remote event to the model, failing the whole review on enrichment errors, and enabling automatically. The approved P0 amendment bounds cost/context, removes local history from the MVP, adds operator control/fail-open behavior, and defines minimal pilot evidence.

## Expected Prerequisites

- Existing strict GitHub list adapter and three selected-PR endpoint normalizer.
- Existing built-in singlepass draft/reconcile and multipass plan/step/synth execution boundaries.
- No local CURe session/history prerequisite.

## Scope

- Add paired Boolean CLI control `--pr-context` / `--no-pr-context`, default off.
- Decide eligibility before fetch; custom prompts/files and unsupported profiles bypass without discussion/orientation calls.
- Treat `--if-reviewed list|latest|prompt-selected` returns and `--no-review` as non-review routes outside the PR-context invocation boundary, even when `--pr-context` is supplied: perform no discussion/orientation call, create no PR-context artifact, and create no new `pr_context` metadata record.
- Fetch only selected-PR issue comments, reviews, and inline review comments.
- Preserve every normalized remote event unchanged and ordered in the audit result/artifact.
- Select orientation input deterministically within the budget remaining under the fully assembled orientation-generation prompt cap.
- Produce and inject a bounded five-section orientation brief.
- Fail open visibly at PR-context enrichment boundaries.
- Record stable pilot metadata and support otherwise-comparable context-on/context-off runs.
- Remove current local session/history discovery, local review inputs/artifacts, filesystem coupling, and local-history corruption semantics.
- Keep existing strict GitHub array/page behavior, fence-aware orientation finalization, opaque insertion, packaging, and code-evidence-wins reconciliation where compatible with this amendment.

## Out of Scope

- Finding identity or disposition model
- Blind-finding suppression primitives or semantic arbitration
- Local CURe session/history discovery, recovery, or migration
- Authoritative resolution/thread state
- Freshness digests, caching, or persistent review memory
- Richer reconciliation analytics
- Default-on/general release
- Arbitrary pilot quality thresholds
- Live GitHub/network tests
- FB-010 terminal two-attempt exception provenance

## Concrete Defaults

| Limit | Value |
|------|-------|
| Fully assembled orientation-generation prompt | 12,000 estimated tokens |
| Per-selected-event body | 1,000 estimated tokens |
| Selected events | 100 maximum |
| Orientation output | 2,000 estimated tokens |
| Injected `$PRIOR_CONTEXT` | 2,000 estimated tokens |

Estimated tokens are deterministic `ceil(len(text) / 4)` values over Unicode code points. The 12,000 value covers fixed orientation instructions, literal framing, normalized PR stats, and compact deterministic JSON for selected normalized event records; selection receives only the exact remaining budget after that overhead. Provider usage, when available, is separate actual usage and must never be labeled as an estimate.

## Scenarios / Behavior Examples

> **ID continuity:** S1-S16 describe the pre-amendment implementation/review history and are superseded as current normative scenarios where they require local history, unbounded input, automatic enablement, or fail-hard enrichment. Current scenarios begin at S17.

### S17 — Default-off and explicit operator control
- Given: a normal built-in `cure pr` review with no PR-context option.
- When: routing begins.
- Then: no discussion fetch or orientation call occurs; metadata says `bypassed/disabled_default`, enablement source `default`, and the ordinary review runs. `--pr-context` explicitly enables an eligible flow; `--no-pr-context` explicitly bypasses with `disabled_cli`.
- Covers: A19

### S18 — Unsupported/custom flow bypasses before fetch
- Given: `--pr-context` with a custom prompt, custom prompt file, or unsupported prompt/profile flow.
- When: eligibility is evaluated.
- Then: enrichment is bypassed before any discussion/orientation call, a stable reason is recorded, and ordinary operator-owned prompt behavior remains unchanged.
- Covers: A20

### S19 — Full audit corpus, bounded deterministic model input
- Given: endpoint events that approach/exceed the 12,000-estimated-token fully assembled prompt cap or the 100-event cap, including bodies over 1,000 estimated tokens and equal, offset-equivalent, missing, or invalid timestamps.
- When: context is built.
- Then: the complete normalized remote corpus remains byte-for-byte field-equivalent and endpoint-ordered in the public result and `work/pr_context_discussion.json`. Fixed instructions/framing/stats are charged first; candidates follow D-13's total order, stop at the first full-prompt/count limit, cap only selected body copies, and restore D-13 chronological order. Exact counts, estimates, and body/count/prompt truncation flags match the deterministic oracle.
- Covers: A21

### S20 — Output and injection are independently bounded
- Given: fresh orientation output or fresh delivery context is at cap, one code point over cap, or contains an unterminated Markdown fence.
- When: finalization/delivery occurs.
- Then: finalized orientation output and fresh injection independently fit 2,000 estimated tokens; the finalized brief retains canonical usage instructions, all five headings, and valid fence structure; exact output/injection estimates and distinct truncation flags are recorded.
- Covers: A22

### S21 — Remote same-PR-only MVP
- Given: matching or corrupt local CURe sessions exist and remote bodies resemble local reviews.
- When: context is built.
- Then: no local session root or historical review file is scanned/read; only events from the selected PR's three endpoints enter the audit/selection boundary; footer/session/commit/body similarity cannot alter remote membership.
- Covers: A23

### S22 — Enrichment persistence respects the delivery boundary
- Given: eligible context is enabled and fetch, selection, orientation, required pre-delivery audit/brief persistence, or the final best-effort metadata mirror fails.
- When: `cure pr` runs.
- Then: failures before delivery warn, record D-14's first failing enrichment reason as `degraded`, and continue context-free. A post-route `work/pr_context_meta.json` failure warns once, records `persistence.meta_artifact=failed` in authoritative `meta.json::pr_context`, retains the already determined used/bypassed/degraded outcome and all delivery telemetry, does not rerun review, and is not retried. Core session `meta.json` flush failures and unrelated review/process failures retain existing propagation.
- Covers: A24

### S23 — Branch-specific delivery fails open
- Given: a blind singlepass draft or context-free multipass plan/steps have completed in a fresh, regular-resume, or completed-session incremental-resume route.
- When: singlepass context reconciliation fails, or the first fresh/resume synth call fails specifically while non-empty prior context is supplied.
- Then: singlepass retains the ordinary blind draft. Every context-bearing multipass route warns, records `degraded/context_synthesis_failed`, and retries synthesis exactly once with empty prior context using the same successful plan/step outputs. A successful retry records `context_mode=off`, combined delivery latency, and separate nullable delivery/fallback provider-usage fields; failure of that context-free synthesis propagates while authoritative session metadata retains the degradation reason and any available attempt telemetry.
- Covers: A25

### S24 — Pilot records support context-on/off comparison
- Given: otherwise comparable runs of the same PR/head/profile/model with `--pr-context` and `--no-pr-context`.
- When: the operator evaluates the pilot.
- Then: the exact D-14/D-18 metadata schema, path, and field-ownership oracle distinguishes outcome/reason, enablement/eligibility, counts, estimates, nullable provider usage, truncation, persistence, and stage latency. Existing run coordinates plus `context_mode` permit review-output comparison for duplicate/context-invalid comments without finding IDs, dispositions, or matching primitives.
- Covers: A26

### S25 — No-data enabled run
- Given: an eligible `--pr-context` run whose three endpoint arrays normalize to zero events.
- When: context composition begins.
- Then: no orientation call occurs; authoritative metadata says `bypassed/no_remote_context`; ordinary review proceeds context-free; `work/pr_context_discussion.json` is the complete empty audit array and `work/pr_context_meta.json` mirrors the final metadata when writable.
- Covers: A27

### S26 — Pilot completion does not enable general release
- Given: all implementation/proof tasks for this story pass.
- When: the story is completed.
- Then: CLI default remains off. Any default-on/general release change requires a separate operator-approved proposal using collected evidence; no invented numerical threshold silently authorizes rollout.
- Covers: A28

### S27 — Both resume routes trust only an originating used outcome
- Given: either regular `_resume_flow_impl` synthesis or completed-session incremental `_run_incremental_completed_multipass_resume` synthesis with persisted PR-context state.
- When: the route reads originating session `meta.json::pr_context` and `work/pr_context_orientation.md`.
- Then: both routes reuse the exact brief only for `outcome == "used"` plus readable UTF-8, nonempty, structurally valid, at-most-2,000-token content; all other metadata/brief variants inject `""`, record D-14's resume reason, perform no discussion fetch/orientation, and leave no raw `$PRIOR_CONTEXT` token.
- Covers: A31

### S28 — Nonempty remote audit can select no model context
- Given: an enabled eligible run with a nonempty normalized endpoint corpus whose first newest-first candidate cannot fit after fixed prompt/framing overhead.
- When: bounded selection runs.
- Then: the complete nonempty audit corpus/artifact is preserved unchanged, no event is selected, no orientation call occurs, metadata says `bypassed/no_selected_context`, and ordinary review proceeds context-free. This is distinct from zero normalized events, which remains `bypassed/no_remote_context`.
- Covers: A32

### S29 — Resume with no new delivery preserves origin evidence
- Given: `_resume_flow_impl` reaches either the completed/same-head fast no-op or a regular reusable-review-artifact branch that skips synthesis.
- When: the resume completes without reconciliation or synthesis and therefore creates no new PR-context delivery decision.
- Then: the originating session `meta.json::pr_context` value is preserved deep-equal with no key/value mutation, no new `work/pr_context_meta.json` mirror attempt occurs, and lifecycle timestamps/status may change without misclassifying the existing review artifact as a new context-on/off run.
- Covers: A26

### S30 — Historical-review selection exits before PR-context work
- Given: completed sessions exist and `cure pr --pr-context` is invoked with `--if-reviewed list`, `--if-reviewed latest`, or interactive `--if-reviewed prompt` where the operator selects an existing review.
- When: `_pr_flow_impl` serves the historical-session action.
- Then: it returns before sandbox/session creation, performs no discussion fetch or orientation call, writes no PR-context artifact or metadata, and does not mutate the selected historical session.
- Covers: A33

### S31 — `--no-review` never enriches
- Given: `cure pr --no-review --pr-context` proceeds through its existing session/index-only route.
- When: `_pr_flow_impl` reaches review routing.
- Then: it performs no discussion fetch, selection, orientation, reconciliation, or synthesis; writes no `work/pr_context_*` artifact and no `meta.json::pr_context`; and preserves the existing `--no-review` completion behavior.
- Covers: A34

## Acceptance

> **ID continuity:** A1-A18 and their TAP-01..TAP-13 evidence remain historical implementation records. They are not current authority where they require local history, complete remote model input, automatic activation, or fail-hard enrichment. Current amended acceptance begins at A19.

- A19: **Boolean control/default:** `cure pr` exposes paired `--pr-context` / `--no-pr-context`; omission defaults off. Metadata records `enablement_source=default|cli_explicit`. Disabled paths perform no discussion/orientation call.
- A20: **Eligibility before I/O:** custom prompt, custom prompt-file, and unsupported profile flows bypass before fetch/orientation with stable reasons and ordinary context-free behavior.
- A21: **Deterministic bounded orientation prompt:** the complete normalized selected-PR remote corpus remains field-equivalent and endpoint-ordered in the public result and `work/pr_context_discussion.json`; selection mutates only body fields on model-input copies. The exact fully assembled orientation-generation prompt—including fixed instructions, literal framing, normalized PR stats, and compact deterministic selected-event JSON—fits 12,000 estimated tokens. Event bodies fit 1,000 estimated tokens, at most 100 events are admitted using D-13's valid/equal/missing/invalid timestamp order and stop-at-first-limit rule, and selected records use D-13 chronological order. Exact selected/omitted/body-truncated counts, full-prompt estimate, and body/count/prompt flags are reproducible at cap-1/cap/cap+1.
- A22: **Output/injection caps:** finalized orientation output and freshly injected `$PRIOR_CONTEXT` each independently fit 2,000 estimated tokens at cap-1/cap/cap+1. A non-empty finalized brief retains canonical usage instructions, all five required headings, and valid fence structure. Exact orientation-output/injected estimates and separate orientation-output/injected truncation flags are recorded.
- A23: **Remote-only composition:** no production PR-context path scans local CURe sessions/history or returns local past reviews. Endpoint membership alone defines the complete remote audit corpus; no footer/session/head/similarity parsing controls membership.
- A24: **Phase-correct persistence fail-open:** fetch, selection, orientation, and required pre-delivery discussion/brief write failures warn, record `degraded` with D-14's first-failure reason, and continue context-free. Final `work/pr_context_meta.json` mirror failure warns once, is not retried, records `persistence.meta_artifact=failed` in authoritative session `meta.json::pr_context`, and retains the already determined route outcome, context mode, review artifact, usage, and latency without rerunning delivery. Core `meta.json` flush plus unrelated checkout, prompt/profile, cancellation, ordinary review, output/posting, and process-control failures preserve existing propagation.
- A25: **Delivery fail-open:** built-in singlepass reconciliation failure retains the ordinary blind draft. In fresh, regular-resume, and completed-session incremental-resume routes, a synthesis failure attributable to non-empty prior context records `degraded/context_synthesis_failed` and adds exactly one empty-context synth-stage invocation from the same successful plan/step outputs, with no second PR-context fallback. Successful retry records `context_mode=off`, combined delivery latency, and separate nullable delivery/fallback provider-usage fields; failure of the context-free retry propagates while authoritative session metadata retains the degradation reason and available attempt telemetry.
- A26: **Stable pilot observability:** every fresh or resume route that enters a PR-context delivery decision records the exact D-14/D-18 metadata schema and deterministic path/reason/field-ownership oracle, including outcome `used|bypassed|degraded`, reason, enabled/eligible/source, counts, estimates, nullable provider usage, truncation, persistence, stage latency, and `context_mode`. Completed/same-head fast no-op and reusable-review-artifact branches that perform no synthesis/reconciliation are not new PR-context invocations: they preserve the originating `meta.json::pr_context` value deep-equal with no key/value mutation and make no new metadata-mirror attempt. Existing PR/head/profile/model/run coordinates plus `context_mode` support context-on/off review-output comparison; estimates are never provider usage, and no finding identity/disposition/matching field is introduced.
- A27: **No-remote-data bypass:** an enabled eligible run whose three endpoint arrays normalize to zero events skips orientation, records D-14's `bypassed/no_remote_context` values, writes the complete empty `work/pr_context_discussion.json`, proceeds context-free, and mirrors final metadata to `work/pr_context_meta.json` when writable under D-16.
- A28: **Release gate:** final story state leaves the CLI default off and documents that default-on/general release requires a separate operator-approved evidence review. No numerical quality threshold is invented by this story.
- A29: **Regression preservation:** strict GitHub list decoding/pagination, complete remote audit ordering, fence-aware orientation finalization, opaque insertion, packaging, and context-free built-in review behavior remain covered where not superseded.
- A30: **Explicit exclusions:** no finding identity/disposition primitive, local history, authoritative resolution, freshness/cache, persistent memory, or richer reconciliation analytics is introduced.
- A31: **Resume persisted-context authority:** regular `_resume_flow_impl` and completed-session incremental `_run_incremental_completed_multipass_resume` reuse `work/pr_context_orientation.md` if and only if originating session `meta.json::pr_context.outcome == "used"` and the exact brief is readable UTF-8, nonempty, structurally valid, and within 2,000 estimated tokens. Missing/bypassed/degraded/legacy/other metadata or missing/malformed/non-UTF-8/invalid/over-cap brief injects `""`, records the exact resume bypass reason, performs no discussion fetch/orientation, and leaves no raw template token.
- A32: **No-selected-context bypass:** a nonempty normalized corpus with zero admitted events preserves its complete audit result and `work/pr_context_discussion.json`, skips orientation, records D-14's exact `bypassed/no_selected_context` counts/context-mode values, proceeds context-free, and mirrors final metadata under D-16; `no_remote_context` remains reserved for zero normalized events.
- A33: **Historical-selection non-invocation:** with explicit `--pr-context`, each completed-session `--if-reviewed list|latest|prompt-selected` return occurs before sandbox/session creation, makes no discussion/orientation call, writes no PR-context artifact or metadata, and leaves historical sessions unchanged.
- A34: **No-review non-invocation:** with explicit `--pr-context`, the `--no-review` route preserves its existing session/index-only completion while making no discussion/selection/orientation/reconciliation/synthesis call and writing neither `work/pr_context_*` nor `meta.json::pr_context`.

## Verification

### Verification Commands

- Parser and runtime routing: `python -m pytest tests/test_cure_pr_flow.py::test_parser_pr_context_is_paired_and_defaults_off -v`; `python -m pytest tests/test_reviewflow_unittest.py -k 'pr_flow_prior_review or pr_flow_no_review_skips_review_only_setup' -v`; and `python -m pytest tests/test_cure_pr_flow.py -v`
- Remote normalization, selection, orientation, artifacts, and adapter regression: `python -m pytest tests/cure_pr_context tests/test_cure_github.py -v`
- Exact persisted-context validation and regular/incremental resume orchestration owners: `python -m pytest tests/cure_pr_context/test_runtime.py tests/test_cure_pr_flow.py -v`; and `python -m pytest tests/test_reviewflow_unittest.py -k '(resume_flow_from_synth and (pr_context or prior_context)) or (incremental_completed_resume and pr_context)' -v`
- Combined amended proof: `python -m pytest tests/cure_pr_context tests/test_cure_github.py tests/test_cure_pr_flow.py tests/test_reviewflow_unittest.py -q`
- Full regression: `python -m pytest tests/ -x --timeout=120`
- Changed-path Ruff: `base="$(git merge-base HEAD origin/main)"; mapfile -d '' -t py_paths < <({ git diff --name-only --diff-filter=ACMR -z "$base" -- '*.py'; git ls-files --others --exclude-standard -z -- '*.py'; } | sort -zu); ((${#py_paths[@]} == 0)) || ruff check "${py_paths[@]}"`
- Typed production boundary: `mypy cure_github.py cure_pr_context/`
- Package smoke: `tmp="$(mktemp -d)"; python -m build --wheel --outdir "$tmp/dist" && python -m pip install --no-deps --target "$tmp/site" "$tmp"/dist/*.whl && PYTHONPATH="$tmp/site" python -c 'import cure_github, cure_pr_context'`
- Complete-delta hygiene: `base="$(git merge-base HEAD origin/main)"; git diff --check "$base" --`
- Structural reviewer action: inspect S17-S31 → A19-A34 → TAP/APM rows plus D-09/D-13/D-14/D-17/D-18 and confirm every matrix variant, including unrelated build/orientation faults and parser-accepted aware year-boundary timestamps, has exactly one owning executable row before changing proof maturity.

### Feedback Source and Disposition

- **FB-019:** endpoint-owned remote membership; retained for full audit membership.
- **FB-020:** complete remote corpus retained for audit; superseded only in its former implication that all events enter model input.
- **FB-021:** bounded fully assembled orientation prompt/body/count/output/injection contract; current.
- **FB-022:** remote same-PR-only MVP; current and supersedes local corpus obligations.
- **FB-023:** paired opt-in/default-off control, used-outcome-gated resume, and visible fail-open behavior; current and supersedes automatic/fail-hard obligations.
- **FB-024:** stable pilot observability and separate general-release gate; current.
- **FB-031:** escaped fail-open catch-width recurrence; require a genuine `_pr_flow_impl` fault seam proving unrelated `OSError`/`UnicodeError` from context construction or orientation-file handling propagates rather than becoming `artifact_write_failed`.
- **FB-032:** canonical proof-owner correction; TAP-14, TAP-18, and TAP-19 commands and owner lists must collect the actual paired parser, singlepass delivery, D-18 metadata, persisted-context validator, and current regular-resume route owners before affected proof can return to final.
- **FB-033:** parser-accepted timezone-aware year-boundary timestamps remain valid even when direct UTC conversion overflows; D-13 ordering and TAP-15 must prove a total, instant-correct, overflow-safe order without reclassifying them invalid.
- **GATE-001:** latest implementation review found the canonical Ruff inventory omitted untracked Python owners; the gate now unions merge-base tracked changes with untracked, non-ignored Python paths before Ruff.
- **PRC-001:** latest implementation review found remote-only orientation mislabeled as including past CURe reviews; all singlepass/shared multipass delivery headings must identify selected-PR remote discussion only.
- **PRC-002:** latest implementation review found a dead persisted-orientation reader bypassing D-15; remove it so `cure_pr_context.runtime.read_persisted_context()` remains the sole validation authority.
- **FB-010:** terminal retry provenance remains deferred.

### Fail-open Checks

| Render / route | Enabled activation proof | Disabled/fallback proof | Raw-token / swallowed-failure guard |
|---|---|---|---|
| Fresh built-in singlepass (`_pr_flow_impl` → `_reconcile_prior_context`) | nonempty brief appears exactly once in reconciliation input after a fresh blind draft | default/explicit-off/custom/unsupported and reconciliation-failure branches accept the ordinary draft without fetch/orient or a second successful context call | no unresolved `$PRIOR_CONTEXT`; blind-draft/acceptance failures still propagate |
| Fresh built-in multipass (`_pr_flow_impl` → `_render_synth_prompt_with_prior_context` → `mrereview_gh_local_big_synth.md`) | nonempty brief is opaquely inserted exactly once only at synth | disabled/degraded path renders the same synth with `""` and reuses successful plan/steps | no raw `$PRIOR_CONTEXT`; fallback synth failure propagates |
| Regular resume (`_resume_flow_impl`, shared synth template) | D-15 used-valid persisted brief is inserted byte-for-byte; context-bearing synth success is observed | every non-used/invalid variant injects `""`; a used-valid context synth failure gets exactly one empty retry from unchanged plan/steps | no raw token/network; successful fallback is `degraded/context_synthesis_failed` with `context_mode=off`; fallback failure propagates |
| Completed-session incremental resume (`_run_incremental_completed_multipass_resume`, `mrereview_gh_local_big_resume_synth.md`) | D-15 used-valid brief is inserted byte-for-byte in the incremental synth template; context-bearing synth success is observed | every non-used/invalid variant injects `""`; a used-valid context synth failure gets exactly one empty retry from unchanged plan/steps | template gains exactly one owned token; no raw token/network; successful fallback metadata and fatal fallback failure match the regular route |
| Resume no-delivery branches | no activation: completed/same-head fast no-op and regular reusable-review-artifact branch execute no synth/reconcile | originating `meta.json::pr_context` remains deep-equal without key/value mutation and no new metadata mirror is attempted | D-17 prevents stale origin evidence from being relabeled as a new context-on/off invocation |
| Historical-selection exits | no activation: `--if-reviewed list|latest|prompt-selected` returns before sandbox/session creation even with `--pr-context` | historical output/list behavior remains unchanged; no PR-context call, artifact, metadata, or historical-session mutation | these are not review invocations and therefore do not enter D-14 |
| `--no-review` | no activation even with `--pr-context` | existing session/index-only completion remains unchanged; no fetch/select/orient/reconcile/synth or PR-context artifact/metadata | route is outside D-14 because no review delivery can occur |
| Metadata mirror | final route metadata is written once after successful delivery, successful fallback, or bypass telemetry is known | mirror failure is warning-only and not retried; authoritative session metadata retains route and persistence failure | no attempt on D-17 no-delivery, A33/A34 non-invocations, or failed ordinary fallback; session `meta.json` flush failure remains process-control propagation |

### Input Boundary Shape Risk

| Boundary | Raw Input Source | Strict Assumption | Variant / Case | Evidence | Mitigation / Exclusion |
|---|---|---|---|---|---|
| GitHub list adapter | `gh api --paginate` / public fallback bytes | each document/page is an array of objects | empty array, blank, malformed JSON, scalar/object, mixed pages, multi-page arrays | TAP-21 at `tests/test_cure_github.py` and `tests/cure_pr_context/test_fetcher.py` | retain strict adapter; no live network |
| Three endpoint items | issue comments, reviews, inline comments | normalized object fields without changing endpoint membership | missing user/body/id, review submitted time, inline line/path, footer/session-like text | TAP-21 | preserve complete endpoint-owned audit membership and field normalization |
| `created_at` ordering | normalized external timestamp strings | every nonempty timezone-aware value accepted by `datetime.fromisoformat(value.replace("Z", "+00:00"))` is a valid sort instant | `Z`, equal instants expressed with different offsets, equal timestamp, parser-accepted aware minimum/maximum-year values whose direct UTC conversion would underflow/overflow, naive, malformed, empty/missing | TAP-15 | D-13 overflow-safe total order; parser-accepted aware values are never reclassified invalid and the raw value remains unchanged in audit/model copy |
| PR stats / prompt assembly | computed mapping and selected normalized records | JSON-safe finite values and exact canonical serialization | absent stats, Unicode, sorted nested keys, `NaN`/non-serializable values, cap-1/cap/cap+1 | TAP-15 | canonical JSON; assembly failure is `degraded/selection_failed` |
| Orientation Markdown | LLM text | five real headings, canonical instructions, valid fences, <=2,000 estimate | cap boundary, fenced pseudo-headings, shorter/equal/longer close, unterminated fence | TAP-16 | cap-aware finalizer reserves structure and closes fences |
| Persisted origin metadata | session `meta.json::pr_context` | mapping with exact `outcome == "used"` for reuse | missing file/key/outcome, legacy shape, bypassed/degraded/other, malformed JSON/non-object | TAP-19/TAP-20 | D-15 rejects to empty context without network |
| Persisted brief | `work/pr_context_orientation.md` bytes | readable UTF-8, nonempty, finalized structure, <=2,000 estimate | missing, directory, invalid UTF-8, empty, malformed headings/fence, cap/cap+1 | TAP-19/TAP-20 | exact reuse only; no repair/truncation |
| Artifact filesystem | `work/` paths and writes | fixed contained filenames and atomic complete writes | parent/path/write failure before delivery; final meta-mirror failure after route | TAP-18 | D-16 phase semantics; no dynamic/untrusted path |
| Provider telemetry | optional adapter usage mapping | nullable integers never substituted by estimates | observer absent/`None`, partial mapping, available delivery/fallback usage | TAP-18 | normalize missing fields to `null`; telemetry never controls behavior |

### Surface / Branch Proof Matrix

| Surface | Supported Variant | Internal Execution Branch | Proof Class | Owning Proof Seam | Why This Seam Is Sufficient | Out of Scope Notes |
|---|---|---|---|---|---|---|
| Fresh built-in singlepass | omitted / explicit-off | `_pr_flow_impl` eligibility before fetch | behavior | TAP-14, `tests/test_cure_pr_flow.py` | real flow sentinels prove no I/O and one ordinary draft | custom prompt content itself unchanged |
| Fresh built-in singlepass | explicit-on normal/big | blind draft → reconcile | behavior | TAP-17 | real review artifact proves context activation and draft retention fallback | no context in initial draft |
| Fresh built-in multipass | explicit-on | plan/steps without context → shared synth with context / empty retry | behavior | TAP-17 plus TAP-16 template proof | real flow captures plan/steps/synth and final artifact | no plan/step context |
| Fresh custom prompt / file | explicit-on | eligibility bypass | routing + behavior | TAP-14 | real flow fetch/orient sentinels plus unchanged prompt capture | custom reconciliation unsupported |
| Fresh unsupported profile | explicit-on | eligibility bypass | routing + behavior | TAP-14 | exact profile fixture and no-I/O sentinels | named unsupported set is program-owned |
| Historical completed-session selection | `--if-reviewed list|latest|prompt-selected` plus explicit-on | pre-session return in `_pr_flow_impl` | behavior | TAP-14 | real-flow output plus sandbox/history snapshots and fetch/orient bombs prove no invocation or mutation | `--if-reviewed new` continues to normal eligibility |
| Fresh no-review | `--no-review` plus explicit-on | session/index-only branch in `_pr_flow_impl` | behavior | TAP-14 | established real no-review flow plus fetch/select/orient/reconcile/synth bombs and artifact/meta absence prove no enrichment | indexing remains existing behavior |
| Regular resume | used-valid success / used-valid context-synth failure / every rejected metadata-or-brief shape | `_resume_flow_impl` shared synth | behavior | TAP-19 | real executor captures prove exact-or-empty insertion, exactly one empty fallback with unchanged plan/steps, successful-fallback metadata, fatal retry propagation, and no network | no refetch/reorientation |
| Regular resume no-delivery | completed/same-head fast no-op / reusable review artifact | `_resume_flow_impl` before incremental dispatch or with `should_synth == false` | behavior | TAP-18/TAP-19 | deep-equal before/after `meta.json::pr_context` and mirror-attempt sentinels prove D-17 preservation | lifecycle status/timestamps remain owned by resume |
| Completed-session incremental resume | used-valid success / used-valid context-synth failure / every rejected metadata-or-brief shape | `_run_incremental_completed_multipass_resume` incremental synth | behavior | TAP-20 | distinct real incremental executor captures prove exact-or-empty insertion, one empty fallback, metadata, fatal retry propagation, and retained guidance | no refetch/reorientation |
| Remote audit | empty / nonempty / zero-selected / body-truncated | `fetch_pr_discussion` → `build_pr_context` artifact | behavior | TAP-15/TAP-21 | public result plus real file read prove complete endpoint order | live network excluded |
| Local history | matching/corrupt sessions present | production composition sentinel | behavior | TAP-21 | read/scan sentinels at removed owners prove no filesystem coupling | migration excluded |
| Metadata/persistence | used/bypassed/degraded, early/late write failure, and no-delivery resume preservation | session meta plus work mirror | behavior | TAP-18/TAP-19 | exact dict/file equality, malformed-origin/fake-clock/usage fixtures, and deep-equal/no-mirror sentinels prove D-14/D-17/D-18 oracle | finding-level analytics excluded |

### Design Sources

| Source | Status | Durable anchor |
|---|---|---|
| Initiative P0 decisions | normative | `openspec/initiatives/simple-pr-context/initiative.md::FB-021` through `FB-024` and `## Decisions & Constraints` |
| Technical design | normative | `openspec/changes/simple-pr-context/design.md::Deterministic selection`, `::Stable metadata contract`, `::Field-level fresh/resume metadata oracle`, `::Persistence and delivery phase semantics` |
| Historical implementation/PR material | orientation only | `story.md::Implementation Log` and Plan Review Log's historical branch/PR anchors; superseded where they conflict with FB-021-FB-024 |

### Design Element Trace

| Source Anchor | Visible Element / State | Obligation | Bounds / Required Behavior | Scenario | Acceptance ID | Proof Row / Reviewer Action |
|---|---|---|---|---|---|---|
| FB-023 / design eligibility | paired CLI/default off | required | omission and explicit disable perform no enrichment I/O | S17/S18 | A19/A20 | TAP-14 parser + real-flow commands |
| FB-023 / review-only enrichment boundary | historical-selection and `--no-review` non-invocations | required | explicit-on cannot create enrichment work/artifacts/metadata when no new review is delivered | S30/S31 | A33/A34 | TAP-14 real pre-session/no-review flow |
| FB-021 / D-13 | audit/model split and deterministic selection | required | 12k/1k/100, complete audit, exact total orders | S19 | A21 | TAP-15 cap/order/audit fixtures |
| FB-021 / orientation finalization | output/injection caps | required | independent 2k caps with headings/instructions/fences | S20 | A22 | TAP-16 output/template fixtures |
| FB-022 | remote-only MVP | required | three endpoints; no local scan/read | S21 | A23 | TAP-21 raw-boundary/sentinel proof |
| FB-023 / D-16 | phase-correct fail-open | required | early context-free fallback; late mirror retention/no retry | S22 | A24 | TAP-18 persistence plus TAP-22 negative propagation |
| FB-023 | branch delivery fallback | required | blind draft retention / one empty synth retry on fresh and both resume synth routes | S23 | A25 | TAP-17/TAP-19/TAP-20 real executor captures plus TAP-22 propagation |
| FB-024 / D-14/D-17/D-18 | pilot observability | required | exact entered-path and field-ownership schema/oracle; no-delivery resume preserves origin evidence; comparison coordinates | S24/S29 | A26 | TAP-18/TAP-19 exact metadata/file/no-mirror assertions |
| FB-023 | zero-data distinctions | required | empty remote vs nonempty zero-selected reasons/artifacts | S25/S28 | A27/A32 | TAP-15/TAP-18 |
| FB-024 | release gate | required | default remains off; separate approval | S26 | A28 | TAP-23 source/runtime gate |
| FB-023 / D-15 | both resume routes | required | used-valid exact reuse only; all others empty/no-network | S27 | A31 | TAP-19/TAP-20 real prompt captures |

### Risk Lens Inventory

| Lens | Activation | Proof / explicit exclusion |
|---|---|---|
| External service / network / subprocess | GitHub CLI/public API list input | TAP-21 deterministic fakes; live network excluded |
| Filesystem / persistence / generated artifacts | audit, brief, metadata mirror, persisted resume input | TAP-18/TAP-19/TAP-20; fixed contained paths and early/late semantics |
| Retries / process lifecycle | one context-free synth retry on fresh and both resume delivery routes; no metadata-mirror retry | TAP-17/TAP-18/TAP-19/TAP-20/TAP-22 exact invocation counts, metadata, and propagation |
| Prompt/template naming | `$PRIOR_CONTEXT` in shared and incremental synth templates | TAP-16/TAP-19/TAP-20 exact-one token and captured render proof |
| Raw shape / serialization | endpoint JSON, timestamp parsing, canonical prompt JSON, persisted metadata/UTF-8 | Input Boundary Shape Risk rows and TAP-15/TAP-21 |
| Time / telemetry | monotonic stage latency and nullable provider usage | TAP-18 fake clock/adapter variants; no wall-clock/live provider |
| Concurrency / async / permissions / migrations / UI | no new behavior in this story | explicitly excluded; existing process permissions/UI behavior unchanged |

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|---|---|---|---|---|---|---|---|---|---|
| TAP-14 | parser + fresh routing | A19/A20/A27/A33/A34 | `tests/test_cure_pr_flow.py::test_parser_pr_context_is_paired_and_defaults_off`; `tests/_reviewflow_unittest_grounding_impl.py::{test_pr_flow_prior_review_latest_happens_before_picker,test_pr_flow_no_review_skips_review_only_setup}` extended with adjacent list/prompt-selected and PR-context sentinels; `tests/test_cure_pr_flow.py` planned `test_pr_context_*eligibility*` cases | `build_parser` and real `_pr_flow_impl` pre-session returns, no-review route, and boundary before `fetch_pr_discussion` | paired parse values/source; omitted/off/custom/file/unsupported no fetch/orient; enabled empty endpoints bypass; list/latest/prompt-selected and no-review explicit-on paths make no context call/artifact/meta or historical mutation | argparse vectors; seeded completed sessions and TTY choices; sandbox/history snapshots; monkeypatched fetch/orient/reconcile/synth bombs; no network | `python -m pytest tests/test_cure_pr_flow.py::test_parser_pr_context_is_paired_and_defaults_off -v`; `python -m pytest tests/test_reviewflow_unittest.py -k 'pr_flow_prior_review or pr_flow_no_review_skips_review_only_setup' -v`; `python -m pytest tests/test_cure_pr_flow.py -k 'pr_context and (eligibility or no_remote)' -v` | if the established broad-flow owner cannot express a sentinel, add a focused real-flow case in `tests/test_cure_pr_flow.py`; never replace behavior proof with parser/helper-only proof | one row owns operator routing before review creation; each independent exit gets its own fixture/assertions |
| TAP-15 | package/public composition | A21/A32 | `tests/cure_pr_context/test_corpus.py`, `test_init.py`, `test_integration.py` | `select_orientation_events` through `build_pr_context` and real discussion artifact write | D-13 cap/order oracle including parser-accepted aware year-boundary values whose direct UTC conversion overflows; exact counts/flags; complete unchanged audit for empty/nonempty/zero-selected/body-truncated cases | deterministic Unicode canonical JSON; valid/equal/offset-equivalent/parser-accepted aware minimum/maximum-year UTC-overflow/missing/invalid timestamps; cap-1/cap/cap+1; tmp work dir | `python -m pytest tests/cure_pr_context/test_corpus.py tests/cure_pr_context/test_init.py tests/cure_pr_context/test_integration.py -v` | if public composition obscures a boundary, retain public proof and add selector unit fixtures rather than replacing it | selector and artifact are merged because A21 requires both selected prompt and unchanged public/file audit |
| TAP-16 | orientation + template assembly | A22/A29 | `tests/cure_pr_context/test_orient.py`, `test_templates.py` | finalizer and exact-one opaque insertion into `prompts/mrereview_gh_local_big_synth.md` and `mrereview_gh_local_big_resume_synth.md` | independent 2k estimates/flags; instructions/headings/fences; no raw token; plan/step templates context-free | cap-1/cap/cap+1 Markdown; variable fences; marker-like context bytes | `python -m pytest tests/cure_pr_context/test_orient.py tests/cure_pr_context/test_templates.py -v` | if template unit render diverges from runtime, TAP-17/19/20 runtime captures are authoritative | cheapest structure/cap proof is unit-level; runtime route activation is deliberately split |
| TAP-17 | fresh delivery behavior | A24/A25 | `tests/test_cure_pr_flow.py` planned named fail-open cases plus established singlepass/reconcile tests | real `_pr_flow_impl` blind draft/reconcile and multipass synth executor | stage warnings/reasons; early failures context-free; draft retained; exactly one empty synth retry with same plan/steps; retry failure propagates | injected exception per named enrichment stage; distinct ordinary-failure sentinels; captured prompts/artifacts | `python -m pytest tests/test_cure_pr_flow.py -k 'pr_context and (fail_open or reconcile or synthesis)' -v` | use established full-flow grounding fixture only where focused real flow cannot capture synth invocation | singlepass/multipass remain one row because they share A25 delivery fallback but each has independent assertions |
| TAP-18 | metadata + persistence | A24/A26/A27/A32 | `tests/cure_pr_context/test_init.py`; `tests/test_cure_pr_flow.py::{test_tap18_pr_context_meta_d14_d18_complete_route_dictionary,test_resume_metadata_inherits_only_sanitized_used_acquisition,test_tap18_pr_context_singlepass_fresh_success_genuine_route_owner,test_tap17_tap18_pr_context_synthesis_meta_fresh_multipass_canonical_routes,test_tap18_pr_context_meta_no_selected_artifact_genuine_route_owners,test_tap18_tap19_pr_context_meta_resume_no_delivery_same_head_genuine_route,test_tap18_tap19_tap20_resume_pr_context_empty_delivery_records_validator_and_provider_telemetry,test_tap18_empty_prior_context_synth_is_not_pr_context_delivery_telemetry,test_tap18_canonical_metadata_flush_precedes_equal_final_mirror}` plus mirror-failure route owners; the planned singlepass wrapper delegates to `tests/_reviewflow_unittest_grounding_impl.py::test_tap18_pr_context_pr_flow_singlepass_fresh_success_has_exact_authority_usage_and_route_latency` | `progress.meta['pr_context']`, session `meta.json`, `work/pr_context_meta.json`, required audit/brief writes, completed/same-head and reusable-artifact resume exits | exact D-14/D-18 schema/path/field-ownership/reason oracle including fetched-versus-normalized; fake-clock ms; nullable/available usage; early write degradation; final mirror failure retention/no retry; D-17 deep-equal origin preservation and zero mirror attempts | deterministic endpoint cardinalities and used/non-used/malformed origin dictionaries; monotonic clock; adapters absent/partial/full usage; write-failure injection by fixed artifact; seeded sentinel origin payload and mirror-write bomb | `python -m pytest tests/cure_pr_context/test_init.py tests/test_cure_pr_flow.py -v` | if package code cannot observe final delivery, keep build metadata assertions there and final/no-delivery oracle in flow tests | persistence is split from delivery because its late phase differs; one exact-dictionary parameterization owns every D-18 reset/inherit/current field class |
| TAP-19 | regular resume orchestration | A25/A26/A31 | `tests/cure_pr_context/test_runtime.py`; `tests/test_cure_pr_flow.py::{test_resume_requires_used_origin,test_resume_pr_context_reuses_exact_used_valid_brief,test_resume_pr_context_reuses_exact_crlf_brief,test_resume_rejects_invalid_used_brief,test_tap18_tap19_pr_context_meta_resume_no_delivery_same_head_genuine_route}`; `tests/_reviewflow_unittest_grounding_impl.py::{test_resume_flow_from_synth_pr_context_synthesis_reuses_exact_crlf_and_fallback_captures_calls,test_tap19_resume_flow_from_synth_prior_context_non_used_and_used_invalid_render_empty,test_tap18_tap19_resume_flow_from_synth_prior_context_same_head_d17_completed_latest_head_is_exact_no_delivery_state}` | `_resume_flow_impl`, shared synth executor/template, `_mark_resume_noop_completed`, and `should_synth` reusable-artifact decision | D-15 cross-product exact brief or `""`; used-valid first-call failure gets exactly one empty retry with unchanged plan/steps; successful fallback D-14 metadata; fallback failure propagates; D-17 no-delivery branches preserve the origin value without key/value mutation and skip mirror; no fetch/orient/raw token | origin metadata × brief matrix; scripted first/second synth outcomes with captured prompts and seeded plan/steps; sentinel origin payload; same-head and reusable-artifact fixtures | `python -m pytest tests/cure_pr_context/test_runtime.py tests/test_cure_pr_flow.py -v`; `python -m pytest tests/test_reviewflow_unittest.py -k 'resume_flow_from_synth and (pr_context or prior_context)' -v` | extend established grounding fixture if focused flow cannot prove executor prompt; do not use helper-only rendering as closure | distinct row because regular resume uniquely owns both no-delivery exits and the shared-template delivery route |
| TAP-20 | incremental completed resume orchestration | A25/A31 | `tests/_reviewflow_unittest_grounding_impl.py::test_incremental_completed_resume_threads_verbose_guidance_into_resume_synth_prompt` extended/adjacent PR-context fallback cases | `_run_incremental_completed_multipass_resume` + incremental synth executor/template | D-15 representative exact-or-empty insertion; used-valid first-call failure gets exactly one empty retry with unchanged plan/steps; successful fallback D-14 metadata; fallback failure propagates; no network/raw token; guidance retained | established completed-session fixture; used-valid/non-used/used-invalid representatives; scripted first/second synth outcomes; captured prompts and seeded plan/steps | `python -m pytest tests/test_reviewflow_unittest.py -k 'incremental_completed_resume and (prior_context or verbose_guidance or context_synthesis)' -v` | if full origin/brief cross-product is too costly, prove it in TAP-19/shared validator and retain route representatives plus complete fallback outcomes here | separate row is mandatory because this branch has its own template/callsite and must prove its own fallback executor behavior |
| TAP-21 | external/raw boundary + remote-only regression | A23/A29 | `tests/cure_pr_context/test_fetcher.py`, `test_corpus.py`, `test_init.py`, `tests/test_cure_github.py` | raw gh bytes/pages → normalized events → public composition; filesystem sentinel at removed local owner | strict arrays/pages; every endpoint event retained; footer/session-like fields ordinary; no `sandbox_root`/`past_reviews`/local read | fake HTTP/CLI pages and malformed shapes; local tree/read/scan bombs; no live network | `python -m pytest tests/cure_pr_context/test_fetcher.py tests/cure_pr_context/test_corpus.py tests/cure_pr_context/test_init.py tests/test_cure_github.py -v` | retain direct adapter tests if package fake cannot represent pagination; retain public composition for no-read proof | merged because these are the complete raw-to-public remote-only boundary and retained adapter regression |
| TAP-22 | negative failure boundary | A24/A25 | `tests/test_cure_pr_flow.py` planned `test_pr_context_does_not_swallow_*` parameterization and `test_pr_context_does_not_swallow_build_or_orientation_file_faults_genuine_route` | real `_pr_flow_impl` exceptions outside named enrichment-stage translations, including `OSError`/`UnicodeError` injected from `build_pr_context` and raw orientation cleanup/read | checkout/config/cancel/draft/plan/step/fallback synth/accept/post/session flush plus unrelated context-build/orientation-file faults preserve existing exception/control signal rather than becoming `artifact_write_failed` | one fault per stage with stage-reach sentinels; monkeypatched context builder and orientation-file operations; no network | `python -m pytest tests/test_cure_pr_flow.py -k 'pr_context and does_not_swallow' -v` | split any branch whose existing harness cannot reach the real stage; never replace with source-text assertion | isolated because a false-positive catch is a different failure signal from enrichment fallback |
| TAP-23 | final release/regression gates | A28/A29/A30 | all focused owners, `pyproject.toml`, source scan, package/full suite | installed package and complete repository delta | default off; excluded primitives absent from current production contract; all rows final; package/full/ruff/mypy/diff pass | no live network; disposable install target; merge-base changed paths | run every command under `### Verification Commands` | stop and leave proof provisional on any unavailable lane; do not substitute historical GREEN | final gates are merged because they share release disposition, not behavior implementation |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|---|---|---|---|---|---|---|
| A19 | final | automated TAP-14 | run TAP-14 parser and flow commands | omitted/off/on parse values and source; disabled no-I/O ordinary review | `cure.py::build_parser`, `_pr_flow_impl` | Canonical TAP-14 collected the actual paired parser owner (1), historical/no-review owners (4), and eligibility/no-remote owners (8); all passed. |
| A20 | final | automated TAP-14 | run TAP-14 eligibility filter | custom prompt/file/unsupported each records exact bypass before sentinels | `cure.py::_pr_flow_impl`, prompt/profile routing | custom prompt/file and unsupported-profile pre-I/O cases pass |
| A21 | final | automated TAP-15 | run package composition command and inspect cap boundary IDs | exact D-13 order, <=12k, 1k/100 limits, immutable result/file audit, counts/flags | `cure_pr_context/{corpus,__init__}.py`, discussion artifact | TAP-15 passed 31 tests, including parser-accepted aware minimum/maximum-year offset values ordered by the signed integer microsecond key without UTC conversion. |
| A22 | final | automated TAP-16 | run orient/template command | independent <=2k output/injection with exact estimates/flags, headings/instructions/fences | `orient.py`, both synth templates, fresh insertion | TAP-16 passes 16 tests; fresh orientation output and injected context are independently finalized and capped with separate estimates/truncation flags while retaining required structure and opaque insertion. |
| A23 | final | automated TAP-21 | run raw/remote-only command and inspect public signature | no local read/export/result; all endpoint-owned events retained | `fetcher.py`, `corpus.py`, `__init__.py` | remote-only public API and no-local-read sentinels pass |
| A24 | final | automated TAP-17/TAP-18/TAP-22 | run fail-open, persistence, and negative-boundary commands | early context-free degradation; late mirror retained outcome/no retry; unrelated failures propagate | `_pr_flow_impl`, session/work metadata/artifacts | TAP-18/22 passed: required orientation writes still degrade, while real build and raw orientation cleanup/read `OSError`/`UnicodeError` faults propagate unchanged. |
| A25 | final | automated TAP-17/TAP-19/TAP-20/TAP-22 | run fresh plus both exact resume fallback commands | blind draft retained; each context-bearing synth route makes one empty retry with unchanged plan/steps; successful fallback records degraded/off, combined delivery latency, and separate nullable delivery/fallback usage; fallback failure propagates with authoritative degradation evidence | singlepass reconcile; fresh, regular-resume, and incremental-resume synth executors | Canonical current fresh/regular/incremental owner commands passed, including 4 regular/incremental resume owners plus 2 subtests. |
| A26 | final | automated TAP-18/TAP-19 | run metadata and regular-resume no-delivery commands; compare exact dicts/files and mirror-attempt sentinel | D-14/D-18 entered-path values, field ownership, precedence, and telemetry; D-17 same-head/reusable exits preserve the origin value deep-equal with no key/value mutation and no new mirror; coordinates and no finding fields | session `meta.json`, `work/pr_context_meta.json`, `_mark_resume_noop_completed`, regular `should_synth` branch | Canonical TAP-18 command collected and passed all fresh singlepass, D-18 inheritance/reset/current-attempt, persistence, and no-delivery owners (75 tests with runtime/TAP-19 owners). |
| A27 | final | automated TAP-14/TAP-18 | run no-remote filter | empty audit array, no orient, bypass reason, final mirror when writable | fresh flow and work artifacts | enabled empty-endpoint artifact/bypass owner passes |
| A28 | final | automated/file read TAP-23 | run parser/default and inspect final story/release text | default false and only opt-in pilot authorized | parser, initiative/proposal/story | runtime default-off and opt-in-only source gate pass |
| A29 | final | automated TAP-16/TAP-21/TAP-23 | run retained focused/full/package commands | strict list/order/fence/opaque insertion/package/context-free regressions pass | adapter/package/templates/full flow | exact disposable build/install/import smoke and 685-test full regression pass; isolated imports resolve from the installed wheel |
| A30 | final | source/file read TAP-23 | search current production/result/meta schemas for excluded primitives and inspect scope | no finding identity/disposition/local history/cache/persistent memory/richer analytics | production delta and OpenSpec scope | current PR-context production/result/metadata exclusion scan passes |
| A31 | final | automated TAP-19/TAP-20 | run both exact resume commands | regular and incremental routes use exact used-valid brief only; all others empty/reason/no-network/no-token; used-valid delivery follows A25 fallback semantics | both resume functions, both synth executors, and both synth templates | Canonical TAP-19 collected `test_runtime.py`, public non-used/invalid validator cases, and current regular-resume owners; the combined runtime/flow lane passed 75 and the real resume lane passed 4 plus 2 subtests. |
| A32 | final | automated TAP-15/TAP-18 | run zero-selected composition/metadata cases | nonempty unchanged audit, zero selected, no orient, exact reason/counts/artifacts | selector, public composition, flow metadata | Package and genuine fresh-route proof distinguish fixed-overhead `selection_failed` from exact-cap `bypassed/no_selected_context`, preserving the complete audit artifact, exact metadata/mirror, no orientation call, and ordinary context-free delivery. |
| A33 | final | automated TAP-14 | run real historical-selection routing cases for list/latest/prompt-selected with explicit-on | no sandbox/context call/artifact/meta, unchanged historical session, and established output behavior | `_pr_flow_impl` pre-session exits | list/latest/prompt-selected non-invocation sentinels pass |
| A34 | final | automated TAP-14 | run established real no-review flow with explicit-on and context-stage bombs | session/index-only completion with no context call/artifact/meta | `_pr_flow_impl` no-review branches | explicit-on no-review artifact/metadata absence owner passes |

## Critical Files

| Path | Planned role |
|------|--------------|
| `cure.py::_pr_flow_impl` / `build_parser` | paired CLI option, historical/no-review non-invocation routing, pre-fetch eligibility, fresh singlepass/multipass delivery, D-14/D-18 metadata, and D-16 persistence sequencing |
| `cure.py::_execute_multipass_synth_stage` | shared real synth executor boundary whose fresh/regular/incremental callers own A25 context-bearing failure interception, exact one-empty retry, and fatal retry propagation |
| `cure.py::_resume_flow_impl` / `_mark_resume_noop_completed` | regular resume D-15 persisted-origin/brief gate, shared synth A25 fallback, and D-17 completed/same-head plus reusable-artifact no-delivery preservation |
| `cure.py::_run_incremental_completed_multipass_resume` | distinct completed-session incremental resume gate, incremental synth insertion, and A25 fallback |
| `cure_pr_context/__init__.py::build_pr_context` | remote-only public composition/result and required discussion/brief artifact contract |
| `cure_pr_context/fetcher.py` | complete selected-PR endpoint normalization |
| `cure_pr_context/corpus.py` | D-13 deterministic bounded remote selection; replaces local-history behavior |
| `cure_pr_context/orient.py` | bounded five-section finalization and output cap |
| `cure_pr_context/runtime.py` | fresh eligibility classification, build-metadata application, D-15 persisted-context validation, D-18 resume metadata ownership/sanitization, and atomic brief/metadata persistence |
| `cure_github.py` | retained strict list/pagination adapter |
| `prompts/mrereview_gh_local_big_synth.md` | fresh/regular shared synth exact-one opaque context token |
| `prompts/mrereview_gh_local_big_resume_synth.md` | incremental completed-resume exact-one opaque context token |
| `tests/cure_pr_context/` and `tests/test_cure_github.py` | TAP-15/TAP-16/TAP-18/TAP-21 package/raw/artifact proof |
| `tests/test_cure_pr_flow.py` | TAP-14/TAP-17/TAP-18/TAP-19/TAP-22 real fresh/regular-resume proof |
| `tests/test_cure_pr_flow.py::test_parser_pr_context_is_paired_and_defaults_off` | actual paired `--pr-context` / `--no-pr-context` parser proof owner for TAP-14 |
| `tests/cure_pr_context/test_runtime.py`; `tests/test_cure_pr_flow.py::{test_resume_requires_used_origin,test_resume_pr_context_reuses_exact_used_valid_brief,test_resume_pr_context_reuses_exact_crlf_brief,test_resume_rejects_invalid_used_brief,test_tap18_tap19_pr_context_meta_resume_no_delivery_same_head_genuine_route}`; `tests/_reviewflow_unittest_grounding_impl.py::{test_resume_flow_from_synth_pr_context_synthesis_reuses_exact_crlf_and_fallback_captures_calls,test_tap19_resume_flow_from_synth_prior_context_non_used_and_used_invalid_render_empty,test_tap18_tap19_resume_flow_from_synth_prior_context_same_head_d17_completed_latest_head_is_exact_no_delivery_state,test_tap20_incremental_completed_resume_pr_context_synthesis_reuses_exact_crlf_and_fallback_captures_calls}` | canonical persisted-context validator and current real regular/incremental synth capture owners for TAP-19/TAP-20 |
| `openspec/changes/simple-pr-context/` | amended contract, tasks, evidence, and opt-in release gate |

## Implementation Notes

### New RED-first phases

- **R10 — amended-contract RED:** add TAP-14..TAP-20 failing boundary tests before production edits. Preserve already-green historical behavior without manufacturing failures.
- **R11 — bounded implementation/GREEN:** implement remote-only bounded composition, CLI eligibility/control, fail-open delivery, and stable metadata; run each owning suite independently.
- **R12 — final gates/reconciliation:** run focused/full/quality/type/package/diff/structural checks; reconcile only from current evidence; leave default off and request fresh plan/implementation review through the normal operator workflow.
- **R13 — FB-031–FB-033 remediation RED/GREEN:** first add the genuine `_pr_flow_impl` unrelated-fault seam, the missing canonical TAP-14/TAP-18/TAP-19 owner collection, and D-13 aware year-boundary overflow-ordering cases; then make only the bounded catch/order repairs needed to turn those proofs GREEN. Preserve all existing acceptance semantics and rerun the complete canonical gates before restoring proof maturity.
- **R14 — GATE-001/PRC-001/PRC-002 review remediation:** prove selected-PR remote-only delivery labels RED-first, remove the dead D-15-bypassing reader, make the canonical Ruff inventory include untracked non-ignored Python owners, and rerun all focused and release gates before returning to review.

### Locked Decisions

- **D-04 — Audit/model split:** full normalized endpoint corpus remains unchanged in audit output; only deterministic selected copies enter orientation.
- **D-05 — Exact defaults:** 12,000 for the canonically assembled complete orientation-generation prompt, 1,000 per-body, 100 events, 2,000 output, and 2,000 injection estimated-token caps.
- **D-06 — Selection order:** newest-first admission until first limit, then chronological model-input order; no skip-to-pack behavior.
- **D-07 — Remote-only MVP:** remove all local session/history discovery and `past_reviews` API/artifact behavior without compatibility fallback.
- **D-08 — Control:** paired CLI Boolean, default off; unsupported/custom flows bypass before I/O.
- **D-09 — Fail-open boundary:** only named enrichment stages degrade. Singlepass keeps blind draft; every fresh, regular-resume, and incremental-resume multipass route that first invokes synth with non-empty context adds exactly one empty-context synth-stage invocation from the same successful plan/steps, with no second PR-context fallback. Existing grounding/manual retry policy inside either synth-stage invocation is separately owned and is not changed by this contract. A successful empty-context invocation is `degraded/context_synthesis_failed` with `context_mode=off`, combined delivery latency, and separate nullable delivery/fallback provider-usage fields; ordinary fallback/process failures propagate.
- **D-10 — Pilot metadata/release:** stable used/bypassed/degraded run records; estimates distinct from provider usage; story completion enables only opt-in pilot.
- **D-11 — Resume authority:** persisted context is reused only for originating `pr_context.outcome == "used"` plus an exact valid/in-cap brief; all other and legacy states resume context-free with no network enrichment.
- **D-12 — Distinct zero-selection bypass:** nonempty audit corpus plus zero admitted events is `bypassed/no_selected_context`; zero normalized events alone is `bypassed/no_remote_context`.
- **D-13 — Timestamp/order oracle:** a valid sort timestamp is a nonempty timezone-aware RFC3339/ISO-8601 string accepted by `datetime.fromisoformat(value.replace("Z", "+00:00"))`; normalize only the sort instant to UTC and never rewrite the event field. Admission orders valid instants descending, then endpoint ordinal ascending (`issue_comment=0`, `review=1`, `review_comment=2`), then zero-based source index ascending. Missing, empty, naive, or parse-invalid timestamps follow every valid instant and use endpoint ordinal/source index ascending. Model input orders valid instants ascending with the same ascending tie-breakers, followed by invalid/missing values in endpoint/source order. Equal instants expressed with different offsets are ties. Parser-accepted timezone-aware values remain valid even when direct `astimezone(timezone.utc)` conversion would underflow or overflow at a year boundary; ordering must compare those instants overflow-safely, remain total and instant-correct, and must not reclassify them with missing/naive/parse-invalid values.
- **D-14 — Metadata path/reason oracle:** `design.md::Stable metadata contract` is exact. Disabled precedence is omission `bypassed/disabled_default` then explicit `--no-pr-context` `bypassed/disabled_cli`; with explicit enablement, custom prompt/file precedes unsupported profile, then fetch/normalize → required discussion-audit write → select → orient/finalize → required brief write → delivery in execution order, and the first failing entered enrichment stage wins. Zero remote is classified after its empty audit write; zero selected is classified after successful selection with the nonempty audit already written. Resume delivery classifies all non-`used`/missing/legacy origins as `resume_without_used_context` and only a `used` origin with bad brief as `resume_invalid_context`; D-17/A33/A34 non-delivery/non-review exits do not enter this table. Successful delivery is `used/context_delivered`; delivery fallback reasons are `reconciliation_failed` or `context_synthesis_failed`. The final metadata-mirror failure never replaces the determined outcome/reason; it sets `persistence.meta_artifact=failed` and `persistence.warning=meta_artifact_write_failed`.
- **D-15 — Exact resume owners and persisted producer:** fresh `_pr_flow_impl` writes the finalized nonempty brief to `work/pr_context_orientation.md` before context delivery and records the final nested authority at session `meta.json::pr_context`; both `_resume_flow_impl` and `_run_incremental_completed_multipass_resume` read those exact paths. The shared and incremental synth templates each own exactly one `$PRIOR_CONTEXT` token. A shared validator returns the exact persisted brief or `""` plus D-14 reason; neither route fetches or orients.
- **D-16 — Persistence phase semantics:** `work/pr_context_discussion.json` and a nonempty `work/pr_context_orientation.md` are required pre-delivery artifacts and use atomic replacement; their write failure degrades before context use. Authoritative run state is session `meta.json::pr_context`, flushed at each route transition—including before an empty-context retry and after its final telemetry; a core session flush failure propagates as existing process-control failure. `work/pr_context_meta.json` is a final best-effort mirror written once only after a successful route completion (delivery, successful fallback, or bypass) has final usage and latency. Mirror failure warns, is not retried, preserves the current review artifact and route outcome/context mode/telemetry, records persistence failure in authoritative metadata, and never triggers a second review. If the empty-context retry fails, the review failure propagates, authoritative metadata retains `degraded/context_synthesis_failed` plus available attempt telemetry, and the final mirror is not attempted.
- **D-17 — No-delivery resume metadata scope:** a PR-context invocation begins only when fresh flow evaluates enrichment or a resume route reaches reconciliation/synthesis with a D-15 context decision. `_resume_flow_impl`'s completed/same-head fast no-op and regular reusable-review-artifact branch perform no new review delivery and are outside the D-14 invocation-path table. They must preserve the originating nested `meta.json::pr_context` value deep-equal with no key/value mutation and must not attempt `work/pr_context_meta.json`; ordinary resume lifecycle status/timestamp/footer updates remain allowed.
- **D-18 — Field-level metadata ownership:** `design.md::Field-level fresh/resume metadata oracle` is normative. Fresh `counts.fetched` is the total object count only after all three endpoint arrays return and pass list/object shape validation; `counts.normalized` is the resulting normalized-event count and is independently assigned only after normalization succeeds. Resume dictionaries inherit only canonical acquisition provenance from an origin whose `outcome == "used"`, reset all acquisition fields for every other origin, and always replace delivery/result/mirror fields with current-attempt observations exactly as the design table specifies. Missing, wrong-typed, negative, or non-enum inherited leaves canonicalize field-by-field to the schema default without making an otherwise used-valid brief ineligible.

## Discovery Notes

- `_pr_flow_impl` returns from completed-session `--if-reviewed list|latest|prompt-selected` before sandbox creation and gates review setup/context composition behind `not args.no_review`; these live branches own A33/A34 non-invocation behavior.
- Existing strict GitHub list adapter and endpoint normalizer remain reusable.
- Existing full remote corpus behavior becomes audit evidence, not an unbounded orientation-input requirement.
- Existing local `find_past_reviews`/`sandbox_root`/`past_reviews` behavior is intentionally removed from the MVP rather than hidden behind an empty compatibility shim.
- Existing singlepass already has a blind draft boundary suitable for fallback retention.
- Existing fresh, regular-resume, and incremental-resume multipass plan/step outputs are context-free, so a context-specific synth failure can retry synthesis with empty context without rerunning plan/steps.
- `_resume_flow_impl` has two verified no-delivery exits: the completed/same-head fast no-op through `_mark_resume_noop_completed`, and a reusable-review-artifact branch where `should_synth` remains false. Neither creates a new review artifact or PR-context delivery decision, so D-17 preserves origin evidence instead of inventing a new context classification.
- Existing progress metadata and `work/` artifacts provide the narrow pilot observability surface; no finding-level persistence is needed.
- Historical S1-S16/A1-A18/TAP-01..TAP-13 and R1-R9 remain evidence of prior work only where compatible with D-04..D-10.
- `_pr_flow_impl` now limits `(OSError, UnicodeError)` artifact-write degradation to `_finalize_and_persist_fresh_pr_context`; unrelated construction and raw orientation cleanup/read faults propagate unchanged under D-09 while required orientation writes retain D-16 degradation.
- D-13 now compares parser-accepted aware timestamps by a signed integer microsecond instant key, so minimum/maximum-year offset values remain valid without out-of-range UTC datetime construction.
- Corrected TAP-14/TAP-18/TAP-19 commands collect the paired parser, genuine fresh singlepass/D-18, runtime validator, and current regular-resume owners.
- Remote-only orientation delivery headings now identify selected-PR remote discussion without claiming past CURe reviews, and the removed dead reader leaves `read_persisted_context()` as the sole D-15 validation authority.
- The canonical changed-path Ruff inventory unions tracked merge-base Python changes with untracked non-ignored Python paths, so new package/test owners cannot escape quality proof.

## Implementation Log

- 2026-07-20T12:26:22Z Completed GATE-001/PRC-001/PRC-002 R14 remediation and transitioned implementation to review.
  - RED/GREEN: the focused delivery-prompt provenance test failed against the old singlepass label, then all 6 template tests passed after heading-only repairs; dead `_read_persisted_pr_context_orientation()` was removed and sole-validator scans pass.
  - Canonical proof: the repaired Ruff inventory collected 18 Python paths, including untracked `cure_pr_context/runtime.py` and `tests/cure_pr_context/test_runtime.py`; Ruff passed. Focused template/runtime passed 14, flow passed 67, resume passed 4 plus 2 subtests, combined amended proof passed 579 plus 30 subtests, and full regression passed 784.
  - Final gates: mypy passed 6 source files; merge-base diff hygiene, structural trace, production provenance/sole-validator scan, and disposable `build==1.5.0` wheel/install/import smoke passed. The default interpreter retains the known `build.__main__` environment limitation.

- 2026-07-20T11:31:48Z Completed FB-031–FB-033 R13 remediation and transitioned implementation to review.
  - RED/GREEN: genuine `_pr_flow_impl` build/raw-file `OSError`/`UnicodeError` propagation and D-13 year-boundary overflow failures were reproduced before source edits; scoped catch handling and signed integer instant ordering made them GREEN while required orientation-write degradation remained GREEN.
  - Canonical proof: TAP-14 parser 1, historical/no-review 4, eligibility/no-remote 8; TAP-15 31; TAP-18/TAP-19 runtime/flow 75; resume route 4 plus 2 subtests; TAP-22 19. Combined amended proof passed 578 plus 30 subtests and full regression passed 783.
  - Final gates: Ruff passed all 16 merge-base changed Python paths; scoped mypy passed 6 source files; merge-base diff hygiene passed at `775c8617c9fb6b63c51cd400a974d22e109cf6fb`; disposable `build==1.5.0` wheel/install/import smoke passed after the default interpreter's known repository `build/` namespace prevented the exact frontend from starting.


- 2026-07-18T08:26:57Z Closed the final A29/R12 package and regression gate and transitioned implementation to review.
  - Root cause: the repository's ignored generated `build/` directory is visible as a namespace package when the default interpreter has no PyPA `build` distribution installed; it does not contain or replace a valid `build.__main__`. A disposable virtual environment with PyPA `build==1.5.0` supplied the repository-approved frontend without changing repository dependencies.
  - Proof: the exact `python -m build --wheel` / target install / import smoke passed; stronger imports from `/` resolved `cure_github` and `cure_pr_context` from the disposable installed target. The full suite passed `685`, changed-path Ruff passed, scoped mypy passed, and merge-base diff hygiene passed.
  - Reconciliation: A19-A34 and R10-R12 are final/checked. All tasks and implementation proof pass; status moved `🔄 IN PROGRESS` → `🟣 IN REVIEW`.

- 2026-07-18T07:28:00Z Completed all executable FB-021..FB-024 implementation/proof while retaining the unavailable package gate.
  - Added distinct fresh, regular-resume, and completed-session incremental-resume context-synth fallback success/fatal executor captures and exact partial discussion-write/selection/orientation metadata dictionaries.
  - Proof: 480 amended combined tests plus 11 subtests, 685 full-suite tests, changed-path Ruff, scoped mypy, and merge-base diff hygiene passed.
  - Reconciliation: A19-A28/A30-A34 are final; A29 and the R12 packaging/regression task remain provisional/open because this environment's `python -m build` fails before build startup with no `build.__main__`. Status remains `🔄 IN PROGRESS`.

- 2026-07-16T14:36:49Z Completed approved FB-012..FB-018 and R7-R9 remediation and transitioned to review.
  - RED/GREEN: 14 intended focused failures reproduced FB-014..FB-018 gaps; preserved FB-012 normal/big stale-artifact enforcement and TAP-11/TAP-12 behavior checkpoints were already GREEN. After bounded repairs, 86 package/adapter/focused-flow tests and 4 established real fresh/resume synth captures passed.
  - Adapter proof: TAP-11 captured exact slurp/retry/cached-no-slurp commands plus direct/post-retry auth routing and ineligible propagation. TAP-12 exercised the real public helper with fake two-page Link traversal, ordered accumulation, invalid JSON, and non-array failures. No live CLI/network was used; FB-010 terminal both-attempt exception provenance remains deferred.
  - Final proof: full suite `711 passed`; Ruff passed all 16 merge-base-delta Python paths; mypy passed `cure_github.py cure_pr_context/`; installed wheel imports resolved from the disposable target; structural S1-S14/A1-A16/TAP-01..TAP-12 traceability passed; merge base `775c8617c9fb6b63c51cd400a974d22e109cf6fb` passed `git diff --check "$base" --`.

- 2026-06-20T08:20:00Z Story claimed and implemented in worktree `/home/vscode/add-worktrees/CURe-simple-pr-context-impl`.
  - Added `cure_pr_context` package (`fetcher`, `corpus`, `orient`, public `build_pr_context`) and setuptools package metadata.
  - Added `cure_github.py::gh_api_list`, `_pr_flow_impl` context build phase after `compute_pr_stats`, effective `head_sha=review_head_sha or head_sha`, and prior-context propagation only for the multipass synth/reconcile paths; plan and step entries intentionally exclude prior context.
  - Superseded by the two-pass update: `$PRIOR_CONTEXT` belongs only in the multipass synth template; normal/big singlepass templates exclude it and use the reconcile call when context exists.
  - Verification passed: `python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q` (15 passed), `python -m pytest tests/test_reviewflow_unittest.py -q` (433 passed, 13 subtests), `python -m pytest tests/ -q` (635 passed, 13 subtests), `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py tests/_reviewflow_unittest_grounding_impl.py`, `mypy cure_pr_context`, and wheel/install import smoke.

- 2026-06-20T17:45:00Z Story resumed after implementation review request-changes.
  - Fixed A4 remote footer trust: `parse_footer_metadata()` now requires a valid non-empty `sha` token inside official footer markers before an event can become a past review; added marker-only footer regression coverage.
  - Fixed fail-hard local session handling: corpus scan validates local `meta.json` parseability/object shape before delegating to `scan_completed_sessions_for_pr`, so corrupt session metadata aborts PR context build.
  - Fixed TAP-07 proof maturity: added a runtime `_pr_flow_impl` monkeypatch test proving `compute_pr_stats` -> `build_pr_context` order, effective `review_head_sha` propagation, and prior-context branch behavior; A7 proof row is final.
  - Fixed meta shape: `build_pr_context().meta` now includes `n_comments`, `n_reviews`, and `n_review_comments` alongside aggregate counts; unit/integration tests assert the split.
  - Verification passed: `python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q` (18 passed), `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py`, and `mypy cure_pr_context`.

- 2026-07-17 P0 contract supersession/replanning record.
  - Historical implementation and proof entries above remain unchanged evidence of work performed under the then-current contract; they do not establish completion of FB-021..FB-024.
  - Automatic enablement, unbounded complete-corpus model input, local session/history discovery, and fail-hard enrichment are superseded. No production code or tests were changed by this planning amendment.
  - Current implementation must restart RED-first at R10 and remain `🔄 IN PROGRESS`; S17–S31 cover A19–A28/A31–A34, A29/A30 are direct closure acceptances, and all A19–A34 rows are provisional.

## Plan Review Log

- 2026-07-20T11:01:06Z Historical plan-review log compressed after FB-031–FB-033 feedback absorption.
  - Preserved history: plan feedback through 2026-07-17T17:16:03Z was addressed at 2026-07-17T17:24:28Z; an independent 2026-07-17T17:48:07Z review approved the FB-021–FB-024 contract before later feedback reopened planning.
  - Preserved decisions/evidence: FB-021..FB-024; S30/S31 and A33/A34 non-invocations; D-13 timestamp order; D-14 reason precedence; D-15 producer/consumers; D-16 persistence phases; D-17 no-delivery preservation; D-18 field ownership; TAP-14..TAP-23; FB-010 deferred.
  - Material source anchors: `cure.py::{_pr_flow_impl,_execute_multipass_synth_stage,_mark_resume_noop_completed,_resume_flow_impl,_run_incremental_completed_multipass_resume}`; `cure_pr_context/`; `cure_github.py`; both synth templates; named TAP-14..TAP-23 owners.
  - Debt Friction: none.

- 2026-07-20T10:43:27Z Plan review run by fresh maintainer session
  - Verdict: request_changes
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: unchanged: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `openspec/initiatives/simple-pr-context/initiative.md` Goal/Story Candidates/FB-021..FB-024/Decisions, current story FB-031..FB-033 disposition, `proposal.md`, `design.md`, and `tasks.md`; no issue, PR, or Jira link is recorded
  - Traceability: forward complete; backward gaps
  - Design trace: gaps
  - Code surfaces searched: `cure.py::{build_parser,_pr_flow_impl,_finalize_and_persist_fresh_pr_context,_resume_flow_impl,_run_incremental_completed_multipass_resume}`; `cure_pr_context/{__init__,corpus,orient,runtime}.py`; TAP-14/TAP-18/TAP-19/TAP-22 named owners and collection filters
  - Risk lenses reviewed: external GitHub/subprocess I/O; raw timestamp shape and timezone-boundary ordering; filesystem persistence/generated artifacts; prompt insertion; retry/process lifecycle; nullable telemetry; concurrency, async, migrations, and UI excluded by contract
  - Evidence quality: confirmed current initiative/story/proposal/design/tasks, live catch and timestamp implementations, runtime policy owner, named test owners, focused collection, structural matrices, dirty worktree, and complete-delta hygiene; inferred none; unknown no external issue/PR/Jira intent because none is linked; provisional FB-031..FB-033 proof remains explicitly bounded
  - Finding closure: PLAN-001 requires an unchecked R13 task breakdown and final reconciliation gate in `tasks.md`; PLAN-002 requires the live `cure_pr_context/runtime.py` owner and FB-033 overflow-safe ordering strategy to be reconciled into normative design/Critical Files, followed by structural and owner-collection checks
  - Key findings:
    - **PLAN-001 — HIGH:** `story.md::Implementation Notes` adds current R13 remediation, but `tasks.md` still says R10-R12 are the only current implementation plan and every R10-R12 task/gate is checked. The durable task plan therefore has no red-first, bounded implementation, or final reconciliation work item for FB-031..FB-033.
    - **PLAN-002 — HIGH:** source inspection found `cure_pr_context/runtime.py` owns fresh classification, metadata application, persisted-context validation, resume metadata, and atomic persistence used by `cure.py`, yet `design.md::Package structure` and `story.md::Critical Files` omit that production owner. The same normative design's D-13 algorithm still says to normalize accepted aware timestamps to UTC without stating the newly required overflow-safe comparison strategy. This leaves A19/A21/A24/A26/A31 implementation ownership and the FB-033 edge incompletely traced.
    - FB-031..FB-033 are otherwise represented by provisional A19/A21/A24/A25/A26/A31 rows, R13, corrected TAP-14/TAP-18/TAP-19/TAP-22 proof targets, and explicit regression/side-effect gates.
    - The large dirty worktree is preserved and was treated only as live contract/source context; this review did not assess implementation completeness.
  - Hypothesis triage: `tasks.md` current-plan declaration -> amended work may be skipped or falsely treated complete -> add unchecked R13 task/proof owners; `cure_pr_context/runtime.py` plus `design.md::Deterministic selection` -> hidden owner and ambiguous overflow implementation -> reconcile design/Critical Files before source remediation
  - Debt Friction: none
  - Next action: `/openspec-story-plan-resume simple-pr-context simple-pr-context` to repair `tasks.md`, `design.md`, and `story.md::Critical Files`, then run a fresh plan review

- 2026-07-20T11:01:06Z Plan feedback addressed by `/openspec-story-plan-resume`
  - Original plan review entry: 2026-07-20T10:43:27Z
  - Sections edited: `story.md::Critical Files`, `design.md::Package structure`, `design.md::Deterministic selection`, `tasks.md::Current-contract note`, `tasks.md::FB-031–FB-033 R13 Remediation`, `story.md::Plan Review Log`
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Changes: added unchecked R13 RED/GREEN/final-reconciliation tasks for FB-031–FB-033; added `cure_pr_context/runtime.py` to normative package/critical-file ownership; locked D-13 to a signed integer microsecond instant key that never constructs an out-of-range UTC `datetime` and preserves parser-accepted aware year-boundary values as valid.
  - Preserved boundaries: no acceptance, scope, status, default-off, metadata, persistence, or implementation/source behavior changed; production remediation remains implementation-owned.
  - Debt Friction: none

- 2026-07-20T11:04:17Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED
  - Status transition: unchanged: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `openspec/initiatives/simple-pr-context/initiative.md` Goal/Story Candidates/FB-021..FB-024/Decisions, FB-031..FB-033 disposition and source IDs in current story/notebook trace, `proposal.md`, `design.md`, and `tasks.md`; no issue, PR, or Jira link is recorded
  - Traceability: forward complete; backward complete
  - Design trace: complete
  - Code surfaces searched: `cure.py::{build_parser,_pr_flow_impl,_finalize_and_persist_fresh_pr_context,_mirror_pr_context_metadata,_resume_flow_impl,_run_incremental_completed_multipass_resume}`; `cure_pr_context/{__init__,corpus,orient,runtime}.py`; TAP-14/TAP-18/TAP-19/TAP-22 named owners and collection filters
  - Risk lenses reviewed: external GitHub/subprocess I/O; raw timestamp shape and timezone-boundary ordering; filesystem persistence/generated artifacts; prompt insertion; retry/process lifecycle; nullable telemetry; naming-sensitive D-13 invariants; concurrency, async, migrations, permissions, and UI excluded by contract
  - Evidence quality: confirmed current initiative/story/proposal/design/tasks, direct live runtime/corpus/cure ownership, R13 unchecked task state, D-13 integer-key arithmetic probe, 15-scenario/16-APM/10-TAP structural checks, focused owner collection, complete-delta hygiene, and dirty-worktree preservation; inferred none; unknown no external issue/PR/Jira intent because none is linked; provisional FB-031..FB-033 implementation proof remains explicitly bounded to R13
  - Finding closure: PLAN-001 closed by three unchecked R13 RED/GREEN/final-reconciliation tasks with canonical owner and side-effect gates; PLAN-002 closed by normative `runtime.py` package/Critical Files ownership and an explicit signed integer microsecond D-13 comparison strategy that avoids out-of-range UTC datetime construction
  - Key findings:
    - No blocking planning-contract or proof-design finding remains.
    - FB-031..FB-033 are fully planned without changing acceptance or scope: A19/A21/A24/A25/A26/A31 stay provisional until unchecked R13 implementation and canonical proof complete.
    - The dirty worktree remains implementation context only; this approval does not claim production remediation or implementation completeness.
  - Hypothesis triage: none
  - Debt Friction: none
  - Next action: choose `/openspec-story-converge simple-pr-context simple-pr-context` or `/openspec-story-resume simple-pr-context simple-pr-context`, not both
