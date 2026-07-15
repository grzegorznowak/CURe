Plan: 🟢 PLAN APPROVED
Status: 🟣 IN REVIEW

## Purpose

`cure pr` currently reviews PRs blind to discussion history — it sees only the PR description and the diff. This change adds a `cure_pr_context` package that fetches all PR discussion (comments, reviews, review comments) and past CURe reviews, deduplicates them, and runs a single LLM orientation scan. The resulting structured brief is delivered through real execution boundaries instead of an in-template protocol illusion. Multipass is unchanged: plan and step prompts remain independent calls, and the synth prompt receives `$PRIOR_CONTEXT` for reconciliation. Singlepass with context uses two real LLM calls: pass 1 renders the normal or big singlepass template without `$PRIOR_CONTEXT` and produces a draft review, then pass 2 calls `_reconcile_prior_context(draft_review, orientation_brief, run_llm)` with the draft plus the brief and emits the final review. Singlepass without context (`orientation_brief == ""`) remains the current one-call path. The feature runs automatically on `cure pr` review runs with no operator flags required.

## Actors

- **Primary:** CURe operator running `cure pr` — receives reviews informed by discussion context without additional flags
- **Secondary:** Review agent (LLM) — consumes orientation guidance via multipass synth `$PRIOR_CONTEXT` or the singlepass reconcile prompt
- **Affected:** PR author / reviewers — their past comments and reviews now influence future automated reviews
- **Reviewer:** CURe maintainer — verifies that the package does not break the existing flow and that tests pass

## Triggering Need

The `cure-subsequent-pr-review` initiative (38 commits) built an 18-file pipeline that turned out to be over-engineering for the real problem. Users reported that what they need is simple orientation about the PR discussion, not a multi-stage classification and verification system. This story implements the simplified version from scratch, porting only the reusable code from the old branch.

## Expected Prerequisites

None. This is the first and only story of the initiative. The old branch `cure-subsequent-pr-review/story-01-intake` is a historical reference, not a live prerequisite.

## Scope

- Create `cure_pr_context/` package with 4 files: `__init__.py`, `fetcher.py`, `corpus.py`, `orient.py`
- Register `cure_pr_context` and top-level `cure_github.py` in `pyproject.toml` so installs/wheels include both
- Add list-capable `gh_api_list`/`gh_fetch` in `cure_github.py` (imported/re-exported by `cure.py`); do not reuse `gh_api_json` for endpoints that return arrays
- `fetch_pr_discussion()`: 3 GitHub endpoints → flat dicts
- `find_past_reviews(..., head_sha)`: local sessions under `sandbox_root` + current remote CURe footers for the same PR across heads + reviewed/current head metadata annotation + combined-source collapse + character 3-gram Jaccard dedup
- `build_orientation_brief()`: LLM scan → fixed sections with inline instructions
- `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)`: orchestration, returns dict with `orientation_brief`, `discussion`, `past_reviews`, `meta`; `discussion` already comes without events duplicated against `past_reviews`
- Inject call in `cure.py::_pr_flow_impl` after `compute_pr_stats`, passing effective `head_sha`
- Add `cure.py::_reconcile_prior_context(draft_review, orientation_brief, run_llm)` with an inline reconcile prompt for singlepass pass 2
- `$PRIOR_CONTEXT` appears only in the shared multipass synth template. Singlepass templates (`prompts/mrereview_gh_local.md`, `prompts/mrereview_gh_local_big.md`) remove `$PRIOR_CONTEXT` and the old in-template sequencing protocol. Singlepass with context uses two real LLM calls: pass 1 produces an independent draft review, pass 2 reconciles that draft with `orientation_brief`; singlepass with `orientation_brief == ""` remains one call. Multipass plan/step/synth remain separate calls; plan and step exclude context, while every fresh or resumed render of the shared synth template supplies `PRIOR_CONTEXT` (the current brief for a fresh run; persisted `work/pr_context_orientation.md` content or `""` for `_resume_flow_impl`).
- Debug artifacts: `work/pr_context_discussion.json`, `work/pr_context_past_reviews.json`
- Unit tests + integration with deterministic fixtures
- Fail hard on any error

## Out of Scope

- Cache or persistent storage
- New CLI flags
- Changes in `cure_flows.py`; `$PRIOR_CONTEXT` belongs to prompt templates and `cure.py` wiring only
- UI/TUI changes
- Truncation of long discussion
- Separate model for the scan (uses the same LLM as the review)
- Guaranteeing that custom prompts (`--prompt` / `--prompt-file`) contain `$PRIOR_CONTEXT`; custom prompt text is operator-owned and is not part of the built-in two-pass contract
- Authoritative GitHub review-thread resolution state; the three REST discussion endpoints do not expose that signal, so `Resolved areas` is based on discussion/past-review content that says an area was addressed or resolved
- Adding `$PRIOR_CONTEXT` to distinct follow-up/resume templates; the existing `_resume_flow_impl` callsite that renders the shared multipass synth template remains in scope and must satisfy that template's substitution contract

## Scenarios / Behavior Examples

### S1 — Baseline: PR with no discussion or past reviews
- Given: new PR, 0 comments, 0 reviews, 0 prior local sessions
- When: `cure pr` runs
- Then: `build_pr_context()` returns `orientation_brief = ""`. Built-in singlepass skips `_reconcile_prior_context()` and runs exactly one LLM call as today; multipass synth renders `PRIOR_CONTEXT=""` without leaving raw `$PRIOR_CONTEXT` tokens.
- Covers: A6

### S2 — PR with active discussion, no past CURe reviews
- Given: PR with 15 comments from 3 authors, 2 reviews (CHANGES_REQUESTED + APPROVED), 8 inline review comments. No prior local sessions.
- When: `cure pr` runs
- Then: The scanner receives all 25 normalized events and returns the five-section `orientation_brief`. Its prompt defines "Resolved areas" as areas that the supplied discussion or past-review text describes as addressed or resolved; the section may be empty and does not claim authoritative GitHub thread-resolution state.
- Covers: A5

### S3 — PR with past CURe review (local session + remote footer), dedup
- Given: PR with one prior CURe review represented by both a completed local session and its posted comment/review body with an official CURe footer. The posted body also appears as a comment in the discussion. 5 other normal comments.
- When: `cure pr` runs
- Then: The local and posted representations collapse to one retained `past_reviews` entry. The duplicate posted comment is removed from `discussion` output/debug/LLM input (one past review + the 5 normal comments remain). `meta.n_deduped = 1`.
- Covers: A4

