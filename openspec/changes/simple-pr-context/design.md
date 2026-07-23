# Design: simple-pr-context

## Package structure

```text
cure_github.py      # GitHub CLI plus D-19 bounded paginated-list public fallback; strict transactional list boundary
cure_llm.py         # Codex provider-state, event/display-log resolution, and orientation-local progress routing
cure_output.py      # Codex JSON event sink and explicit display-log file routing

cure_pr_context/
  __init__.py   # build_pr_context(...) orchestration and result/meta assembly
  fetcher.py    # selected-PR three-endpoint fetch + normalization
  corpus.py     # deterministic bounded remote-event selection (no local discovery)
  orient.py     # bounded orientation prompt/finalization and five-section brief
  runtime.py    # fresh classification, metadata application/resume authority, and atomic persistence
```

`cure_pr_context` and `cure_github` remain explicitly registered in `pyproject.toml`.

## Eligibility and operator control

`cure.py` decides eligibility before binding/calling the discussion fetcher:

1. Parse the paired Boolean option `--pr-context` / `--no-pr-context`; omission means disabled.
2. Record `enablement_source` as `cli_explicit` when either spelling is supplied, otherwise `default`.
3. Eligible MVP flows are fresh built-in normal/big singlepass and built-in multipass reviews. Custom `--prompt`, `--prompt-file`, or unsupported/profile-specific flows bypass before fetch/orientation.
4. Completed-session `--if-reviewed list`, `latest`, and interactive `prompt` selections are historical-output operations, not new review invocations. They return before sandbox/session creation even when `--pr-context` is supplied; they make no discussion/orientation call, create no PR-context artifact or metadata, and do not mutate the selected historical session. `--if-reviewed new` continues into ordinary eligibility.
5. `--no-review` is also outside the PR-context invocation boundary even when paired with `--pr-context`. Its existing session/index-only route creates no `meta.json::pr_context` and no `work/pr_context_*` artifact and makes no fetch, selection, orientation, reconciliation, or synthesis call.
6. Both regular `_resume_flow_impl` synthesis and completed-session incremental `_run_incremental_completed_multipass_resume` synthesis read originating session `meta.json::pr_context` plus `work/pr_context_orientation.md`. They reuse the exact brief only if `outcome == "used"` and the brief is readable UTF-8, nonempty, structurally finalized with canonical instructions/five headings/fence validity, and within the 2,000-estimated-token injection cap. Missing/non-object metadata, `bypassed`, `degraded`, legacy metadata with no outcome, any other outcome, or a missing/directory/non-UTF-8/empty/invalid/over-cap brief supplies `""`. Neither resume route fetches discussion, discovers local sessions, or calls orientation.
7. A resume route that does not reach synthesis/reconciliation creates no PR-context delivery decision. The completed/same-head fast no-op and regular reusable-review-artifact branch preserve the originating nested `meta.json::pr_context` value deep-equal with no key/value mutation and make no new `work/pr_context_meta.json` mirror attempt; ordinary lifecycle timestamps/status/footer may still change.
8. Bypasses that enter the PR-context decision boundary record stable metadata and invoke no GitHub discussion or orientation boundary. The historical-selection and `--no-review` routes above never enter that boundary, so they intentionally produce no bypass dictionary.

The feature defaults off. Enabling this story authorizes only an opt-in pilot.

## Provider-state and CURe-log isolation

`cure_llm.run_codex_exec()` passes its supplied environment to both the primary and trusted-directory retry, while Codex stores rollouts beneath the effective `CODEX_HOME`. It also resolves raw/display event logs from the supplied progress object and sends Codex JSON stdout through `cure_output.CodexJsonEventSink`; that sink writes raw JSON to `codex.events.jsonl`, completed agent-message text to `codex.log`, and compact event text into `progress.meta.live_progress`. `_iter_codex_session_logs()` and `find_codex_resume_info()` demonstrate the durable provider `sessions/` shape. Fresh PR-context orientation therefore owns one explicit source-fit runtime boundary rather than relying on the three coordinator artifacts or provider state alone:

1. Derive the configured Codex source home from the orientation environment before override, then create a fresh invocation-scoped orientation runtime root under coordinator-owned session state. Its contained paths are `codex-home/`, `logs/codex.events.jsonl`, `logs/codex.log`, and `meta.json` for orientation-only progress.
2. Stage only regular-file `auth.json` and `config.toml` into `codex-home/` when present; reject non-regular inputs and never copy `sessions/` or other history. Set orientation-only `CODEX_HOME` to `codex-home/` for the full provider call.
3. Create a dedicated `SessionProgress` at the runtime root's `meta.json`, initialize its `logs.codex_events` and `logs.codex` paths to the runtime root, and call `run_llm_exec(..., progress=orientation_progress)`. `run_codex_exec()` continues to resolve both log paths from its supplied progress object on primary and trusted-directory attempts. `ReviewflowOutput.run_logged_cmd(..., codex_display_log_path=...)` must use the resolved orientation display path rather than its ordinary open `work/logs/codex.log`; `CodexJsonEventSink` remains the raw/display serializer. Both `run_codex_exec()` return paths pass `codex-home/` explicitly as `codex_root` to `find_codex_resume_info()`.
4. The session's ordinary `SessionProgress` is not passed to Codex orientation. Consequently its `meta.json::{last_cmd,live_progress}` and its registered `work/logs/codex.events.jsonl` / `work/logs/codex.log` receive no orientation prompt, response, event, display, or isolated-path record. Later review agents continue through `prepare_review_agent_runtime()` with independently resolved provider state plus session/work access, so this non-mutation is part of the capability boundary rather than log hygiene.
5. After provider output and usage have been ingested into coordinator memory, remove the entire orientation runtime root on success and failure. Before every fresh blind/context-free launch, the same launch gate verifies that root and the three PR-context artifact paths are absent. Failure to remove or prove absence propagates and launches no agent.
6. Deterministic proof drives normal Codex JSON stdout through the real sink with a unique orientation sentinel and writes the same prompt beneath `codex-home/sessions/.../rollout-*.jsonl`. It must observe the sentinel only inside the runtime root while that root exists, then prove the root absent and scan every later agent-reachable session/work log or metadata path plus seeded configured/default Codex homes to prove the sentinel absent before each permissive launch. HTTP orientation creates no local provider/CURe transcript root; remote provider retention is outside this local process/filesystem capability contract.

