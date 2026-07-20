# Simple PR Context — Discussion Orientation

source_of_truth: internal

## Goal / Context

`cure pr` currently reviews a pull request from its description and diff without a bounded summary of that pull request's discussion. This initiative adds an optional, lightweight orientation pass over the selected PR's remote issue comments, reviews, and inline review comments. The complete normalized same-PR remote corpus remains available for audit, while only a deterministic bounded subset is sent to the orientation model and only a bounded brief is injected into supported built-in review flows.

The MVP is an **opt-in pilot**. `--pr-context` enables it and `--no-pr-context` disables it; omission defaults to off. Unsupported or custom prompt/profile flows bypass enrichment before any discussion fetch or orientation call. Enrichment-specific failures warn visibly and fall back to the ordinary context-free review path. Completion of this story does not authorize default-on or general release.

### Pilot goal

Collect comparable context-on/context-off run evidence showing whether orientation reduces duplicate or context-invalid review comments at acceptable token, latency, and degradation cost. No arbitrary quality threshold is locked in by this initiative; default-on/general release requires a separate operator-approved follow-up based on pilot evidence.

### Risks / unknowns

- **Orientation bias or low-quality summaries:** bounded prior context may still anchor the reviewer incorrectly. Mitigation: opt-in operation, context-on/off comparison, and code-evidence-wins reconciliation instructions.
- **Large discussions:** full PR threads can exceed model limits. Mitigation: fixed selection, event-body, orientation-output, and injection caps with deterministic truncation accounting.
- **Provider accounting gaps:** some LLM adapters do not expose usage. Mitigation: always record deterministic estimates and record provider usage only when actually available, as a distinct field.
- **Availability:** GitHub or orientation calls may fail. Mitigation: enrichment errors visibly degrade to the ordinary context-free flow without swallowing unrelated review/process failures.

## Story Candidates

1. **Remote fetch and audit** — fetch and normalize the selected PR's three discussion endpoints; preserve the complete ordered corpus unchanged in `work/pr_context_discussion.json`.
2. **Bounded selection and orientation** — cap the fully assembled orientation-generation prompt, each selected event body, selected event count, orientation output, and injected `$PRIOR_CONTEXT`; select deterministically newest-first within the budget remaining after fixed prompt/framing overhead, then restore chronological model-input order.
3. **Operator and eligibility control** — paired `--pr-context` / `--no-pr-context`, default off; bypass unsupported/custom prompt flows before fetch/orientation.
4. **Fail-open delivery** — use the brief only in supported built-in singlepass reconciliation or multipass synthesis; retain the ordinary blind draft or run context-free synthesis when enrichment-specific processing fails.
5. **Pilot observability** — stable used/bypassed/degraded metadata, reasons, enablement source, counts, estimates/actual usage when available, truncation, and latency, sufficient for context-on/off run comparison without finding identity primitives.
6. **Tests and release gate** — RED-first boundary tests, focused implementation gates, and an operator-reviewed pilot evidence checkpoint before any default-on/general release proposal.

## Feedback-Derived Story Candidates

### FB-010 — Preserve retry failure provenance (deferred)
- A failed no-slurp fallback should surface useful terminal/attempt provenance.
- This remains adapter hardening outside the PR-context MVP.

### FB-011 — Keep corpus discovery read-only (superseded/deferred)
- The earlier local-session discovery candidate is no longer part of the MVP.
- Any future local-history work must define read-only/migration behavior in a separately approved story.

## Feedback-Derived Decisions

### FB-019 — PR endpoints define remote discussion membership
- Every normalized event returned by the selected PR's issue-comment, review, and inline-review-comment endpoints belongs to the full remote audit corpus.
- Footer, session, author, review-state, commit, and body-similarity metadata never include, exclude, reassign, collapse, or prune a remote event.

### FB-020 — Preserve complete remote audit evidence
- The complete normalized same-PR remote corpus remains ordered and unchanged in the audit artifact.
- This does not require every event to enter model input; FB-021 supersedes that former implication.

### FB-021 — Bound context end-to-end
- Fully assembled orientation-generation prompt cap: **12,000 estimated tokens**, including the fixed orientation instructions, canonical framing, normalized PR stats, and compact deterministic JSON for selected normalized event records.
- Per-selected-event body cap: **1,000 estimated tokens**.
- Selected-event cap: **100 events**.
- Orientation output cap: **2,000 estimated tokens**.
- Injected `$PRIOR_CONTEXT` cap: **2,000 estimated tokens**.
- Selection considers newest events first within the budget remaining after fixed prompt/framing overhead, stops at the first prompt-budget or event-count limit, then restores chronological order for model input.
- Report selected, omitted, and body-truncated event counts plus full orientation-prompt/output/injected token estimates. Provider usage, when available, is reported separately and never represented as an estimate.

### FB-022 — Remote same-PR-only MVP
- The MVP uses only discussion from the selected PR's three remote endpoints.
- All local CURe session/history discovery, recovery, filesystem coupling, corruption semantics, and local-history privacy/maintenance surface are deferred.

### FB-023 — Opt-in, fail-open, operator-controlled enrichment
- CLI control is `--pr-context` / `--no-pr-context`, default off.
- Unsupported/custom prompt or profile flows bypass before fetch/orientation.
- Zero normalized endpoint events bypass as `no_remote_context`; a nonempty normalized corpus with zero deterministically selected events preserves its complete audit artifact, bypasses as `no_selected_context`, and never calls orientation.
- Enrichment-specific errors warn visibly and continue through the ordinary context-free review.
- Built-in singlepass retains its ordinary blind draft when reconciliation enrichment fails. Multipass retries synthesis once with empty prior context when its context-specific synthesis fails; failure of that ordinary synthesis remains fatal.
- Resume reuses a persisted brief only when the originating run metadata has `pr_context.outcome == "used"` and the brief is valid and within the 2,000-token injection cap. Missing, bypassed, degraded, legacy/no-outcome, or invalid/over-cap persisted state resumes context-free without network fetch or orientation.
- Fail-open applies only to PR-context enrichment boundaries. Checkout, prompt/profile validity, ordinary draft/plan/step/synth execution, output acceptance/posting, cancellation, and other process-control failures retain their existing behavior.

### FB-024 — Minimal pilot observability and release gate
- Stable run metadata records outcome `used|bypassed|degraded`, reason, enablement source, selected/omitted/truncated counts, estimates, provider usage when available, truncation, and latency.
- Records support context-on/context-off comparison for otherwise comparable runs without adding finding identity or disposition primitives.
- Story completion authorizes only an opt-in pilot. Default-on/general release requires a separate operator-approved follow-up based on collected evidence.

## Decisions & Constraints

**Locked-in:**
- Same-PR remote discussion only; no local CURe history discovery in this MVP.
- Complete remote audit corpus is distinct from bounded model input.
- Deterministic token estimate for caps is `ceil(len(text) / 4)` over Unicode code points; estimates remain explicitly labeled.
- Stable ordering uses normalized `created_at`, then endpoint order and source index as deterministic tie-breakers.
- The five existing orientation sections and code-evidence-wins guidance remain.
- No cache/freshness contract in this iteration.
- Opt-in pilot only; default off.

**Explicitly NOT part of this initiative:**
- Finding identity/disposition model, semantic arbitration, or authoritative resolution state
- Local session/history discovery or recovery
- Freshness digests, caching, or persistent review memory
- Richer reconciliation analytics
- A default-on/general release decision
- Arbitrary pilot quality thresholds

## External Resources

- Old initiative branch (historical reference only): `cure-subsequent-pr-review/story-01-intake`