### S4 — Error: GitHub API fails
- Given: a list-capable `gh_fetch` raises while `build_pr_context()` fetches PR discussion
- When: `build_pr_context()` runs
- Then: the exception propagates instead of returning a partial PR-context result.
- Covers: A2

### S5 — Multipass synth receives `$PRIOR_CONTEXT` (plan and steps do not)
- Given: large PR that triggers the `big` profile and multipass is enabled
- When: `cure pr` runs in multipass mode
- Then: The plan and each step are executed WITHOUT `$PRIOR_CONTEXT` — they are independent review passes. The multipass synth prompt receives `$PRIOR_CONTEXT` and reconciles it against the independent step findings in the synth call.
- Covers: A8

### S6 — Big singlepass with context uses two real calls
- Given: large PR that triggers the `big` profile, multipass is disabled by config or CLI, and `orientation_brief` is non-empty
- When: `cure pr` runs in singlepass mode with `prompts/mrereview_gh_local_big.md`
- Then: Pass 1 renders the big singlepass prompt without `$PRIOR_CONTEXT` and produces a draft review. Pass 2 calls `_reconcile_prior_context(draft_review, orientation_brief, run_llm)` with the draft plus the brief and returns the final review. If `orientation_brief == ""`, pass 2 is skipped and the path is unchanged from today.
- Covers: A8

### S7 — Interrupted multipass resumes at synth without a raw token
- Given: a multipass PR review was interrupted before synth and its work directory may or may not contain the persisted `pr_context_orientation.md`
- When: `_resume_flow_impl` renders `prompts/mrereview_gh_local_big_synth.md`
- Then: The render always supplies `PRIOR_CONTEXT`; it uses the persisted orientation brief when present and `""` when absent, and the rendered synth prompt contains no raw `$PRIOR_CONTEXT` token.
- Covers: A8

### S8 — GitHub discussion arrays normalize through the list-capable boundary
- Given: deterministic array responses for issue comments, PR reviews, and inline review comments
- When: `fetch_pr_discussion()` calls all three endpoints through `gh_fetch`
- Then: it returns one flat normalized event list with the A3 keys and preserves endpoint-specific review/path fields.
- Covers: A3

### S9 — Error: singlepass prior-context reconciliation fails
- Given: built-in singlepass has produced a draft, `orientation_brief` is non-empty, and the reconcile LLM call raises
- When: `_pr_flow_impl` calls `_reconcile_prior_context()`
- Then: the exception propagates, the run is recorded as failed, and the independent draft is not accepted as a successful final review.
- Covers: A12

### S10 — Installed distribution exposes the PR-context modules
- Given: a wheel built from the repository is installed into an isolated target
- When: Python imports `cure_pr_context` and `cure_github` from that target
- Then: both imports succeed from the installed distribution.
- Covers: A11

## Acceptance

- **A1:** `cure_pr_context/` package exists with 4 files: `__init__.py`, `fetcher.py`, `corpus.py`, `orient.py`
- **A2:** `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)` returns a dict with keys `orientation_brief`, `discussion`, `past_reviews`, `meta`, or raises an exception on error; `head_sha` is the current PR/review SHA used to annotate prior-review head metadata (`reviewed_head`, `current_head`, match status), never to exclude same-PR reviews from earlier heads; `gh_fetch` is list-capable (`cure_github.gh_api_list`/bound callable), not `gh_api_json`
- **A3:** `fetch_pr_discussion()` calls 3 GitHub endpoints via `gh_fetch` and returns a list of flat dicts with keys `kind`, `author`, `body`, `created_at`, `url`, `path`, `line`, `review_state`
- **A4:** `find_past_reviews()` detects local sessions (`review.md`) under `sandbox_root` and official remote CURe footers (in issue comments and review bodies) delimited by `CURE_REVIEW_FOOTER_START` / `CURE_REVIEW_FOOTER_END` with token `sha <short>`, retains all same-PR CURe reviews regardless of reviewed head SHA, ignores remote footer/session metadata that indicates a different PR, annotates `reviewed_head`, `current_head`, and match status when both are known, collapses local and posted remote representations of one completed review to one retained `past_reviews` entry, and deduplicates discussion with character 3-gram Jaccard ≥ 0.85 (inclusive) while removing duplicate events from `discussion`
- **A5:** `build_orientation_brief()` sends normalized discussion, retained past reviews, and PR stats to one LLM scan whose prompt defines `Resolved areas` only from supplied text that describes an area as addressed or resolved (not authoritative GitHub thread state), then produces a string with five actual Markdown level-2 headings (`## Resolved areas`, `## Problem areas`, `## Pending issues`, `## Repeated patterns`, `## Decisions made`) and inline usage instructions; arbitrary mentions of those names do not satisfy the heading requirement
- **A6:** When there is no discussion or past reviews, `orientation_brief` is `""`; built-in singlepass paths skip `_reconcile_prior_context()` and remain one-call reviews, while multipass synth substitutes `PRIOR_CONTEXT=""` so no raw `$PRIOR_CONTEXT` remains
- **A7:** `build_pr_context()` is called from `_pr_flow_impl` after `compute_pr_stats`, before the final multipass/singlepass decision, and receives effective `head_sha` (`review_head_sha` if it exists, otherwise PR API `head_sha`)
- **A8:** `$PRIOR_CONTEXT` appears only in `prompts/mrereview_gh_local_big_synth.md` (the shared multipass synth template). Normal singlepass, big singlepass, multipass plan, and multipass step templates have no `$PRIOR_CONTEXT` token. Singlepass context is delivered only by the second LLM call `_reconcile_prior_context(draft_review, orientation_brief, run_llm)` after an independent draft pass; singlepass with `orientation_brief == ""` remains one call. Every fresh or resumed render of the shared synth template supplies `PRIOR_CONTEXT`: `_pr_flow_impl` uses the current orientation brief, while `_resume_flow_impl` reads persisted `work/pr_context_orientation.md` when present and otherwise uses `""`; no rendered synth prompt may retain the raw token. Custom prompts and distinct follow-up/resume templates are excluded.
- **A9:** Debug artifacts `work/pr_context_discussion.json` (pruned discussion) and `work/pr_context_past_reviews.json` (retained past reviews) are written even when `orientation_brief` is `""` (as long as there is data)
- **A10:** Unit tests per module (`fetcher`, `corpus`, `orient`) + end-to-end integration test with deterministic fixtures
- **A11:** `pyproject.toml` includes `cure_pr_context` and top-level `cure_github.py` in the explicit setuptools metadata, and an install/wheel smoke can import both `cure_pr_context` and `cure_github`
- **A12:** When built-in singlepass has a non-empty `orientation_brief` and `_reconcile_prior_context()`'s LLM call raises, `_pr_flow_impl` propagates the exception, records the run as failed, and does not accept the independent draft as a successful final review