## Data flow

```text
paired CLI option + route classification
        │
        ├── historical list/latest/prompt-selected ──> return existing output; no session/context state
        ├── --no-review ──> existing session/index-only route; no context state
        │
        ▼
built-in-flow eligibility
        │
        ├── disabled/custom/unsupported ──> bypass metadata ──> ordinary review
        │
        ▼
selected PR's 3 GitHub endpoints
        │
        ▼
fetch_pr_discussion() ──> complete normalized remote corpus held in coordinator memory
        ├── zero normalized ──> write empty audit (non-context-bearing) ──> bypass:no_remote_context ──> ordinary review
        ▼
select_orientation_events()
        │
        ├── newest-first consideration under 100-event limit
        ├── per-selected-body cap 1k estimated tokens
        ├── chronological restoration + canonical compact JSON
        ├── admission under the remaining 12k full-prompt budget
        ├── nonempty/zero selected ──> ordinary review with every nonempty PR-context artifact absent
        │                                └── after all review agent calls: persist complete audit; bypass:no_selected_context
        └── selection counts/estimates/truncation
        │
        ▼
build_orientation_brief()
        │
        ├── output capped at 2k estimated tokens
        └── five finalized sections + usage instructions
        │
        ▼
independent injection cap at 2k estimated tokens
        │
        ├── built-in singlepass: all nonempty context artifacts absent -> blind draft
        │      -> atomically persist complete discussion + canonical brief immediately before reconcile
        │      reconcile failure => warn, retain blind draft
        └── built-in multipass: complete discussion + finalized brief held only in coordinator memory
               raw orientation output removed; discussion and canonical orientation artifacts absent
               Codex orientation uses a fresh invocation-scoped runtime root containing an isolated
                  CODEX_HOME, CURe event/display logs, and orientation-only progress metadata;
                  after provider exit the entire root is removed and absence-proved, while shared
                  session logs/meta remain orientation-sentinel-free
               context-free plan/steps run only while all three nonempty PR-context paths and
                  the orientation runtime root remain nonexistent
               plan parse failure => singlepass fallback whose blind draft retains the same absence boundary,
                  then publish discussion + brief only immediately before permitted reconciliation
               successful plan abort => write the abort review, then publish the complete audit after the plan agent,
                  finalize authoritative bypass metadata/mirror, and return without publishing the brief
               after all ordinary plan/steps: publish complete discussion + canonical brief via per-file atomic replacement immediately before context synth
               pre-context persistence failure => remove any partial publication before one context-free synth
               inability to prove absence => propagate without launching a context-free agent
               context-bearing provider-call failure => warn, retry synth once with ""
               ordinary post-provider validation failure => propagate; no empty retry

post-build selection/orientation degradation
        └── remove raw/partial artifacts -> ordinary review with every nonempty PR-context artifact absent
              └── after all review agent calls: persist complete audit when available; retain first degradation reason

origin session meta.json::pr_context + work/pr_context_orientation.md
        │
        ├── regular `_resume_flow_impl` shared synth
        └── completed-session incremental `_run_incremental_completed_multipass_resume`
               used + valid/in-cap => exact opaque brief; otherwise ""; never fetch/orient
               delivery entry => sanitized current resume record becomes authoritative
               nonempty-context provider-call failure => one empty retry from unchanged plan/steps
               ordinary post-provider validation => current telemetry + delivery_validation_failed; propagate; no retry/mirror

resume with no new delivery
        ├── completed/same-head fast no-op
        └── regular reusable review artifact (`should_synth == false`)
               preserve origin pr_context without key/value mutation; no new metadata mirror
```

No stage scans local CURe sessions or reads historical local review artifacts. Fresh blind/context-free stages receive neither discussion/orientation content nor artifact paths in prompts. Their filesystem blindness does not depend on constraining the supported permissive provider runtime: complete nonempty discussion and finalized orientation stay only in coordinator memory; `work/pr_context_orientation.raw.md` is removed after ingestion; and `work/pr_context_discussion.json`, the raw orientation path, and `work/pr_context_orientation.md` are absent before and throughout the singlepass blind draft, multipass plan/steps, `no_selected_context`, and every post-build degraded context-free agent call. Codex orientation additionally runs inside one fresh invocation-scoped runtime root under coordinator-owned session state. The root contains its isolated `CODEX_HOME`, raw/display Codex logs, and dedicated progress metadata; only required regular-file auth/config inputs are staged, no `sessions/` or other history is copied, and the same local progress/log/provider root is used for any internal trusted-directory retry. The ordinary session progress and shared `work/logs/codex.events.jsonl` / `work/logs/codex.log` are not orientation sinks. After provider output and usage are ingested, the coordinator removes the entire runtime root and proves it absent before every later blind/context-free launch. Cleanup or absence-verification failure is process-control failure and propagates without launching an agent, even when the orientation call itself failed. Review-agent runtime preparation continues to use its ordinary independently resolved provider state and session/work add-dirs; it never receives the deleted orientation root, and those reachable paths contain no orientation sentinel. HTTP providers create no local orientation transcript root, and the real-boundary proof asserts they do not materialize a locally reachable rollout through this path. The coordinator publishes complete discussion plus canonical orientation using atomic replacement for each file only immediately before the first permitted context-bearing reconciliation/synthesis call. If either required publication fails, any partially published nonempty PR-context artifact is removed before a context-free fallback; cleanup/absence-establishment failure propagates without launching an agent. A branch with no context-bearing call publishes its complete audit only after all review agent calls finish. This includes a successful multipass `plan.abort`: its plan process runs with all three paths absent, then `_pr_flow_impl` writes the abort review, publishes only the complete audit, finalizes authoritative `bypassed/plan_aborted` metadata and its one best-effort mirror, and returns without publishing a reusable orientation brief. A multipass plan-parse failure retains all-path absence through both the failed plan parse and the fallback singlepass blind draft, then follows the ordinary singlepass publication-before-reconciliation boundary. The empty audit array on `no_remote_context` is non-context-bearing and may still be written before ordinary review.

