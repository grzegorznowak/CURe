# Design: story-02-auto-infer-subsequent-review-mode

## Architecture Overview
See `story.md` for the canonical story contract. Critical files/surfaces for this change:

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

## Technical Decisions
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

## Implementation Strategy
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

## Risks & Mitigations
- Source recon found `build_parser` currently defines a mutually exclusive `--subsequent-review` / `--no-subsequent-review` group with `dest="subsequent_review"` and default `False` in `projects/CURe/cure.py:15455-15485`.
- `_subsequent_review_enabled(args)` currently returns a bool from `args.subsequent_review` and defaults false in `projects/CURe/cure.py:7471-7479`.
- `_pr_flow_impl` currently invokes `run_subsequent_review_intake` only under the boolean opt-in and records `subsequent_review` meta only when an intake result exists in `projects/CURe/cure.py:9544-9606`.
- Story 01 control-plane disabled mode deliberately returns `None` and creates no `work/subsequent` directory in `projects/CURe/cure_subsequent_review/control_plane.py:93-119`; Story 02 should write decision metadata outside disabled intake.
- Existing tests in `projects/CURe/tests/test_subsequent_review.py` cover Story 01 artifacts, historical list exits, and enabled new-run intake but currently use `--subsequent-review`; they are natural red-first update points for default auto.
- FB-002 replan source recon: current `decide_subsequent_review` counts `remote_cure_markers` with `_looks_cure_authored(...)` and enables on `cure_pr_discussion_found` in `projects/CURe/cure_subsequent_review/decision.py:135-151`; historical `_looks_cure_authored` body/login behavior left CURe-looking human text and missing thread-state metadata unproven.
- FB-002 replan source recon: `collect_pr_discussion` treats missing/unknown thread-state shapes as `thread_state_unavailable` in `projects/CURe/cure_subsequent_review/github_history.py:38-47` and appends that reason for review comments in `projects/CURe/cure_subsequent_review/github_history.py:103-106`; Story 02 proof must ensure metadata absence is not a positive prior-review marker and remains a non-enabling degraded reason unless paired with broader remote probe unavailability.
- FB-003 replan source recon: `_pr_flow_impl` writes `meta.json.status = running` through `SessionProgress.init` in `projects/CURe/cure.py:9530-9589` / `:2839-2855`, then calls `decide_subsequent_review`, `write_decision_artifact`, and enabled `run_subsequent_review_intake` at `projects/CURe/cure.py:9602-9628`; the broad `progress.error(...)` handler is later at `projects/CURe/cure.py:10615-10624`, so failure-injection proof must cover the post-init preflight block explicitly.
- FB-026 source recon: `cure_output.py:1547-1549` writes the official review footer markers; current `decision.py:82-85` only counts issue comments and pull review bodies through `_looks_cure_authored`; current `prior_corpus.py:28-41` requires an allowlisted CURe author plus CURe-looking body and `prior_corpus.py:107-123` uses the same predicate for issue-comment / pull-review corpus admission. The amended plan makes the official footer block the shared positive marker regardless of author while preserving review-comment exclusion and body-only spoof rejection.