## Verification

### Fail-open Checks

#### Prompt/template substitution (risk lens: prompt/template substitution)

- **No raw `$PRIOR_CONTEXT` tokens leak:** `render_prompt` (`cure_flows.py:1437`) replaces `$KEY` and `${KEY}` only for values present in `extra_vars`. Built-in normal/big singlepass, plan, and step templates must not contain `$PRIOR_CONTEXT`; the shared multipass synth template is the only built-in template with the token, and every fresh/resumed callsite must receive `extra_vars["PRIOR_CONTEXT"]` (current/persisted brief or `""`). TAP-06/TAP-07 verify the fresh and resumed synth paths plus negative template checks.
- **Empty-string path (baseline):** When `orientation_brief == ""`, built-in singlepass skips `_reconcile_prior_context()` and completes exactly one review call as it does today. Fresh multipass synth receives `extra_vars["PRIOR_CONTEXT"] = ""`; resumed synth does the same when `work/pr_context_orientation.md` is absent. In both cases `render_prompt` removes `$PRIOR_CONTEXT`. TAP-06/TAP-07 cover.
- **Enabled path (activation):** When `orientation_brief` is non-empty, singlepass first produces a draft from the normal/big template without context, then `_reconcile_prior_context()` sends a second prompt containing the draft plus the orientation brief. Multipass substitutes the brief into the synth template as `$PRIOR_CONTEXT`. TAP-06/TAP-07 cover.
- **Degraded path (API/LLM failure):** `build_pr_context()` failure propagates instead of returning partial context (A2/TAP-04). A reconcile LLM failure propagates through `_reconcile_prior_context()` and `_pr_flow_impl`, records the run as failed, and cannot promote the independent draft to a successful final review (S9/A12/TAP-07). TAP-05 is a deterministic happy-path package integration seam and does not claim orchestration failure proof.

### Input Boundary Shape Risk

| Boundary | Source shape | Strict assumption / risk | Required mitigation | Proof |
|----------|--------------|--------------------------|---------------------|-------|
| GitHub discussion endpoints | JSON arrays from comments/reviews/review-comments endpoints | Existing `gh_api_json` rejects non-dict payloads | Add/port `gh_api_list` in `cure_github.py`; `fetch_pr_discussion` accepts only list-capable `gh_fetch` and normalizes arrays | TAP-01, TAP-04, TAP-05 |
| PR metadata endpoint | JSON object | Existing `gh_api_json` remains appropriate for PR metadata | Do not replace metadata fetch with list helper | TAP-07 code review |
| Local prior sessions | Directories under `sandbox_root` / `~/.local/state/cure/sandboxes` | A nonexistent `sessions_root` would miss completed sessions | Pass the real `sandbox_root` into `find_past_reviews` | TAP-02, TAP-04 |
| Remote CURe footers | Markdown bodies with current official footer block and `sha <short>` token | Old `CURe-pr-footer reviewed_head=` contract would miss live footers; limiting context to the current head would discard useful prior reviews from earlier heads | Parse `CURE_REVIEW_FOOTER_START`/`END`, `sha`, and `session` metadata; ignore metadata for a different PR; pass current `head_sha` from `_pr_flow_impl` to annotate `reviewed_head`, `current_head`, and match status while retaining same-PR reviews across heads | TAP-02, TAP-05, TAP-07 |
| Prompt templates / reconcile prompt | Missing `extra_vars` key leaves raw `$PRIOR_CONTEXT`; shared-template callsites can drift; embedding context in one prompt does not create sequential reasoning; reconcile failures could leave a draft looking successful | Fail-open raw token leak, false singlepass sequencing, or swallowed reconcile failure | Only multipass synth contains `$PRIOR_CONTEXT`; every fresh/resumed synth render supplies current/persisted context or `""`; singlepass templates contain no token and use `_reconcile_prior_context()` for a real second pass; reconcile exceptions propagate and fail the run | TAP-06, TAP-07 |
| Packaging metadata | Explicit setuptools package/module lists | New package or adapter module omitted from installs | Add `cure_pr_context` to `pyproject.toml` packages, add `cure_github` to `py-modules`, and run import smoke for both | TAP-09 |

### Surface / Branch Proof Matrix

| Surface / branch | In scope? | `$PRIOR_CONTEXT` obligation | Proof |
|------------------|-----------|-----------------------------|-------|
| Normal singlepass built-in review (`prompts/mrereview_gh_local.md`) | Yes | Template contains no `$PRIOR_CONTEXT`; with non-empty `orientation_brief`, it produces the independent draft for the reconcile pass; with empty context, it remains the only call | TAP-06, TAP-07 |
| Big singlepass built-in review (`prompts/mrereview_gh_local_big.md`) | Yes | Same as normal singlepass, including when multipass is disabled | TAP-06, TAP-07 |
| Singlepass reconcile prompt (`cure.py::_reconcile_prior_context`) | Yes, only when context exists | Second LLM call receives `draft_review` + `orientation_brief` and emits the final review; code evidence in the draft wins over unsupported context claims; if the call raises, `_pr_flow_impl` fails the run and does not accept the draft as final | TAP-06, TAP-07 |
| Multipass plan (`prompts/mrereview_gh_local_big_plan.md`) | Yes, without `$PRIOR_CONTEXT` | Independent review pass — plan template intentionally excludes `$PRIOR_CONTEXT` | TAP-07 code review |
| Multipass step (`prompts/mrereview_gh_local_big_step.md`) | Yes, without `$PRIOR_CONTEXT` | Independent review pass — step template intentionally excludes `$PRIOR_CONTEXT` | TAP-07 code review, TAP-06 negative proof |
| Fresh multipass synth (`_pr_flow_impl` + `prompts/mrereview_gh_local_big_synth.md`) | Yes | Supplies the current orientation brief or `""` and reconciles independent step findings with context using Option B rules | TAP-06, TAP-07 |
| Resumed multipass synth (`_resume_flow_impl` + shared synth template) | Yes | Reads persisted `work/pr_context_orientation.md` when present, otherwise supplies `""`; rendered prompt has no raw token | TAP-07 |
| Custom prompt files / inline prompts | No template insertion guarantee | User-owned text is out of scope and is not part of the built-in two-pass contract | Explicit exclusion in A8 |
| Distinct follow-up/resume templates | No | No insertion into other templates; this does not exclude callsites rendering the shared synth template | Explicit exclusion in A8 |