### Bounded paginated-list public GitHub fallback (D-19)

D-19 applies only to the unauthenticated paginated discussion-list fallback owned by `cure_github._github_public_api_list` and reached through `gh_api_list(..., allow_public_fallback=True)` for the three discussion endpoints. It is considered only for `github.com` after the existing authenticated list-route eligibility decision. The separate `_github_public_api_json` / `gh_api_json` PR-metadata fallback is unchanged and outside D-19. The in-scope list fallback is behaviorally bounded:

- every `_github_public_api_list` page request uses timeout `30.0` seconds;
- use a transport opener whose redirect handler rejects every HTTP redirect response before any follow-up request; redirects are failures rather than pagination and consume no additional page/request budget;
- resolve each `next` against the current page, then reject it before request unless the effective URL is exactly HTTPS `api.github.com` port 443 with no userinfo or fragment;
- reject malformed, non-HTTP(S), and cross-origin targets before request;
- canonicalize and track every requested URL, rejecting both direct and multihop repeats before request;
- request at most 100 pages: a terminal page 100 is success, while a `next` on page 100 fails before any page-101 request;
- decode each page strictly as a JSON array, retaining page order, but expose accumulated items only after the entire chain completes.

Any timeout, redirect, unsafe `next`, cycle, malformed URL, page-budget, HTTP, network, JSON, or non-array failure raises through the discussion fetch boundary. Partial pages are discarded; fresh flow warns, records `degraded/fetch_failed`, writes no discussion or orientation artifact, and reviews context-free. Deterministic fake transports own this proof; live-network tests remain out of scope.

## Audit corpus versus model input

The full normalized remote corpus and the bounded selected corpus are different contracts:

- `discussion` is every event returned by the selected PR's issue-comment, review, and inline-review-comment endpoints, normalized and retained in endpoint order. Body, footer, session, commit, author, and review-state content remains unchanged. It is returned to the coordinator for phase-correct atomic persistence to `work/pr_context_discussion.json`; `build_pr_context()` itself performs no artifact write.
- `selected_discussion` is a deterministic subset used in the orientation prompt. Its event bodies may be prefix-truncated to the per-event body cap. It is returned separately and never replaces or mutates `discussion`; selection details are recorded in stable metadata rather than replacing the full audit artifact.
- The audit artifact is written from `discussion`, never reconstructed from selected input.

## Deterministic estimated-token rule

All policy caps use this provider-independent estimate:

```python
estimated_tokens(text) = ceil(len(text) / 4)
```

`len(text)` is the Python Unicode code-point length after normalization. A zero-length string estimates to zero. Implementations may compute provider usage too, but provider usage is stored in separate nullable fields and never substituted for or labeled as the deterministic estimate.

For exact cap enforcement, a text cap of `N` estimated tokens retains at most the first `4 * N` code points. Truncation is represented in metadata rather than by appending an unbudgeted marker.

## Deterministic selection

`select_orientation_events(events, *, pr_stats, orientation_instructions)` applies these constants:

```text
ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS = 12_000
EVENT_BODY_MAX_ESTIMATED_TOKENS = 1_000
SELECTED_EVENT_MAX = 100
ORIENTATION_OUTPUT_MAX_ESTIMATED_TOKENS = 2_000
INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS = 2_000
```

The orientation-generation input has one canonical serialization/framing contract. `canonical_json(value)` is `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`: object keys are recursively sorted, arrays retain their specified order, and no incidental whitespace is emitted. `normalized_pr_stats` is the existing JSON-safe PR-stats mapping (or `{}` when absent), without selector-added fields. Each serialized selected record is the complete normalized endpoint event copy after only its `body` is prefix-capped; endpoint ordinal/source index are selector-only tie-breakers and are not injected as JSON fields. `ORIENTATION_INSTRUCTIONS` is the exact program-owned fixed scanner instruction constant (including the five requested sections, bounded `Resolved areas` semantics, and code-evidence-wins guidance), stored without a trailing newline. The exact prompt, with no newline after the final separator, is:

```python
ORIENTATION_INSTRUCTIONS
+ "\n--- PR_STATS_JSON ---\n"
+ canonical_json(normalized_pr_stats)
+ "\n--- SELECTED_EVENTS_JSON ---\n"
+ canonical_json(selected_events_in_chronological_order)
+ "\n--- END_ORIENTATION_INPUT ---"
```

The 12,000-token cap applies to `estimated_tokens()` over that fully assembled string: fixed instructions, all literal separators, normalized PR stats, JSON brackets/commas/keys, and selected event values are all charged. The empty-array assembly defines fixed prompt/framing overhead. Implementations must evaluate exact tentative full-prompt assembly rather than sum independently rounded estimates; this makes cap-1/cap/cap+1 fixtures unambiguous. A change to instructions, framing, normalized fields, or PR stats changes the remaining event budget rather than escaping the cap.

Algorithm:

1. Preserve the immutable endpoint-order audit list. Canonicalize normalized PR stats and verify that the exact empty-array prompt fits 12,000 estimated tokens; inability to assemble/fit fixed overhead is a selection-stage degradation, not a no-data bypass.
2. Assign endpoint ordinals in fetch order (`issue_comment=0`, `review=1`, `review_comment=2`) and a zero-based source index within each endpoint. A valid `created_at` sort value is a nonempty timezone-aware RFC3339/ISO-8601 string accepted by `datetime.fromisoformat(value.replace("Z", "+00:00"))`. For comparison, derive a signed integer instant key without constructing a UTC `datetime`: `((parsed.toordinal() * 86400 + parsed.hour * 3600 + parsed.minute * 60 + parsed.second) * 1_000_000 + parsed.microsecond) - offset_microseconds`, where `offset_microseconds` is the exact signed `parsed.utcoffset()` in microseconds. Integer arithmetic may produce a key outside Python's representable `datetime` year range and therefore remains defined for parser-accepted aware minimum/maximum-year offset values. Do not call `astimezone(timezone.utc)` or a platform timestamp conversion for this key, and do not rewrite the event's raw timestamp field. Naive, empty, missing, and parse-invalid values are invalid; parser-accepted aware values are not reclassified invalid because their equivalent UTC wall-clock representation would underflow or overflow.
3. Admission's total order is: valid integer instant keys descending; ties (including offset-different strings denoting the same instant) use endpoint ordinal ascending then source index ascending. Invalid/missing timestamps follow every valid timestamp and use endpoint ordinal/source index ascending.
4. For each candidate, create a model-input copy and prefix-cap only its body to 1,000 estimated tokens; retain every other normalized field unchanged in that copy.
5. Tentatively append the candidate, restore the tentative set to model-input order, canonically assemble the complete prompt above, and admit the candidate only if the complete estimate is at most 12,000. Stop at the first candidate that would exceed the full-prompt cap or when 100 events have been selected; do not skip an event to pack later events.
6. Model-input order is valid integer instant keys ascending, with endpoint ordinal/source index ascending for ties, followed by invalid/missing timestamps in endpoint/source order.
7. Record:
   - total normalized events;
   - selected events;
   - omitted events (`total - selected`);
   - selected events whose bodies were truncated;
   - serialized selected-events estimate (informational only);
   - exact fully assembled orientation-prompt estimate;
   - whether count, prompt budget, or body truncation applied.

## Orientation finalization and injection

`build_orientation_brief()` receives only `selected_discussion` plus PR stats. Fresh finalization and persisted validation use the same structural Markdown scanner. A construct is structural only with 0–3 leading spaces; 4 or more leading spaces are indented-code/nonstructural. Required headings must be real H2 headings outside fences. A fence opener uses a run of at least three backticks or tildes, and closes only with the same marker and a run at least as long as the opener (also at structural indentation); wrong-marker and shorter runs remain content. It retains the existing five sections:

- `## Resolved areas`
- `## Problem areas`
- `## Pending issues`
- `## Repeated patterns`
- `## Decisions made`

`Resolved areas` is text-derived guidance, not authoritative resolution state. Existing fence-aware finalization and program-owned usage instructions remain. Cap-aware finalization first reserves space for the canonical usage instructions and all five required headings, then allocates the remaining 2,000-estimated-token output budget to scanner content in section order. Scanner content is prefix-truncated as needed; if retained content opens a fence, the finalizer reserves/frees enough space to close it. Thus every non-empty orientation brief remains structurally complete and within the cap. Metadata records output truncation and the final estimate.

Before fresh delivery, `cure.py` independently enforces the 2,000 estimated-token injected-context cap. This is a separate defense even though the orientation-output cap has the same default. `$PRIOR_CONTEXT` remains opaque during insertion.

Resume does not repair, truncate, or refinalize persisted context into eligibility. A shared validator reads session `meta.json::pr_context` before `work/pr_context_orientation.md` and returns the exact brief only for `outcome == "used"` plus the shared 0–3-space/H2/matching-marker-and-adequate-close structural grammar and at-most-2,000-token validation above. It otherwise returns `""` with `bypassed/resume_without_used_context` for missing/non-object/non-used/legacy metadata or `bypassed/resume_invalid_context` for a used origin with missing/directory/non-UTF-8/empty/invalid/over-cap brief. `_resume_flow_impl` passes that result through the shared synth's exact-one owned token; `_run_incremental_completed_multipass_resume` passes it through a newly exact-one owned token in `mrereview_gh_local_big_resume_synth.md`. Both routes perform no network enrichment. Once either route enters delivery, the field-by-field sanitized current resume record becomes authoritative rather than the raw origin record. If its context-bearing provider call fails while this validator supplied non-empty context, it records `degraded/context_synthesis_failed`, rerenders exactly once with `""`, and reuses the same successful plan/step outputs. Successful fallback records `context_mode=off`, combined delivery latency, and separate nullable delivery/fallback provider-usage fields; fallback failure propagates while authoritative metadata retains the degradation reason and available telemetry. An ordinary output-validation failure after provider return is not fallback eligible: retain current delivery usage/latency, record `degraded/delivery_validation_failed`, propagate the original failure, and make neither an empty retry nor a final metadata-mirror attempt.

No-data outcomes are stable and distinct:

- Three endpoint results that normalize to zero events produce `bypassed/no_remote_context`, write the complete empty audit artifact when writable, make no orientation call, and continue context-free.
- A nonempty normalized remote corpus for which deterministic bounded selection admits zero events produces `bypassed/no_selected_context`, preserves the complete audit in coordinator memory, makes no orientation call, continues context-free with every nonempty PR-context path absent, and writes the unchanged audit only after all review agent calls.

## Public result contract

The target public orchestration API is remote-only:

```python
def build_pr_context(
    *,
    pr: object,
    pr_stats: dict[str, Any] | None,
    gh_fetch: Callable[[str], list[dict[str, Any]]],
    run_llm: Callable[[str], str],
    usage_observer: Callable[[], Mapping[str, int] | None] | None = None,
) -> dict[str, Any]:
    ...
```

It has no `sandbox_root`, local-session, `past_reviews`, or local `head_sha` dependency. It returns exactly:

```text
orientation_brief   bounded finalized string, or "" for either no-data bypass
discussion          complete unchanged normalized remote audit corpus
selected_discussion bounded model-input copies in chronological order
meta                 stable selection/orientation observability
```

The optional `usage_observer` is queried immediately after the orientation invocation only when the active LLM adapter exposes provider usage. Missing observers, `None`, or absent provider fields produce nullable usage metadata; deterministic estimates remain mandatory. The observer is telemetry-only and cannot affect selection or caps.