### Risk Lens Inventory

| Risk lens | Activated? | Coverage / exclusion |
|-----------|------------|----------------------|
| External services / subprocess I/O | Yes | GitHub list-boundary behavior is covered by TAP-01/TAP-05; package failure propagation is covered by TAP-04 |
| Filesystem / generated artifacts | Yes | `sandbox_root` scanning and `work/pr_context_*.json` artifacts covered by TAP-02/TAP-04/TAP-05 |
| Prompt/template substitution and LLM call boundaries | Yes | Fail-open Checks + TAP-06/TAP-07 |
| Packaging/install surface | Yes | A11 + TAP-09 |
| Persistence/cache/migrations | No | Cache/persistent storage is explicitly out of scope |
| UI/TUI behavior | No | UI/TUI changes are out of scope; progress meta only |

### Design Sources

| Source | Status | Use |
|--------|--------|-----|
| Live CURe code anchors in Discovery Notes (`cure.py`, `cure_flows.py`, `cure_output.py`, `cure_sessions.py`, `paths.py`, `pyproject.toml`, `prompts/`) | normative | Source-fit contracts for API shape, injection point, footer parsing, session root, packaging, and prompt branch coverage |
| Old branch `cure-subsequent-pr-review/story-01-intake` (`github_history.py`, `prior_corpus.py`, old `cure.py`) | orientation only | Porting hints for list helper, discussion normalization, and footer parsing; verify against live code before implementation |

### Design Element Trace

| Design element | Status | Scenario → Acceptance → Verification trace |
|----------------|--------|--------------------------------------------|
| List-capable GitHub discussion normalization via `gh_fetch`/`cure_github.gh_api_list` | required | S8 → A3 → TAP-01/TAP-05 |
| Public PR-context orchestration failure boundary | required | S4 → A2 → TAP-04 |
| Scanner payload, headings, and text-derived `Resolved areas` semantics | required | S2 → A5 → TAP-03 |
| Real prior-review corpus sources (`sandbox_root`, official footer markers, current `head_sha` metadata) | required | S3 → A4 → TAP-02/TAP-05 |
| Empty-context delivery | required | S1 → A6 → TAP-04/TAP-06/TAP-07 |
| Context-bearing fresh, resumed, and singlepass delivery | required | S5/S6/S7 → A8 → TAP-06/TAP-07 |
| Reconcile fail-hard boundary | required | S9 → A12 → TAP-07 |
| Package installability | required | S10 → A11 → TAP-09 |

### Verification Commands

```bash
# Unit tests
python -m pytest tests/cure_pr_context/ -v

# Integration test (fixtures deterministas, sin GitHub real)
python -m pytest tests/cure_pr_context/test_integration.py -v

# Template + flow branch proof
python -m pytest tests/cure_pr_context/test_templates.py tests/test_cure_pr_flow.py -v

# Ruff + mypy
ruff check cure_github.py cure_pr_context/
mypy cure_github.py cure_pr_context/

# Packaging smoke (no install into repo environment)
rm -rf .tmp_package_smoke
python -m pip wheel . -w .tmp_package_smoke/wheelhouse
python -m pip install --no-deps --target .tmp_package_smoke/install .tmp_package_smoke/wheelhouse/cureview-*.whl
PYTHONPATH=.tmp_package_smoke/install python -c "import cure_pr_context, cure_github"

# Full CURe test suite (ensure no regressions)
python -m pytest tests/ -x --timeout=120
```

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|--------|--------------|---------------------------|----------------------|-------------------|--------------------------|----------------------------|-------------------|---------------|------------------------|
| TAP-01 | Unit | `fetch_pr_discussion` — 3 endpoints, normalization, list-capable caller | `tests/cure_pr_context/test_fetcher.py` | GitHub API boundary (mocked `gh_fetch`/`cure_github.gh_api_list`) | dict keys, event count, field types, caller paths, array handling | Mock `gh_fetch` returning list payloads per endpoint | `pytest tests/cure_pr_context/test_fetcher.py` | If mock becomes fragile, use recorded responses | One test per endpoint + failure test |
| TAP-02 | Unit | `find_past_reviews` + `deduplicate` — local sandbox sessions + remote official footers; retained side is `past_reviews`, duplicate source representations collapse, and duplicate discussion events are pruned | `tests/cure_pr_context/test_corpus.py` | Filesystem (`sandbox_root` session dirs) + in-memory discussion + current `head_sha` metadata | past review count, footer detection, SHA/session metadata, same-PR retention across heads, different-PR rejection, reviewed/current head annotation, local/posted-copy collapse, character 3-gram threshold boundary, retained-side/pruned-discussion, dedup count | Temporary directories with fake `review.md`; in-memory discussion events with `CURE_REVIEW_FOOTER_START/END`; matching-head, different-head same-PR, different-PR, and identical local/posted review fixtures; synthetic strings with 3-gram Jaccard exactly 0.85 | `pytest tests/cure_pr_context/test_corpus.py` | If the session scan is slow, reduce fixtures without removing retained-side/head-metadata/source-collapse cases | Separate tests: local, remote, dedup/head metadata, 3-gram boundary |
| TAP-03 | Unit | `build_orientation_brief` — one LLM scan with payload, fixed sections, and bounded resolved-area semantics | `tests/cure_pr_context/test_orient.py` | LLM prompt/output boundary (mocked) | Captured prompt contains normalized discussion/past-review/stats payload and states that `Resolved areas` comes only from supplied text, not authoritative thread state; output contains all five actual `##` headings and usage instructions; usage-only section-name mentions do not suppress normalization | Mock `run_llm` captures prompt and returns a partial brief or usage-only text; fixture includes text that says an area was resolved without a resolution boolean | `pytest tests/cure_pr_context/test_orient.py` | If the format changes, update mock while retaining the semantic-boundary assertion | Payload/prompt contract + partial-section + usage-only heading normalization tests |
| TAP-04 | Unit | `build_pr_context` — internal integration of the 3 modules | `tests/cure_pr_context/test_init.py` | Full public API, including explicit `head_sha` parameter | Dict keys, meta values, `head_sha` propagated to corpus, fail-hard on errors, debug artifact paths, `PRIOR_CONTEXT` empty path | `pr_stats` fixture + `head_sha` fixture + mock `gh_fetch` + mock `run_llm` + tmp sandbox/work dirs | `pytest tests/cure_pr_context/test_init.py` | Convert to real integration if mock becomes fragile | Covers A2, A6, A7 |
| TAP-05 | Package integration | Deterministic happy-path composition for A2/A3/A4/A9 and the end-to-end portion of A10 | `tests/cure_pr_context/test_integration.py` | `build_pr_context`: three endpoint arrays → normalized events → same-PR corpus/head annotation → retained-side dedup → orient → debug artifacts | Public result/meta shape; endpoint-kind counts; matching/different-head same-PR reviews retained; different-PR footer stays discussion; head metadata annotated; duplicate discussion pruned; persisted discussion/past-review artifacts match returned data | In-memory JSON arrays for all 3 API responses; matching-head and different-head same-PR footer bodies; different-PR footer body; mock LLM; isolated tmp sandbox/work dirs | `pytest tests/cure_pr_context/test_integration.py` | Add deterministic package-level fixtures only for package-pipeline regressions; flow/template/install branches remain owned by TAP-06/TAP-07/TAP-09 | Kept separate from unit rows to prove module composition; intentionally does not claim file-count, scanner-format, `cure.py` routing/template, failure, or packaging surfaces |
| TAP-06 | Integration | Template contract + reconcile prompt contract | `tests/cure_pr_context/test_templates.py` | `render_prompt` with `extra_vars`; `_reconcile_prior_context` prompt construction/call seam | Multipass synth template contains `$PRIOR_CONTEXT` and renders with brief/`""`; normal and big singlepass templates do NOT contain `$PRIOR_CONTEXT`; plan/step templates do NOT contain it; reconcile prompt includes draft review + orientation brief and returns the reconciled review | Real built-in templates; mocked `run_llm` for reconcile prompt | `pytest tests/cure_pr_context/test_templates.py` | If templates move, update paths | Covers A6, A8 |
| TAP-07 | Flow integration | A6/A7/A8/A12 — `cure.py` context routing: injection/effective head; two-pass singlepass success and fail-hard reconcile; empty-context one-call path; fresh/resumed synth substitution | `tests/test_cure_pr_flow.py` | `_pr_flow_impl` + `_resume_flow_impl`, singlepass/reconcile LLM seam, multipass step/synth rendering, persisted orientation artifact, and `cure_github` re-export seam | Runtime tests prove call order/effective `review_head_sha`, independent draft then reconcile, empty-context gating, and a reconcile LLM exception propagating with failed-run observability and no successful final-review acceptance; fresh/resumed synth render tests prove present/absent artifact substitution and no raw token; static/source-fit assertions keep plan/step context-free and helpers re-exported | Mock `build_pr_context`; synthetic PR URL; non-empty/empty context cases; reconcile `run_llm` exception fixture; prompt-profile/multipass branches; temporary `work/pr_context_orientation.md`; isolated progress/output paths | `pytest tests/test_cure_pr_flow.py` | Extract a small shared synth-render helper if `_resume_flow_impl` is too expensive to exercise directly, but retain runtime proof for reconcile failure propagation and at least one source-fit assertion for both synth callsites | Split runtime tests by observable branch (context success, empty context, reconcile failure, resume artifact present, resume artifact absent); shared harness may be reused without merging assertions across branches |
| TAP-08 | Lint/Type | Ruff formatting + mypy type checking | `cure_github.py`, `cure_pr_context/` | Style and types | Ruff clean, mypy clean | N/A | `ruff check cure_github.py cure_pr_context/ && mypy cure_github.py cure_pr_context/` | N/A | Quality |
| TAP-09 | Packaging | Installed package/module contains/imports `cure_pr_context` and `cure_github` | `pyproject.toml` + packaging smoke command | setuptools explicit package/module lists / wheel install | `pyproject.toml` includes `cure_pr_context` and `cure_github`; `python -c "import cure_pr_context, cure_github"` succeeds from wheel target | Local wheel built into `.tmp_package_smoke/` | packaging smoke commands above | If wheel tooling unavailable, `pip install -e .` smoke in disposable env | Covers A11 |