The previous `find_past_reviews` export and local/cross-source corpus contract are removed rather than compatibility-shimmed. `corpus.py` becomes the bounded remote selector. No local-history fallback is attempted.

## Persistence and delivery phase semantics

Fixed producers and consumers are:

| Artifact / state | Producer | Timing / authority | Consumer |
|---|---|---|---|
| `work/pr_context_discussion.json` | fresh `_pr_flow_impl` from complete `discussion` held in coordinator memory | empty audit may be written before ordinary review; nonempty audit is absent through blind/context-free agent calls, published atomically with the brief immediately before a permitted context-bearing call, or published only after all review agent calls on a branch with no context-bearing call | audit/reviewer only |
| `work/pr_context_orientation.md` | fresh `_pr_flow_impl` from finalized nonempty brief held in coordinator memory | absent with the nonempty discussion artifact through the blind draft/plan/steps and fresh context-free branches; atomically published immediately before singlepass reconciliation or post-step multipass context synth; removed with any partial publication before a fresh empty-context fallback | both resume routes through the shared validator |
| invocation-scoped orientation runtime root (`codex-home/`, `logs/codex.events.jsonl`, `logs/codex.log`, orientation-only `meta.json`) | `_run_pr_context_orientation` plus `run_codex_exec` / `ReviewflowOutput.run_logged_cmd` / `CodexJsonEventSink` | Codex-only, isolated from session-global progress/log paths; contains provider rollout, raw/display events, and live-progress state only during orientation; removed after output/usage ingestion and absence-proved before every blind/context-free launch | orientation coordinator only; never later review agents |
| session `meta.json::pr_context` | `_pr_flow_impl` / resume flow through `SessionProgress` | authoritative; flushed at each route transition and after final telemetry/persistence status | pilot comparison and resume outcome authority |
| `work/pr_context_meta.json` | fresh/resume flow from final `meta.json::pr_context` payload | one best-effort atomic mirror attempt after successful route completion (delivery, successful fallback, or bypass) has final usage and latency; no attempt on no-delivery resume or failed ordinary fallback | audit/reviewer only |

`build_pr_context()` returns discussion/orientation values without persisting them. Before every fresh blind/context-free agent call, `_pr_flow_impl` establishes absence of all three nonempty PR-context paths—discussion, raw orientation, and canonical orientation—and of any invocation-scoped orientation runtime root. For Codex, `_run_pr_context_orientation` supplies a fresh isolated `CODEX_HOME` plus dedicated CURe event/display logs and `SessionProgress` beneath that runtime root, seeds only required regular-file auth/config inputs from the effective configured Codex home, excludes `sessions/`, ingests the provider result and usage, then removes the entire root. `run_codex_exec` routes its resolved display path through `ReviewflowOutput.run_logged_cmd` on both provider attempts, so `CodexJsonEventSink` never writes orientation content to the ordinary session log; orientation live progress likewise stays in the dedicated metadata file. The launch gate re-verifies root nonexistence and shared session log/meta non-contamination on every blind/context-free branch; cleanup failure is not enrichment degradation because no safe context-free launch can follow. This includes the multipass plan process, a plan-parse fallback's subsequent singlepass blind draft, and the plan process on a successful `plan.abort` route. A required pre-context discussion/brief publication failure warns and records `degraded/artifact_write_failed`; before any fresh context-free fallback, `_pr_flow_impl` removes every partial/nonempty publication and rechecks absence. Failure to establish absence is a process-control failure that propagates without launching another agent. Singlepass therefore retains its already completed blind draft without reconciliation. Fresh multipass uses the same successful plan/step outputs for one context-free synth only after absence is established. A nonempty `no_selected_context` or post-build degraded branch first runs ordinary review with the paths absent, then atomically persists the complete audit after all review agent calls. Failure of that post-agent audit write does not rerun review: it becomes `degraded/artifact_write_failed` when no earlier degradation exists, otherwise the first degradation reason remains authoritative while `persistence.discussion_artifact=failed`. Before a fresh empty-context synth retry after a context-bearing provider-call failure, the same removal/absence gate applies; after agent calls finish, available audit artifacts may be restored from coordinator memory, but a degraded run's orientation is not made reusable. Before an empty-context synth retry, authoritative session metadata is flushed as `degraded/context_synthesis_failed`; after a successful retry it is flushed again with `context_mode=off`, combined delivery latency, and separate nullable delivery/fallback provider-usage fields. If the retry fails, ordinary review failure propagates, available degradation telemetry remains authoritative, and no final mirror is attempted. A final metadata-mirror failure occurs after a successful route outcome is known: it warns once, is not retried, does not rerun review, preserves the already produced review artifact and the route's outcome/reason/context mode/usage/latency, and records `persistence.meta_artifact="failed"` plus `persistence.warning="meta_artifact_write_failed"` in authoritative session metadata. A core session `meta.json` flush failure is existing session/process-control failure and propagates; it is not swallowed as PR-context degradation.

The completed/same-head fast no-op and regular reusable-review-artifact branch do not run reconciliation or synthesis, so they are not new PR-context invocations. Their writes may update ordinary resume lifecycle fields, but the nested originating `meta.json::pr_context` value remains deep-equal with no key/value mutation and `work/pr_context_meta.json` is not attempted. This preserves the authority used by a future real delivery instead of relabeling an old review artifact as a new context-on/off result.

The completed-session `--if-reviewed list|latest|prompt-selected` exits occur earlier still, before a new sandbox/session exists, and therefore cannot emit a run dictionary or artifact. `--no-review` does create its ordinary session but never creates a review delivery decision; it omits the `pr_context` key and every `work/pr_context_*` artifact. These are non-invocations rather than new bypass reasons.

## Stable metadata contract

Every fresh or resume route that enters a PR-context enrichment/delivery decision, including bypasses and degradations created by `cure.py`, records the same top-level keys. D-17 no-delivery resume exits are deliberately outside this invocation set and preserve their originating value deep-equal with no key/value mutation:

```json
{
  "outcome": "used|bypassed|degraded",
  "reason": "stable_reason",
  "enabled": false,
  "enablement_source": "default|cli_explicit",
  "eligible": false,
  "counts": {
    "fetched": 0,
    "normalized": 0,
    "selected": 0,
    "omitted": 0,
    "truncated_events": 0
  },
  "estimated_tokens": {
    "selected_events": 0,
    "orientation_prompt": 0,
    "orientation_output": 0,
    "injected": 0
  },
  "provider_usage": {
    "orientation_input_tokens": null,
    "orientation_output_tokens": null,
    "delivery_input_tokens": null,
    "delivery_output_tokens": null,
    "fallback_input_tokens": null,
    "fallback_output_tokens": null
  },
  "truncation": {
    "event_body": false,
    "event_count": false,
    "prompt_budget": false,
    "orientation_output": false,
    "injected_context": false
  },
  "latency_ms": {
    "fetch": 0,
    "selection": 0,
    "orientation": 0,
    "delivery": 0,
    "total_enrichment": 0
  },
  "persistence": {
    "discussion_artifact": "not_attempted|written|failed",
    "orientation_artifact": "not_attempted|written|failed",
    "meta_artifact": "not_attempted|written|failed",
    "warning": null
  },
  "context_mode": "on|off"
}
```

Stable reasons are exact:

- bypassed: `disabled_default`, `disabled_cli`, `custom_prompt`, `unsupported_profile`, `no_remote_context`, `no_selected_context`, `plan_aborted`, `resume_without_used_context`, `resume_invalid_context`;
- degraded: `fetch_failed`, `selection_failed`, `orientation_failed`, `artifact_write_failed`, `reconciliation_failed`, `context_synthesis_failed`, `delivery_validation_failed`;
- used: `context_delivered`.

Path values are deterministic:

| Path | `outcome/reason` | `enabled` / `eligible` / source | `context_mode` | Required distinguishing values |
|---|---|---|---|---|
| built-in omission | `bypassed/disabled_default` | `false / true / default` | `off` | no fetch/orient; zero unentered metrics |
| explicit `--no-pr-context` | `bypassed/disabled_cli` | `false / true / cli_explicit` | `off` | no fetch/orient |
| explicit-on custom prompt or file | `bypassed/custom_prompt` | `true / false / cli_explicit` | `off` | custom prompt route unchanged; no fetch/orient |
| explicit-on unsupported profile | `bypassed/unsupported_profile` | `true / false / cli_explicit` | `off` | no fetch/orient |
| enabled, zero normalized | `bypassed/no_remote_context` | `true / true / cli_explicit` | `off` | fetched and normalized are zero; selected/omitted/truncated are zero; empty audit written |
| enabled, nonempty/zero selected | `bypassed/no_selected_context` | `true / true / cli_explicit` | `off` | normalized > 0, selected 0, omitted = normalized; all nonempty artifacts absent during review; unchanged audit written afterward |
| enabled, successful multipass plan abort | `bypassed/plan_aborted` | `true / true / cli_explicit` | `off` | plan call runs with all three paths absent; abort review succeeds; complete audit is written only afterward; orientation artifact remains `not_attempted`; authoritative metadata and one final mirror complete before return |
| first fetch/select/orient/required-write failure | `degraded/<stage reason>` | `true / true / cli_explicit` | `off` | retain completed earlier-stage counts/latency/persistence; later stages zero/not attempted |
| singlepass reconcile fallback | `degraded/reconciliation_failed` | `true / true / cli_explicit` | `off` | orientation usage retained; blind draft is final; delivery/fallback provider fields reflect calls |
| multipass empty-context synth fallback | `degraded/context_synthesis_failed` | `true / true / cli_explicit` | `off` | first context synth and successful empty fallback usage retained |
| successful fresh delivery | `used/context_delivered` | `true / true / cli_explicit` | `on` | injected estimate > 0; final branch usage/latency retained |
| resume non-used/missing/legacy origin | `bypassed/resume_without_used_context` | copy field-valid origin control values, else per-field `false / true / default` | `off` | acquisition fields reset; injected zero; no fetch/orient |
| resume used origin + bad brief | `bypassed/resume_invalid_context` | `true / true / cli_explicit` | `off` | sanitized origin acquisition provenance inherited; injected/delivery zero; persistence mirror is current |
| resume used-valid | `used/context_delivered` | `true / true / cli_explicit` | `on` | exact persisted injection estimate and route delivery usage/latency |
| resume used-valid context provider call fails, empty retry succeeds | `degraded/context_synthesis_failed` | `true / true / cli_explicit` | `off` | same plan/steps; exactly two PR-context synth-stage invocations; context then empty; combined delivery latency and separate nullable delivery/fallback usage retained |
| either resume route returns from provider then ordinary validation fails | `degraded/delivery_validation_failed` | sanitized current resume values | current attempted mode | current delivery usage/latency retained; originating acquisition leaves only per D-18; original failure propagates; no empty retry or final mirror |
| completed/same-head fast no-op or regular reusable review artifact | no new D-14 invocation | unchanged originating payload | unchanged originating payload | preserve nested `meta.json::pr_context` deep-equal with no key/value mutation; no metadata mirror attempt |
| completed-session `--if-reviewed list|latest|prompt-selected` | no new D-14 invocation | no new session payload | no new session payload | return historical output/list before sandbox creation; no context call/artifact/metadata or historical mutation |
| `--no-review` with either context spelling | no new D-14 invocation | no `pr_context` key | no `pr_context` key | preserve session/index-only behavior; no context call or `work/pr_context_*` artifact |

### Field-level fresh/resume metadata oracle

The schema is a run-record dictionary, but a real resume may consume acquisition work performed by its originating fresh run. Field ownership is therefore explicit rather than inferred:

| Field group | Fresh decision path | Resume from missing/non-object/non-`used`/legacy origin | Resume from `used` origin with invalid brief | Resume from `used` origin with valid brief, including empty-context fallback |
|---|---|---|---|---|
| `outcome`, `reason`, `context_mode` | current path | current `bypassed/resume_without_used_context/off` | current `bypassed/resume_invalid_context/off` | current `used/context_delivered/on`; current `degraded/context_synthesis_failed/off` after successful fallback; or current `degraded/delivery_validation_failed` with the attempted mode before original validation failure propagates |
| `enabled`, `eligible`, `enablement_source` | current CLI/eligibility | copy each exact-typed canonical origin value when present; otherwise field defaults `false`, `true`, `default` | canonical `true`, `true`, `cli_explicit` | canonical `true`, `true`, `cli_explicit` |
| all `counts.*` | current completed acquisition/selection stages | reset all to `0` | inherit canonical origin acquisition values | inherit canonical origin acquisition values |
| `estimated_tokens.selected_events`, `.orientation_prompt`, `.orientation_output` | current completed stages | reset to `0` | inherit canonical origin values | inherit canonical origin values |
| `estimated_tokens.injected` | current delivery input | current `0` | current `0` | current exact estimate of the validated persisted brief for both first-attempt success and context-bearing-first-attempt fallback |
| `provider_usage.orientation_*` | current orientation call or `null` | reset to `null` | inherit canonical origin values | inherit canonical origin values |
| `provider_usage.delivery_*`, `.fallback_*` | current delivery calls or `null` | current values (`null` when no call) | current values (`null` when no call) | current first delivery and optional empty-fallback call values; a returned provider call's usage survives ordinary validation failure; never inherit these leaves |
| `truncation.event_body`, `.event_count`, `.prompt_budget`, `.orientation_output` | current completed stages | reset to `false` | inherit canonical origin values | inherit canonical origin values |
| `truncation.injected_context` | current fresh injection | current `false` | current `false` | current `false`: resume validates and reuses exactly and never truncates/repairs |
| `latency_ms.fetch`, `.selection`, `.orientation` | current measured stages | reset to `0` | inherit canonical origin values | inherit canonical origin values |
| `latency_ms.delivery` | current delivery calls | current elapsed context-free synth delivery | current elapsed context-free synth delivery | current first attempt plus fallback elapsed milliseconds when fallback occurs; returned-call elapsed time survives ordinary validation failure |
| `latency_ms.total_enrichment` | current eligibility/validator-through-final-route window | current validator window | current validator window | current resume validator/delivery window only; never add inherited acquisition latency |
| `persistence.discussion_artifact`, `.orientation_artifact` | current write state | reset to `not_attempted` | inherit canonical origin write state | inherit canonical origin write state |
| `persistence.meta_artifact`, `.warning` | current final mirror | current attempt | current attempt | current attempt; ordinary validation failure leaves mirror `not_attempted`; mirror failure changes only these leaves |

"Inherit canonical" is field-by-field and never raw-subtree copying: a count/estimate/latency leaf is a non-Boolean integer `>= 0`; provider leaves are `null` or non-Boolean integers `>= 0`; truncation leaves are Booleans; persistence leaves are members of their declared enum. A missing or wrong-typed leaf uses that leaf's schema default (`0`, `null`, `false`, or `not_attempted`). This sanitization does not make an otherwise `outcome == "used"` plus valid brief ineligible. It prevents malformed origin telemetry from contaminating the exact resume dictionary while preserving available source provenance.

Fresh count assignment is also exact:

1. `counts.fetched` is the sum of object items in all three endpoint arrays only after all three calls return and every payload/item passes the strict list/object shape boundary. Any endpoint/shape failure leaves both `fetched` and `normalized` at zero and uses `degraded/fetch_failed`.
2. `counts.normalized` is `len(discussion)` only after all fetched objects normalize successfully. A later normalization failure retains the completed `fetched` value, leaves `normalized` zero, and also uses the combined fetch/normalize-stage reason `degraded/fetch_failed`.
3. `counts.selected`, `counts.omitted = counts.normalized - counts.selected`, and `counts.truncated_events` are assigned only after selection succeeds. Before that, each is zero. Zero-remote and zero-selected paths therefore have exact `0/0/0` and `normalized/0/normalized` normalized-selected-omitted triples respectively.

Once either resume route enters delivery, construct and flush the field-by-field sanitized current record before relying on delivery output; the raw originating dictionary is no longer authoritative for that invocation. This does not change D-17 no-delivery branches, which never enter delivery and preserve the origin deep-equal.

Reason precedence is also exact. Evaluate omission before explicit disable; when explicitly enabled, custom prompt/file precedes unsupported profile. Thereafter the first failing entered stage wins in execution order: fetch/normalize → zero-remote empty-audit write or select → orient/finalize → required pre-context discussion+brief publication → delivery → post-agent nonempty-audit write where applicable. A successful multipass `plan.abort` has no context delivery: only after the blind plan call and successful abort-review completion does it become `bypassed/plan_aborted`, publish the complete audit, flush authoritative metadata, attempt the final mirror once, and return. Zero remote is classified only after the complete empty audit write. Zero selected is classified after selection while the nonempty audit remains in memory; ordinary review runs with all nonempty paths absent, then the audit write completes the bypass. A failed post-agent audit write becomes `degraded/artifact_write_failed` only when no earlier degradation exists; otherwise it updates failed persistence telemetry without replacing the first degradation reason. For resume delivery, any missing/non-object/non-used/legacy origin is `resume_without_used_context`; only a used origin with a bad brief is `resume_invalid_context`. A successful context delivery is `context_delivered`; a successful empty-context fallback retains `degraded/context_synthesis_failed`. An ordinary post-provider validation failure after resume delivery entry records `degraded/delivery_validation_failed` with current provider usage/latency, propagates the original failure, performs no empty retry, and does not produce a final mirror. A failed empty-context retry propagates after the degradation transition and does not produce a final mirror. A final metadata-mirror failure does not replace any determined outcome/reason; it changes only `persistence.meta_artifact` and `persistence.warning`. No-delivery resume exits never enter this precedence table.