**Current source-fit status:** TAP-02 and TAP-05 exercise the amended A4 contract. TAP-03 captures the scanner's normalized payload and bounded resolved-area semantics. TAP-07 proves persisted-or-empty resume substitution and reconcile fail-hard observability. The deterministic focused and full suites pass.

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|--------------|---------------|-------------|-----------------|------------------|------------------|-------------|
| A1 | final | Repository file listing | Verify exact package file set | `cure_pr_context/` contains exactly `__init__.py`, `fetcher.py`, `corpus.py`, and `orient.py` | `cure_pr_context/` | — |
| A2 | final | TAP-04 + TAP-05 | Run unit/package-integration tests and review signature | TAP-05 proves the successful public result/meta shape with explicit `head_sha` and list-capable `gh_fetch`; TAP-04 proves exceptions propagate instead of returning partial context | `__init__.py`, `tests/cure_pr_context/test_init.py`, `tests/cure_pr_context/test_integration.py` | — |
| A3 | final | TAP-01 | Run tests + review code | Fetch tests pass, 3 mock calls verified | `fetcher.py` | — |
| A4 | final | TAP-02 + TAP-05 | Run tests + review code | Corpus and integration tests pass with `sandbox_root` and official footer verified, same-PR different-head reviews retained, different-PR footer metadata ignored, head metadata annotated, local/posted copies collapsed to one retained review, character 3-gram Jaccard proven at the inclusive 0.85 boundary, and duplicate discussion pruned | `corpus.py`, `cure_sessions.py`, `cure_output.py`, `cure.py`, `tests/cure_pr_context/test_corpus.py`, `tests/cure_pr_context/test_integration.py` | — |
| A5 | final | TAP-03 | Run tests and inspect captured scanner prompt | Scanner receives normalized payload; prompt bounds `Resolved areas` to supplied text rather than authoritative thread state; partial and usage-only outputs normalize to all five actual Markdown `##` headings plus instructions | `orient.py`, `tests/cure_pr_context/test_orient.py` | — |
| A6 | final | TAP-04 + TAP-06 + TAP-07 | Run tests | `orientation_brief=""` → singlepass skips reconcile and remains one call; multipass synth renders `PRIOR_CONTEXT=""`; no raw `$PRIOR_CONTEXT` remains | `__init__.py`, templates, `cure.py`, `cure_flows.py` | — |
| A7 | final | TAP-07 | Run flow tests + code review | Runtime mocked `_pr_flow_impl` proof shows `build_pr_context` called after `compute_pr_stats`, before prompt routing, with effective `review_head_sha`; flow branches choose reconcile only when context exists | `cure.py`, `tests/test_cure_pr_flow.py` | — |
| A8 | final | TAP-06 + TAP-07 + Surface / Branch Proof Matrix | Run tests + review templates and both synth-render callsites | Only the shared multipass synth template contains `$PRIOR_CONTEXT`; normal/big singlepass and plan/step templates exclude it; `_reconcile_prior_context()` handles singlepass context in a second LLM call; fresh and resumed synth renders supply context or `""` with no raw token; custom/distinct follow-up exclusions documented | templates, `cure.py`, `tests/test_cure_pr_flow.py` | — |
| A9 | final | TAP-04 + TAP-05 | Run tests, verify written files | `work/pr_context_discussion.json` exists with pruned discussion and `work/pr_context_past_reviews.json` exists with retained past reviews | `__init__.py`, `work/` | — |
| A10 | final | TAP-01..TAP-05 | Run `pytest tests/cure_pr_context/` | All deterministic module and end-to-end tests pass | `tests/cure_pr_context/` | — |
| A11 | final | TAP-09 | Review `pyproject.toml`, run smoke | `cure_pr_context` package and `cure_github` module included in wheel/install and importable | `pyproject.toml`, wheel smoke | — |
| A12 | final | TAP-07 | Run the deterministic reconcile-failure flow test and inspect failed-run observability | Reconcile LLM exception propagates from `_reconcile_prior_context()` through `_pr_flow_impl`; progress records failure; no successful final-review acceptance occurs | `cure.py`, `tests/test_cure_pr_flow.py` | — |

## Critical Files

**New:**
| Path | Role |
|------|------|
| `cure_pr_context/__init__.py` (new) | Public API `build_pr_context(..., head_sha, ...)`, module orchestration |
| `cure_pr_context/fetcher.py` (new) | `fetch_pr_discussion()` — 3 GitHub endpoints via `gh_fetch`/`gh_api_list` |
| `cure_pr_context/corpus.py` (new) | `find_past_reviews(..., head_sha)` + character 3-gram Jaccard dedup, using `sandbox_root`, official CURe footers, same-PR retention across heads, combined local/posted source collapse, reviewed/current head annotation, and duplicate discussion pruning |
| `cure_pr_context/orient.py` (new) | `build_orientation_brief()` — LLM scan |
| `tests/cure_pr_context/test_fetcher.py` (new) | Unit tests fetcher |
| `tests/cure_pr_context/test_corpus.py` (new) | Unit tests corpus |
| `tests/cure_pr_context/test_orient.py` (new) | Unit tests orient |
| `tests/cure_pr_context/test_init.py` (new) | Unit tests `build_pr_context` |
| `tests/cure_pr_context/test_integration.py` (new) | Integration end-to-end |
| `tests/cure_pr_context/test_templates.py` (new) | Template variable injection |
| `cure_github.py` (new) | GitHub CLI/public API adapter: `gh_api_json`, `gh_api_list`, auth/fallback helpers, list decoding/pagination fallback |

**Modified:**
| Path | Role |
|------|------|
| `pyproject.toml` | Add `cure_pr_context` to explicit `packages`, add `cure_github` to `py-modules`, and enable packaging smoke |
| `cure.py` | Import/re-export GitHub helpers, insert `build_pr_context()` after `compute_pr_stats`, pass effective `head_sha`, add `_reconcile_prior_context(draft_review, orientation_brief, run_llm)` for singlepass pass 2, and supply `PRIOR_CONTEXT` at both fresh (`_pr_flow_impl`) and resumed (`_resume_flow_impl`) renders of the shared multipass synth template |
| `prompts/mrereview_gh_local.md` | Remove `$PRIOR_CONTEXT` and the old in-template sequencing protocol; normal singlepass draft prompt stays independent |
| `prompts/mrereview_gh_local_big.md` | Remove `$PRIOR_CONTEXT` and the old in-template sequencing protocol; big singlepass draft prompt stays independent when multipass is disabled |
| `prompts/mrereview_gh_local_big_plan.md` | Intentionally excludes `$PRIOR_CONTEXT` (independent review pass) |
| `prompts/mrereview_gh_local_big_step.md` | Intentionally excludes `$PRIOR_CONTEXT` (independent review pass) |
| `prompts/mrereview_gh_local_big_synth.md` | Only built-in review template with `$PRIOR_CONTEXT` (multipass synth reconciliation) |

**Reference (read-only):**
| Path | Role |
|------|------|
| `cure_subsequent_review/github_history.py` (old branch) | Port fetch/list helper logic as orientation |
| `cure_subsequent_review/prior_corpus.py` (old branch) | Port official footer detection and session scan as orientation |

## Implementation Notes

**Implementation order (dependencies):**
1. `cure_github.py::gh_api_list` — port/adapt list-capable helper before implementing live fetcher; import/re-export from `cure.py` for existing call sites
2. `fetcher.py` — uses `gh_fetch`, has no internal dependencies, testable in isolation
3. `corpus.py` — depends on `fetcher` to receive discussion events; uses `sandbox_root`, effective `head_sha` as current-head metadata, and current official footers
4. `orient.py` — depends on `fetcher` + `corpus` to receive data → LLM
5. `__init__.py` — integrates the 3, orchestrates `build_pr_context(..., head_sha, ...)`, and writes deduplicated debug artifacts in `work_dir`
6. `pyproject.toml` — add `cure_pr_context` to the explicit package list and `cure_github` to `py-modules`
7. Templates — remove `$PRIOR_CONTEXT` and the old sequencing protocol from normal/big singlepass templates; keep `$PRIOR_CONTEXT` only in multipass synth; plan/step remain context-free (parallel to 1-6)
8. `cure.py` — inject the context build call, pass effective `head_sha`, add `_reconcile_prior_context()` with the inline pass-2 prompt, branch singlepass so non-empty context performs draft → reconcile while empty context remains one call, and make `_resume_flow_impl` read `work/pr_context_orientation.md` (or `""`) for shared synth rendering (last, once the package is ready)

**Smallest red-first seam:** `fetcher.py` with mock `gh_fetch`/`gh_api_list` that returns arrays.

**Phases:**
- Phase 0: `cure_github.py::gh_api_list` + packaging metadata smoke (TAP-09 setup)
- Phase 1: `fetcher.py` + tests (TAP-01) — RED → GREEN
- Phase 2: `corpus.py` + tests (TAP-02) — RED → GREEN
- Phase 3: `orient.py` + tests (TAP-03) — RED → GREEN
- Phase 4: `__init__.py` + tests (TAP-04) — RED → GREEN
- Phase 5: Integration + template contract + singlepass reconcile flow + `cure.py` (TAP-05, TAP-06, TAP-07)
- Phase 6: Ruff + mypy clean (TAP-08), packaging smoke (TAP-09), full test suite

**Constraints:**
- The old `github_history.py` uses a `DiscussionEvent` dataclass with 15 fields; simplify to dicts with 6-8 keys
- The old `prior_corpus.py` has already-tested footer detection logic, but the normative source is the current CURe footer (`CURE_REVIEW_FOOTER_START/END` + `sha <short>`)
- `render_prompt` in `cure_flows.py:1437` already supports `extra_vars` — no changes required, but `PRIOR_CONTEXT` must be present at every fresh or resumed render of the shared multipass synth template; normal/big singlepass templates must not contain `$PRIOR_CONTEXT`

## Locked Decisions

A single `cure_pr_context/` package with 4 files plus a small top-level `cure_github.py` adapter module. The public PR-context API is `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)` returning a dict; `sandbox_root` is the real root of completed sandboxes/sessions (`paths.sandbox_root`), `work_dir` is the current session's `work/` directory for debug artifacts, `pr_stats` is the result already computed by `compute_pr_stats`, `head_sha` is the effective PR/review SHA that `_pr_flow_impl` passes explicitly to annotate prior-review head metadata (`reviewed_head`, `current_head`, match status), and `gh_fetch` is a list-capable callable based on `cure_github.gh_api_list` (not `gh_api_json`). Same-PR CURe reviews are retained even when their reviewed head differs from the current head; remote footer/session metadata that indicates a different PR is ignored. The brief is produced by a single LLM scan with fixed sections and inline usage instructions. Prior-context delivery is branch-specific: multipass synth is the only built-in review template with `$PRIOR_CONTEXT`; normal/big singlepass, multipass plan, and multipass step templates have no token. Singlepass with non-empty context uses two real LLM calls: first the normal/big template produces an independent draft, then `cure.py::_reconcile_prior_context(draft_review, orientation_brief, run_llm)` uses an inline reconcile prompt to produce the final review. Singlepass with `orientation_brief == ""` remains one call. Multipass plan and step behavior is unchanged. Every render of the shared synth template receives `PRIOR_CONTEXT`: `_pr_flow_impl` supplies the current brief or `""`, and `_resume_flow_impl` reads persisted `work/pr_context_orientation.md` when present or supplies `""` when absent; synth reconciles independent step findings with Option B rules. Past-review deduplication collapses identical local/posted representations, then uses character 3-grams + Jaccard ≥ 0.85 (inclusive) with no external dependencies; `past_reviews` is the retained side and duplicate events are removed from the returned/written/LLM-passed `discussion`. The LLM is received as a `Callable` injected from `cure.py`. Any error aborts the review. No cache, no new CLI flags, no changes to `cure_flows.py`.

## Discovery Notes

- The old `github_history.py` in `cure-subsequent-pr-review/story-01-intake` has ~300 lines. `collect_pr_discussion()` uses `gh_api_list` (not `gh_api_json`) for the 3 endpoints because GitHub returns arrays. Pagination handling is in `PaginationMarker`.
- `cure_github.gh_api_json` validates `isinstance(payload, dict)` and fails with arrays. The 3 discussion APIs return arrays. Must create/port `gh_api_list` into `cure_github.py` using the pattern from the old branch (`cure.py:7613-7634` in `cure-subsequent-pr-review/story-01-intake`): `gh api --paginate [--slurp]`, fallback without `--slurp`, page flattening.
- `render_prompt` in `cure_flows.py:1437-1491` supports `extra_vars: dict[str, str]`, but only replaces present keys; if `PRIOR_CONTEXT` is missing, `$PRIOR_CONTEXT` remains literal. `_resume_flow_impl` also renders `mrereview_gh_local_big_synth.md`, so the shared-template contract must be enforced at both fresh and resumed synth callsites.
- `_pr_flow_impl` in `cure.py:9334` resolves `head_sha` from the PR API (`cure.py:9371-9375`), `review_head_sha` from the local checkout (`cure.py:9730-9734`), and computes `pr_stats` in `compute_pr_stats` (`cure.py:4162`). The injection point in `_pr_flow_impl` is after `progress.flush()` in `detect_pr_size` (~`cure.py:9754-9767`), before final singlepass/multipass selection/routing; it must pass `review_head_sha or head_sha` as effective `head_sha` to `build_pr_context()`.
- CURe writes current review footers as a block `<!-- CURE_REVIEW_FOOTER_START -->` / `<!-- CURE_REVIEW_FOOTER_END -->` with a line that includes `· sha <short>` (`cure_output.py:22`, `cure_output.py:1547-1549`). Do not use the old hypothetical format `CURe-pr-footer reviewed_head=`.
- `scan_completed_sessions_for_pr` receives `sandbox_root` (`cure_sessions.py:954-980`) and the defaults live in `paths.py` as `~/.local/state/cure/sandboxes` (`paths.py:37-38`, `paths.py:75-77`). Do not design a separate `sessions_root`.
- The built-in review templates are in `prompts/`: `mrereview_gh_local.md` (normal singlepass), `mrereview_gh_local_big.md` (big singlepass), `mrereview_gh_local_big_plan.md`, `_big_step.md`, `_big_synth.md`.
- Live code can use big singlepass when the resolved profile is `big` and multipass is disabled (`cure.py:9847-9867`); `prompt_template_name_for_profile` returns `mrereview_gh_local_big.md` for the `big` profile (`cure.py:4240`).
- `pyproject.toml:16-18` uses explicit setuptools lists (`py-modules = [...]`, `packages = ["prompts"]`), so `cure_pr_context` must be added explicitly to `packages` and `cure_github` must be added explicitly to `py-modules`.
- `write_pr_context_file` in `cure.py` already writes to `work/pr_context.json` — follow that pattern for the debug artifacts.
- `PullRequestRef` (`cure.py:2953-2962`) does not contain SHA, and `compute_pr_stats` (`cure.py:4162-4197`) returns `head_ref` but not SHA; therefore `head_sha` must be an explicit parameter of `build_pr_context()` instead of being inferred from `pr` or `pr_stats`, and it is used as current-head annotation metadata rather than a same-PR exclusion criterion.
- Live CLI does not have a generic `--dry-run` for `cure pr`; the related flag is `--dry-run-chunkhound` (`cure.py:14882`). TAP-07 must use monkeypatch/helper seams if it needs a fallback without running a real review.