Counts and timing unavailable because a stage was not entered remain zero except for the explicitly inherited used-origin acquisition leaves in the field-level oracle; provider usage unavailable from the adapter remains `null`. Latency uses a monotonic clock and `int(max(0.0, end - start) * 1000)` independently per entered stage. Fresh `total_enrichment` spans eligibility entry through final route metadata before the mirror attempt and is zero for pre-I/O disabled/unsupported bypasses; resume `total_enrichment` is the current validator/delivery window and never includes inherited acquisition latency. The build-level observer populates orientation usage; `cure.py` uses executor telemetry after context reconciliation/synthesis and any empty-context synthesis fallback for delivery/fallback usage. Human-readable warnings go to operator-visible stderr/status output and include stage/reason/path but no raw PR bodies.

Metadata is authoritative in session `meta.json::pr_context`; `work/pr_context_meta.json` is the final best-effort mirror defined above.

## Fail-open boundary

Catch only exceptions attributable to a named PR-context enrichment stage:

- discussion fetch for this feature;
- PR-context normalization/selection;
- orientation call/finalization/capping;
- phase-correct discussion/brief artifact publication and pre-agent absence enforcement;
- context insertion/reconciliation;
- failure of the provider call for the first multipass synthesis attempt when it includes non-empty prior context;
- final best-effort PR-context metadata-mirror write, using D-16's retention semantics rather than context-free rerun.

Fallback behavior:

- Before a fresh blind/context-free agent call, establish that discussion plus raw/canonical orientation paths contain no nonempty PR-context artifact. Hold complete discussion/finalized orientation in coordinator memory. Publish the nonempty audit and brief only immediately before a permitted context-bearing call, or publish the audit after all review agent calls on branches with no context-bearing call. A failed pre-context publication warns and records the first `degraded` stage reason; remove partial publications and run context-free only after absence is re-established. Absence/cleanup failure propagates without launching the agent. A post-agent audit-write failure never reruns review.
- Built-in singlepass reconciliation: warn, record `degraded/reconciliation_failed`, and retain the already accepted ordinary blind draft.
- Built-in multipass context synthesis in fresh, regular-resume, or completed-session incremental-resume delivery: only when the context-bearing provider call fails, warn, flush authoritative `degraded/context_synthesis_failed`, then rerender/retry synthesis exactly once with empty prior context from the same successful context-free plan/step outputs. Fresh delivery first removes its nonempty PR-context artifacts and proves absence before launching that empty retry; resume artifact handling remains owned by D-15 and its existing route proofs. On success, retain combined delivery latency, separate nullable delivery/fallback provider-usage fields, and `context_mode=off`; on retry failure, propagate it with no final mirror.
- Final metadata mirror: after any successful route completion (delivery, successful fallback, or bypass), warn once, set the persistence failure fields in authoritative session metadata, do not retry the mirror or review, and preserve route outcome/reason, context mode, review artifact, and telemetry.

Do not catch or relabel checkout failures, invalid base prompt/profile/configuration, ordinary blind draft failure, multipass plan/step failure, failure of the context-free synth retry, cancellation/interrupt, ordinary/final output validation, artifact promotion unrelated to PR context, posting, or session `meta.json` flush/process-control failures. Those retain existing semantics. For either resume route after delivery entry, ordinary post-provider validation first flushes the sanitized current `degraded/delivery_validation_failed` record with returned-call usage/latency, then propagates the original failure without empty retry or final mirror.

## Pilot comparison and release gate

`context_mode`, existing PR/head/profile/model/run coordinates, and the stable metadata permit operators to compare separate `--pr-context` and `--no-pr-context` runs. The pilot may assess duplicate or context-invalid comments, review usefulness, estimates/provider usage, latency, and degradation rate at run level. It does not introduce finding identifiers, dispositions, authoritative resolution, or automated finding matching.

No fixed quality threshold is invented here. Default-on or general release requires a separate change with operator-approved evidence and rollout decision.

## Proof ownership

- TAP-14: parser/default/eligibility, historical-selection pre-session exits, `--no-review`, and real fresh pre-fetch routing.
- TAP-15: public full-audit preservation plus D-13 canonical prompt selection/order/no-selected boundaries.
- TAP-16: orientation output cap/fences, exact-one template insertion, pure build result, and real fresh all-three-path plus isolated-orientation-runtime absence through every blind/context-free branch—including multipass plan-parse fallback and successful plan abort—plus phase-correct publication ordering. Its Codex real-boundary fixture emits a unique sentinel through normal JSON stdout and provider rollout, proves the sentinel is confined to the runtime root's `codex-home`, event/display logs, and orientation-only progress while running, proves ordinary session logs/meta and inherited/default homes never receive it, and proves the entire root is gone before each permissive review launch.
- TAP-17: fresh singlepass/multipass/no-selected/degraded context activation or fallback, explicit plan-parse-fallback publication-before-reconciliation, successful plan-abort post-agent audit/authoritative-metadata completion, artifact/orientation-runtime cleanup gating, shared-log/meta non-contamination, and no-agent-on-absence-failure behavior.
- TAP-18: D-14/D-18 exact metadata including fetched-versus-normalized and resume field ownership, D-16 required/late persistence, and D-17 no-delivery preservation semantics.
- TAP-19: regular `_resume_flow_impl` D-15 authority, context-synth fallback, completed/same-head and reusable-artifact exits, and captured shared synth.
- TAP-20: completed-session incremental resume D-15 authority, context-synth fallback, and captured incremental synth.
- TAP-21: raw GitHub shape, D-19 explicit no-redirect bounded transactional public fallback, strict adapter, and remote-only no-read regression.
- TAP-22: non-enrichment failure propagation, D-19 fetch-boundary degradation, and post-provider validation no-retry/original-propagation behavior.
- TAP-23: focused/full/quality/package/structural and opt-in-only release gates.