## Implementation Log

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

## Plan Review Log

- 2026-07-15T09:40:34Z Prior plan review history compressed by `/openspec-story-plan-resume`
  - Addressed plan-review entries: 2026-06-20T00:00:00Z, 2026-06-20T06:38:04Z, 2026-06-20T06:54:21Z, 2026-06-22T06:58:09Z
  - Superseded approvals: 2026-06-20T07:09:45Z, 2026-06-22T07:31:02Z
  - Preserved decisions: discussion endpoints use list-capable `cure_github.gh_api_list`; `head_sha` annotates rather than filters same-PR past reviews; past-review dedup collapses local/posted copies and uses character 3-grams with inclusive Jaccard 0.85; only the shared multipass synth template owns `$PRIOR_CONTEXT`; singlepass uses independent draft then reconcile; `Resolved areas` is text-derived, not authoritative thread state; deterministic tests, not an unsupported coverage threshold, are the A10 gate.
  - Material evidence anchors: `cure_flows.py:1437-1491` only substitutes supplied keys; `cure.py::_pr_flow_impl`, `_resume_flow_impl`, and `_reconcile_prior_context`; `cure_output.py:22,1547-1549` official footer markers; `cure_sessions.py:954-980` plus `paths.py:37-38,75-77` sandbox root; `pyproject.toml:16-18` explicit setuptools metadata.
  - Latest pre-compression implementation evidence: focused context/flow tests 24 passed, full suite 644 passed plus 13 subtests, Ruff/mypy/wheel smoke/`git diff --check` passed; no commit made.
  - Debt Friction: none identified.

- 2026-07-15T09:40:34Z Plan feedback addressed by `/openspec-story-plan-resume`
  - Original plan review entry: 2026-07-15T09:36:29Z
  - Sections edited: story.md (Scenarios / Behavior Examples, Acceptance, Fail-open Checks, Input Boundary Shape Risk, Surface / Branch Proof Matrix, Risk Lens Inventory, Design Element Trace, Test Architecture Plan, Acceptance Proof Matrix, Plan Review Log); tasks.md (TAP-07 and latest remediation)
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Changes: narrowed S2 to A5 scanner semantics and S4 to A2 public failure propagation; added S8/A3 normalization, S9/A12 reconcile fail-hard, and S10/A11 install scenarios; repaired each required design trace to one Scenario -> Acceptance -> Verification chain; added provisional acceptance-backed TAP-07 proof for reconcile exception propagation, failed-run observability, and no successful final-review acceptance; narrowed TAP-05 to deterministic package happy-path ownership and aligned Fail-open Checks/APM proof boundaries.
  - Debt Friction: none identified.

- 2026-07-15T09:48:15Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED
  - Status transition: unchanged: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `openspec/initiatives/simple-pr-context/initiative.md`; GitHub PR #28 (`https://github.com/grzegorznowak/CURe/pull/28`); historical branch `cure-subsequent-pr-review/story-01-intake`; related commits `db56509`, `e0f9813`, `cc4893f`, `e0555bf`; no Jira/ticket anchor found
  - Traceability: forward complete; backward complete
  - Design trace: complete
  - Code surfaces searched: `cure.py::_pr_flow_impl`, `_resume_flow_impl`, `_reconcile_prior_context`, `SessionProgress.error`; `cure_flows.py::render_prompt`; `cure_github.py`; `cure_pr_context/{__init__,fetcher,corpus,orient}.py`; `cure_output.py`; `cure_sessions.py`; `paths.py`; `pyproject.toml`; built-in `prompts/mrereview_gh_local*.md`; `tests/cure_pr_context/`; `tests/test_cure_pr_flow.py`; historical branch GitHub/corpus owners
  - Risk lenses reviewed: GitHub/subprocess external I/O and array shape; filesystem sessions/generated artifacts; prompt substitution and LLM fail-hard behavior; fresh/resumed/singlepass branch routing; packaging/installability; cache/persistence and UI/TUI explicitly excluded
  - Evidence quality: confirmed current artifacts, live source/test owners, PR #28 intent, path ownership, and structural matrices; inferred none material; unknown no separate ticket beyond PR #28 and initiative; provisional A5/TAP-03 scanner-prompt proof, A8/TAP-07 resume substitution proof, and A12/TAP-07 reconcile-failure proof are explicitly bounded with implementation actions
  - Finding closure: prior scenario-funnel, reconcile fail-hard, and TAP-05 overclaim gaps are closed by S2/S4/S8-S10 single-cover links, A12 plus TAP-07/APM observability, and TAP-05's explicit happy-path exclusions; the surface, fail-open, input-boundary, risk, design-trace, TAP, and APM sections agree, and structural validation plus `git diff --check` found no plan-side regression
  - Key findings:
    - No blocking findings; all 10 normative scenarios have exactly one acceptance link, A1-A12 each have an APM row, and required design elements trace through scenario, acceptance, and TAP proof.
    - A5, A8, and A12 remain correctly provisional with concrete owners, fixtures, observability, and open implementation details; provisional implementation evidence does not weaken plan readiness.
    - Contract review ran on a dirty in-progress worktree (11 tracked modified files); implementation completeness and runtime proof were intentionally not assessed.
  - Hypothesis triage: none
  - Debt Friction: none
  - Next action: `/openspec-story-resume simple-pr-context simple-pr-context` from a fresh session
