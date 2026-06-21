Plan: 🟢 PLAN APPROVED
Status: ✅ DONE

## Purpose

`cure pr` currently reviews PRs blind to discussion history — it sees only the PR description and the diff. This change adds a `cure_pr_context` package that fetches all PR discussion (comments, reviews, review comments) and past CURe reviews, deduplicates them, and runs a single LLM orientation scan. The resulting structured brief is injected as `$PRIOR_CONTEXT` into the synthesis-level review prompts (normal singlepass, big singlepass, and multipass synth), guiding the review agent toward unresolved problem areas and away from already-addressed ones. Multipass plan and step templates intentionally exclude `$PRIOR_CONTEXT` — they are independent review passes. The feature runs automatically on `cure pr` review runs with no operator flags required.

## Actors

- **Primary:** CURe operator running `cure pr` — receives reviews informed by discussion context without additional flags
- **Secondary:** Review agent (LLM) — consumes `$PRIOR_CONTEXT` as orientation guidance
- **Affected:** PR author / reviewers — their past comments and reviews now influence future automated reviews
- **Reviewer:** CURe maintainer — verifies that the package does not break the existing flow and that tests pass

## Triggering Need

The `cure-subsequent-pr-review` initiative (38 commits) built an 18-file pipeline that turned out to be over-engineering for the real problem. Users reported that what they need is simple orientation about the PR discussion, not a multi-stage classification and verification system. This story implements the simplified version from scratch, porting only the reusable code from the old branch.

## Expected Prerequisites

None. This is the first and only story of the initiative. The old branch `cure-subsequent-pr-review/story-01-intake` is a historical reference, not a live prerequisite.

## Scope

- Create `cure_pr_context/` package with 4 files: `__init__.py`, `fetcher.py`, `corpus.py`, `orient.py`
- Register `cure_pr_context` in `pyproject.toml` so installs/wheels include the package
- Add list-capable `gh_api_list`/`gh_fetch` in `cure.py`; do not reuse `gh_api_json` for endpoints that return arrays
- `fetch_pr_discussion()`: 3 GitHub endpoints → flat dicts
- `find_past_reviews(..., head_sha)`: local sessions under `sandbox_root` + current remote CURe footers + head compatibility + Jaccard dedup
- `build_orientation_brief()`: LLM scan → fixed sections with inline instructions
- `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)`: orchestration, returns dict with `orientation_brief`, `discussion`, `past_reviews`, `meta`; `discussion` already comes without events duplicated against `past_reviews`
- Inject call in `cure.py::_pr_flow_impl` after `compute_pr_stats`, passing effective `head_sha`
- `$PRIOR_CONTEXT` in the 3 synthesis-level templates: normal singlepass, big singlepass, multipass synth. Plan and step templates intentionally exclude `$PRIOR_CONTEXT` — they are independent review passes. Context is reconciled only at synthesis time following a 3-phase protocol: (1) independent review, (2) context cross-check, (3) final synthesis where code evidence wins over context claims.
- Debug artifacts: `work/pr_context_discussion.json`, `work/pr_context_past_reviews.json`
- Unit tests + integration with deterministic fixtures
- Fail hard on any error

## Out of Scope

- Cache or persistent storage
- New CLI flags
- Changes in `cure_flows.py` beyond the template variable `$PRIOR_CONTEXT`
- UI/TUI changes
- Truncation of long discussion
- Separate model for the scan (uses the same LLM as the review)
- Guaranteeing that custom prompts (`--prompt` / `--prompt-file`) contain `$PRIOR_CONTEXT`; the safe `extra_vars` can be available, but user templates are the operator's responsibility
- Follow-up/resume templates that are not part of the new `cure pr` review prompt path

## Scenarios / Behavior Examples

### S1 — Baseline: PR with no discussion or past reviews
- Given: new PR, 0 comments, 0 reviews, 0 prior local sessions
- When: `cure pr` runs
- Then: `build_pr_context()` returns `orientation_brief = ""`. `extra_vars["PRIOR_CONTEXT"]` is passed as `""` and `render_prompt` replaces `$PRIOR_CONTEXT` without leaving raw tokens. The review runs semantically as it does today.
- Covers: A6

### S2 — PR with active discussion, no past CURe reviews
- Given: PR with 15 comments from 3 authors, 2 reviews (CHANGES_REQUESTED + APPROVED), 8 inline review comments. No prior local sessions.
- When: `cure pr` runs
- Then: `$PRIOR_CONTEXT` contains a briefing based on the 25 events. Sections "Problem areas" and "Pending issues" reflect the review comments that requested changes. Section "Resolved areas" reflects threads marked as resolved.
- Covers: A5

### S3 — PR with past CURe review (local session + remote footer), dedup
- Given: PR with one prior CURe review (local session + comment/review body with official CURe footer). The CURe footer also appears as a comment in the discussion. 5 other normal comments.
- When: `cure pr` runs
- Then: The CURe footer is detected as a past review. The past review is the retained side: the duplicate comment is removed from `discussion` output/debug/LLM input (the past review + the 5 normal comments remain). `meta.n_deduped = 1`.
- Covers: A4

### S4 — Error: GitHub API fails
- Given: PR without access to the GitHub API (no connection, or invalid token)
- When: `cure pr` runs
- Then: `build_pr_context()` raises an exception. The review aborts with an error message. No partial debug artifacts are created.
- Covers: A2

### S5 — Multipass synth receives `$PRIOR_CONTEXT` (plan and steps do not)
- Given: large PR that triggers the `big` profile and multipass is enabled
- When: `cure pr` runs in multipass mode
- Then: The plan and each step are executed WITHOUT `$PRIOR_CONTEXT` — they are independent review passes. The multipass synth prompt receives `$PRIOR_CONTEXT` and reconciles it against step findings following the 3-phase protocol.
- Covers: A8

### S6 — Big singlepass review receives `$PRIOR_CONTEXT`
- Given: large PR that triggers the `big` profile, but multipass is disabled by config or CLI
- When: `cure pr` runs in singlepass mode with `prompts/mrereview_gh_local_big.md`
- Then: The big singlepass prompt contains `$PRIOR_CONTEXT` with the same orientation brief or safe `""`
- Covers: A8

## Acceptance

- **A1:** `cure_pr_context/` package exists with 4 files: `__init__.py`, `fetcher.py`, `corpus.py`, `orient.py`
- **A2:** `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)` returns a dict with keys `orientation_brief`, `discussion`, `past_reviews`, `meta`, or raises an exception on error; `head_sha` is the current PR/review SHA for verifying remote footer compatibility; `gh_fetch` is list-capable (`gh_api_list`/bound callable), not `gh_api_json`
- **A3:** `fetch_pr_discussion()` calls 3 GitHub endpoints via `gh_fetch` and returns a list of flat dicts with keys `kind`, `author`, `body`, `created_at`, `url`, `path`, `line`, `review_state`
- **A4:** `find_past_reviews()` detects local sessions (`review.md`) under `sandbox_root` and official remote CURe footers (in issue comments and review bodies) delimited by `CURE_REVIEW_FOOTER_START` / `CURE_REVIEW_FOOTER_END` with token `sha <short>`, verifies compatibility by prefix against `head_sha` when footer and head are known, and deduplicates vs discussion with Jaccard ≥ 0.85 retaining `past_reviews` and removing duplicate events from `discussion`
- **A5:** `build_orientation_brief()` produces a string with fixed sections (Resolved areas, Problem areas, Pending issues, Repeated patterns, Decisions made) and inline usage instructions
- **A6:** When there is no discussion or past reviews, `orientation_brief` is `""` and `PRIOR_CONTEXT` is still added to `extra_vars` as `""`; no raw `$PRIOR_CONTEXT` remains in rendered prompts
- **A7:** `build_pr_context()` is called from `_pr_flow_impl` after `compute_pr_stats`, before the final multipass/singlepass decision, and receives effective `head_sha` (`review_head_sha` if it exists, otherwise PR API `head_sha`)
- **A8:** `$PRIOR_CONTEXT` appears in the 3 synthesis-level templates: normal singlepass, big singlepass, multipass synth. Multipass plan and step templates intentionally exclude `$PRIOR_CONTEXT` so all steps are independent review passes. Context reconciliation happens at synthesis time following a 3-phase protocol: independent review first, context cross-check second, final synthesis third where code evidence wins over context claims. Custom prompts and follow-up/resume templates are explicitly excluded.
- **A9:** Debug artifacts `work/pr_context_discussion.json` (pruned discussion) and `work/pr_context_past_reviews.json` (retained past reviews) are written even when `orientation_brief` is `""` (as long as there is data)
- **A10:** Unit tests per module (`fetcher`, `corpus`, `orient`) + end-to-end integration test with deterministic fixtures
- **A11:** `pyproject.toml` includes `cure_pr_context` in the explicit setuptools metadata and an install/wheel smoke can import `cure_pr_context`

## Verification

### Fail-open Checks

#### Prompt/template substitution (risk lens: prompt/template substitution)

- **No raw `$PRIOR_CONTEXT` tokens leak:** `render_prompt` (`cure_flows.py:1437`) replaces `$KEY` and `${KEY}` only for values present in `extra_vars`. When `PRIOR_CONTEXT` is missing, the literal `$PRIOR_CONTEXT` remains. The implementation must always add `extra_vars["PRIOR_CONTEXT"]` (either `""` or content), making the missing-var path dead for built-in review prompts. TAP-06/TAP-07 verify.
- **Empty-string path (baseline):** When `orientation_brief == ""`, `extra_vars["PRIOR_CONTEXT"] = ""`. `render_prompt` replaces `$PRIOR_CONTEXT` with `""` — the agent sees a blank line or nothing. Template rendering completion is semantically identical to current behavior. TAP-06 covers.
- **Enabled path (activation):** When `orientation_brief` is non-empty, `extra_vars["PRIOR_CONTEXT"]` contains the full orientation brief. `render_prompt` substitutes it in the 3 synthesis templates. The agent sees the structured brief during reconciliation (Phase 2), after completing an independent review (Phase 1). TAP-06/TAP-07 cover.
- **Degraded path (API/LLM failure):** `build_pr_context()` raises, the review aborts before prompt rendering. No partial `$PRIOR_CONTEXT` is ever rendered. TAP-04 and TAP-05 verify fail-hard behavior.

### Input Boundary Shape Risk

| Boundary | Source shape | Strict assumption / risk | Required mitigation | Proof |
|----------|--------------|--------------------------|---------------------|-------|
| GitHub discussion endpoints | JSON arrays from comments/reviews/review-comments endpoints | Existing `gh_api_json` rejects non-dict payloads | Add/port `gh_api_list`; `fetch_pr_discussion` accepts only list-capable `gh_fetch` and normalizes arrays | TAP-01, TAP-04, TAP-05 |
| PR metadata endpoint | JSON object | Existing `gh_api_json` remains appropriate for PR metadata | Do not replace metadata fetch with list helper | TAP-07 code review |
| Local prior sessions | Directories under `sandbox_root` / `~/.local/state/cure/sandboxes` | A nonexistent `sessions_root` would miss completed sessions | Pass the real `sandbox_root` into `find_past_reviews` | TAP-02, TAP-04 |
| Remote CURe footers | Markdown bodies with current official footer block and `sha <short>` token | Old `CURe-pr-footer reviewed_head=` contract would miss live footers; no current head signal would make compatibility unprovable | Parse `CURE_REVIEW_FOOTER_START`/`END`, `sha`, and `session` metadata; pass current `head_sha` from `_pr_flow_impl` and compare by prefix when both values are known | TAP-02, TAP-05, TAP-07 |
| Prompt templates | Missing `extra_vars` key leaves raw `$PRIOR_CONTEXT` | Fail-open raw token leak | Always pass `PRIOR_CONTEXT` as `""` or brief | TAP-06, TAP-07 |
| Packaging metadata | Explicit setuptools package list | New package omitted from installs | Add `cure_pr_context` to `pyproject.toml` and run import smoke | TAP-09 |

### Surface / Branch Proof Matrix

| Surface / branch | In scope? | `$PRIOR_CONTEXT` obligation | Proof |
|------------------|-----------|-----------------------------|-------|
| Normal singlepass built-in review (`prompts/mrereview_gh_local.md`) | Yes | Template contains `$PRIOR_CONTEXT` with 3-phase guardrails; render uses always-present `extra_vars["PRIOR_CONTEXT"]` | TAP-06, TAP-07 |
| Big singlepass built-in review (`prompts/mrereview_gh_local_big.md`) | Yes | Same as normal singlepass, including when multipass is disabled | TAP-06, TAP-07 |
| Multipass plan (`prompts/mrereview_gh_local_big_plan.md`) | Yes, without `$PRIOR_CONTEXT` | Independent review pass — plan template intentionally excludes `$PRIOR_CONTEXT` | TAP-07 code review |
| Multipass step (`prompts/mrereview_gh_local_big_step.md`) | Yes, without `$PRIOR_CONTEXT` | Independent review pass — step template intentionally excludes `$PRIOR_CONTEXT` | TAP-07 code review, TAP-06 negative proof |
| Multipass synth (`prompts/mrereview_gh_local_big_synth.md`) | Yes | Synth template contains `$PRIOR_CONTEXT`; reconciles independent step findings with context | TAP-06, TAP-07 |
| Custom prompt files / inline prompts | No template insertion guarantee | If a user includes `$PRIOR_CONTEXT`, safe `extra_vars` can substitute it; user-owned text is out of scope | Explicit exclusion in A8 |
| Follow-up/resume templates | No | Not part of this story's new `cure pr` review prompt path | Explicit exclusion in A8 |

### Risk Lens Inventory

| Risk lens | Activated? | Coverage / exclusion |
|-----------|------------|----------------------|
| External services / subprocess I/O | Yes | GitHub API helper and failure paths covered by TAP-01/TAP-04/TAP-05 |
| Filesystem / generated artifacts | Yes | `sandbox_root` scanning and `work/pr_context_*.json` artifacts covered by TAP-02/TAP-04/TAP-05 |
| Prompt/template substitution | Yes | Fail-open Checks + TAP-06/TAP-07 |
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
| List-capable GitHub discussion fetch via `gh_fetch`/`gh_api_list` | required | S2/S4 → A2/A3 → TAP-01/TAP-04/TAP-05 |
| Real prior-review corpus sources (`sandbox_root`, official footer markers, current `head_sha`) | required | S3 → A4 → TAP-02/TAP-05/TAP-07 |
| Always-safe prompt variable substitution | required | S1/S5/S6 → A6/A8 → TAP-06/TAP-07 |
| Package installability | required | Implementation/install surface → A11 → TAP-09 |
| Custom/follow-up prompt exclusion | flexible (bounded) | A8 explicit exclusion → Surface / Branch Proof Matrix |

### Verification Commands

```bash
# Unit tests
python -m pytest tests/cure_pr_context/ -v

# Integration test (fixtures deterministas, sin GitHub real)
python -m pytest tests/cure_pr_context/test_integration.py -v

# Template + flow branch proof
python -m pytest tests/cure_pr_context/test_templates.py tests/test_cure_pr_flow.py -v

# Ruff + mypy
ruff check cure_pr_context/
mypy cure_pr_context/

# Packaging smoke (no install into repo environment)
rm -rf .tmp_package_smoke
python -m pip wheel . -w .tmp_package_smoke/wheelhouse
python -m pip install --no-deps --target .tmp_package_smoke/install .tmp_package_smoke/wheelhouse/cureview-*.whl
PYTHONPATH=.tmp_package_smoke/install python -c "import cure_pr_context"

# Full CURe test suite (ensure no regressions)
python -m pytest tests/ -x --timeout=120
```

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|--------|--------------|---------------------------|----------------------|-------------------|--------------------------|----------------------------|-------------------|---------------|------------------------|
| TAP-01 | Unit | `fetch_pr_discussion` — 3 endpoints, normalization, list-capable caller | `tests/cure_pr_context/test_fetcher.py` | GitHub API boundary (mocked `gh_fetch`/`gh_api_list`) | dict keys, event count, field types, caller paths, array handling | Mock `gh_fetch` returning list payloads per endpoint | `pytest tests/cure_pr_context/test_fetcher.py` | If mock becomes fragile, use recorded responses | One test per endpoint + failure test |
| TAP-02 | Unit | `find_past_reviews` + `deduplicate` — local sandbox sessions + remote official footers; retained side is `past_reviews`, duplicate discussion events are pruned | `tests/cure_pr_context/test_corpus.py` | Filesystem (`sandbox_root` session dirs) + in-memory discussion + current `head_sha` | past review count, footer detection, SHA/session metadata, head-SHA compatibility, retained-side/pruned-discussion, dedup count | Temporary directories with fake `review.md`; in-memory discussion events with `CURE_REVIEW_FOOTER_START/END`; compatible and incompatible footer SHA fixtures | `pytest tests/cure_pr_context/test_corpus.py` | If the session scan is slow, reduce fixtures without removing retained-side/head-SHA cases | Separate tests: local, remote, dedup/head compatibility |
| TAP-03 | Unit | `build_orientation_brief` — LLM scan with fixed sections | `tests/cure_pr_context/test_orient.py` | LLM boundary (mocked) | Output contains the 5 sections, usage instructions present | Mock `run_llm` that returns predefined brief | `pytest tests/cure_pr_context/test_orient.py` | If the format changes, update mock | One test per section + prompt construction test |
| TAP-04 | Unit | `build_pr_context` — internal integration of the 3 modules | `tests/cure_pr_context/test_init.py` | Full public API, including explicit `head_sha` parameter | Dict keys, meta values, `head_sha` propagated to corpus, fail-hard on errors, debug artifact paths, `PRIOR_CONTEXT` empty path | `pr_stats` fixture + `head_sha` fixture + mock `gh_fetch` + mock `run_llm` + tmp sandbox/work dirs | `pytest tests/cure_pr_context/test_init.py` | Convert to real integration if mock becomes fragile | Covers A2, A6, A7 |
| TAP-05 | Integration | End-to-end pipeline with deterministic fixtures | `tests/cure_pr_context/test_integration.py` | End-to-end: fetch → corpus/head-SHA check → retained-side dedup → orient → build | A1-A10 verifiable without real GitHub, including pruned discussion output and retained past review | JSON fixtures for the 3 API responses; compatible/incompatible footer SHA bodies; mock LLM; tmp sandbox dirs | `pytest tests/cure_pr_context/test_integration.py` | Add more scenarios if they fail live | Covers all S1-S5 with fixtures |
| TAP-06 | Integration | `$PRIOR_CONTEXT` present and rendered in 3 synthesis templates, absent from plan/step | `tests/cure_pr_context/test_templates.py` | `render_prompt` with `extra_vars` | `$PRIOR_CONTEXT` correctly replaced with brief and with `""` in 3 synthesis templates; token absent from plan/step templates | Real built-in templates, `extra_vars` always with `PRIOR_CONTEXT` for synthesis paths | `pytest tests/cure_pr_context/test_templates.py` | If templates move, update paths | Covers A6, A8 |
| TAP-07 | Integration | `cure.py` calls `build_pr_context` at the correct point and propagates extra vars; prior context excluded from step entries | `tests/test_cure_pr_flow.py` | `_pr_flow_impl` flow + multipass step helper | Runtime test monkeypatches `compute_pr_stats` and `build_pr_context` and stops after render, proving call order, effective `review_head_sha`, and rendered `PRIOR_CONTEXT` in synthesis paths; step helper test proves prior context is excluded from step entries | Mock `build_pr_context`, synthetic PR URL, prompt-profile/multipass branch fixtures | `pytest tests/test_cure_pr_flow.py` | Helper seams/monkeypatch cover the flow without a nonexistent generic `--dry-run` (only `--dry-run-chunkhound` exists) | Covers A7, A8 |
| TAP-08 | Lint/Type | Ruff formatting + mypy type checking | `cure_pr_context/` | Style and types | Ruff clean, mypy clean | N/A | `ruff check cure_pr_context/ && mypy cure_pr_context/` | N/A | Quality |
| TAP-09 | Packaging | Installed package contains/imports `cure_pr_context` | `pyproject.toml` + packaging smoke command | setuptools explicit package list / wheel install | `pyproject.toml` includes `cure_pr_context`; `python -c "import cure_pr_context"` succeeds from wheel target | Local wheel built into `.tmp_package_smoke/` | packaging smoke commands above | If wheel tooling unavailable, `pip install -e .` smoke in disposable env | Covers A11 |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|--------------|---------------|-------------|-----------------|------------------|------------------|-------------|
| A1 | final | `ls cure_pr_context/` + TAP-05 | Verify 4 files and run tests | File listing, tests pass | `cure_pr_context/` | — |
| A2 | final | TAP-04 + TAP-05 | Run tests, review signature | Tests pass, dict keys verified, signature includes `head_sha`, list-capable `gh_fetch` used | `__init__.py`, `cure.py` | — |
| A3 | final | TAP-01 | Run tests + review code | Fetch tests pass, 3 mock calls verified | `fetcher.py` | — |
| A4 | final | TAP-02 | Run tests | Corpus tests pass, `sandbox_root` and official footer verified, `head_sha` compatibility tested, `past_reviews` retained and duplicate discussion pruned with fixtures | `corpus.py`, `cure_sessions.py`, `cure_output.py`, `cure.py` | — |
| A5 | final | TAP-03 | Run tests | Mocked LLM output contains sections and instructions | `orient.py` | — |
| A6 | final | TAP-04 + TAP-06 | Run tests | `orientation_brief=""` → `PRIOR_CONTEXT` is `""` and no raw `$PRIOR_CONTEXT` remains | `__init__.py`, templates, `cure_flows.py` | — |
| A7 | final | TAP-07 | Run flow tests + code review | Runtime mocked `_pr_flow_impl` proof shows `build_pr_context` called after `compute_pr_stats`, before prompt render, with effective `review_head_sha`; prompt receives rendered `PRIOR_CONTEXT` | `cure.py`, `tests/test_cure_pr_flow.py` | — |
| A8 | final | TAP-06 + TAP-07 + Surface / Branch Proof Matrix | Run tests + review templates | 3 synthesis templates contain `$PRIOR_CONTEXT`; plan/step templates intentionally exclude it; custom/follow-up exclusions documented | templates, `cure.py` | — |
| A9 | final | TAP-04 + TAP-05 | Run tests, verify written files | `work/pr_context_discussion.json` exists with pruned discussion and `work/pr_context_past_reviews.json` exists with retained past reviews | `__init__.py`, `work/` | — |
| A10 | final | TAP-01..TAP-05 | Run `pytest tests/cure_pr_context/` | All tests pass, coverage ≥ 80% | `tests/cure_pr_context/` | — |
| A11 | final | TAP-09 | Review `pyproject.toml`, run smoke | Package included in wheel/install and importable | `pyproject.toml`, wheel smoke | — |

## Critical Files

**New:**
| Path | Role |
|------|------|
| `cure_pr_context/__init__.py` (new) | Public API `build_pr_context(..., head_sha, ...)`, module orchestration |
| `cure_pr_context/fetcher.py` (new) | `fetch_pr_discussion()` — 3 GitHub endpoints via `gh_fetch`/`gh_api_list` |
| `cure_pr_context/corpus.py` (new) | `find_past_reviews(..., head_sha)` + Jaccard dedup, using `sandbox_root`, official CURe footers, head compatibility by prefix, and duplicate discussion pruning |
| `cure_pr_context/orient.py` (new) | `build_orientation_brief()` — LLM scan |
| `tests/cure_pr_context/test_fetcher.py` (new) | Unit tests fetcher |
| `tests/cure_pr_context/test_corpus.py` (new) | Unit tests corpus |
| `tests/cure_pr_context/test_orient.py` (new) | Unit tests orient |
| `tests/cure_pr_context/test_init.py` (new) | Unit tests `build_pr_context` |
| `tests/cure_pr_context/test_integration.py` (new) | Integration end-to-end |
| `tests/cure_pr_context/test_templates.py` (new) | Template variable injection |

**Modified:**
| Path | Role |
|------|------|
| `pyproject.toml` | Add `cure_pr_context` to explicit `packages` and enable packaging smoke |
| `cure.py` | Insert `build_pr_context()` call after `compute_pr_stats`, pass effective `head_sha`, always inject `$PRIOR_CONTEXT` in `extra_vars`, add `gh_api_list` helper |
| `prompts/mrereview_gh_local.md` | Add `$PRIOR_CONTEXT` (normal singlepass) |
| `prompts/mrereview_gh_local_big.md` | Add `$PRIOR_CONTEXT` (big singlepass when multipass is disabled) |
| `prompts/mrereview_gh_local_big_plan.md` | Intentionally excludes `$PRIOR_CONTEXT` (independent review pass) |
| `prompts/mrereview_gh_local_big_step.md` | Intentionally excludes `$PRIOR_CONTEXT` (independent review pass) |
| `prompts/mrereview_gh_local_big_synth.md` | Add `$PRIOR_CONTEXT` (multipass synth) |

**Reference (read-only):**
| Path | Role |
|------|------|
| `cure_subsequent_review/github_history.py` (old branch) | Port fetch/list helper logic as orientation |
| `cure_subsequent_review/prior_corpus.py` (old branch) | Port official footer detection and session scan as orientation |

## Implementation Notes

**Implementation order (dependencies):**
1. `cure.py::gh_api_list` — port/adapt list-capable helper before implementing live fetcher
2. `fetcher.py` — uses `gh_fetch`, has no internal dependencies, testable in isolation
3. `corpus.py` — depends on `fetcher` to receive discussion events; uses `sandbox_root`, effective `head_sha`, and current official footers
4. `orient.py` — depends on `fetcher` + `corpus` to receive data → LLM
5. `__init__.py` — integrates the 3, orchestrates `build_pr_context(..., head_sha, ...)`, and writes deduplicated debug artifacts in `work_dir`
6. `pyproject.toml` — add `cure_pr_context` to the explicit package list
7. Templates — add `$PRIOR_CONTEXT` to the 3 synthesis templates and 3-phase guardrails to all 5 templates (parallel to 1-6)
8. `cure.py` — inject the call and pass effective `head_sha` (last, once the package is ready)

**Smallest red-first seam:** `fetcher.py` with mock `gh_fetch`/`gh_api_list` that returns arrays.

**Phases:**
- Phase 0: `gh_api_list` + packaging metadata smoke (TAP-09 setup)
- Phase 1: `fetcher.py` + tests (TAP-01) — RED → GREEN
- Phase 2: `corpus.py` + tests (TAP-02) — RED → GREEN
- Phase 3: `orient.py` + tests (TAP-03) — RED → GREEN
- Phase 4: `__init__.py` + tests (TAP-04) — RED → GREEN
- Phase 5: Integration + 5 templates + `cure.py` (TAP-05, TAP-06, TAP-07)
- Phase 6: Ruff + mypy clean (TAP-08), packaging smoke (TAP-09), full test suite

**Constraints:**
- The old `github_history.py` uses a `DiscussionEvent` dataclass with 15 fields; simplify to dicts with 6-8 keys
- The old `prior_corpus.py` has already-tested footer detection logic, but the normative source is the current CURe footer (`CURE_REVIEW_FOOTER_START/END` + `sha <short>`)
- `render_prompt` in `cure_flows.py:1437` already supports `extra_vars` — no changes required, but `PRIOR_CONTEXT` must always be present in `extra_vars`

## Locked Decisions

A single `cure_pr_context/` package with 4 files. The public API is `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm) -> dict`; `sandbox_root` is the real root of completed sandboxes/sessions (`paths.sandbox_root`), `work_dir` is the current session's `work/` directory for debug artifacts, `pr_stats` is the result already computed by `compute_pr_stats`, `head_sha` is the effective PR/review SHA that `_pr_flow_impl` passes explicitly for remote footer compatibility, and `gh_fetch` is a list-capable callable based on `gh_api_list` (not `gh_api_json`). The brief is produced by a single LLM scan with fixed sections and inline usage instructions; it is injected as `$PRIOR_CONTEXT` into the 3 synthesis templates (normal singlepass, big singlepass, multipass synth). Multipass plan and step templates intentionally exclude `$PRIOR_CONTEXT` — they are independent review passes. `PRIOR_CONTEXT` is always passed in `extra_vars` as `""` or content to avoid raw token leaks; plan/step templates simply have no `$PRIOR_CONTEXT` token to substitute. The 3-phase review protocol is embedded in all 5 templates: (1) independent review, (2) context reconciliation, (3) final synthesis where code evidence wins over context claims. Past-review deduplication uses char n-grams + Jaccard with no external dependencies; `past_reviews` is the retained side and duplicate events are removed from the returned/written/LLM-passed `discussion`. The LLM is received as a `Callable` injected from `cure.py`. Any error aborts the review. No cache, no new CLI flags, no changes to `cure_flows.py`.

## Discovery Notes

- The old `github_history.py` in `cure-subsequent-pr-review/story-01-intake` has ~300 lines. `collect_pr_discussion()` uses `gh_api_list` (not `gh_api_json`) for the 3 endpoints because GitHub returns arrays. Pagination handling is in `PaginationMarker`.
- The existing `gh_api_json` (`cure.py:7401-7418`) validates `isinstance(payload, dict)` and fails with arrays. The 3 discussion APIs return arrays. Must create/port `gh_api_list` using the pattern from the old branch (`cure.py:7613-7634` in `cure-subsequent-pr-review/story-01-intake`): `gh api --paginate [--slurp]`, fallback without `--slurp`, page flattening.
- `render_prompt` in `cure_flows.py:1437-1491` supports `extra_vars: dict[str, str]`, but only replaces present keys; if `PRIOR_CONTEXT` is missing, `$PRIOR_CONTEXT` remains literal.
- `_pr_flow_impl` in `cure.py:9334` resolves `head_sha` from the PR API (`cure.py:9371-9375`), `review_head_sha` from the local checkout (`cure.py:9730-9734`), and computes `pr_stats` in `compute_pr_stats` (`cure.py:4162`). The injection point in `_pr_flow_impl` is after `progress.flush()` in `detect_pr_size` (~`cure.py:9754-9767`), before final singlepass/multipass selection/routing; it must pass `review_head_sha or head_sha` as effective `head_sha` to `build_pr_context()`.
- CURe writes current review footers as a block `<!-- CURE_REVIEW_FOOTER_START -->` / `<!-- CURE_REVIEW_FOOTER_END -->` with a line that includes `· sha <short>` (`cure_output.py:22`, `cure_output.py:1547-1549`). Do not use the old hypothetical format `CURe-pr-footer reviewed_head=`.
- `scan_completed_sessions_for_pr` receives `sandbox_root` (`cure_sessions.py:954-980`) and the defaults live in `paths.py` as `~/.local/state/cure/sandboxes` (`paths.py:37-38`, `paths.py:75-77`). Do not design a separate `sessions_root`.
- The built-in review templates are in `prompts/`: `mrereview_gh_local.md` (normal singlepass), `mrereview_gh_local_big.md` (big singlepass), `mrereview_gh_local_big_plan.md`, `_big_step.md`, `_big_synth.md`.
- Live code can use big singlepass when the resolved profile is `big` and multipass is disabled (`cure.py:9847-9867`); `prompt_template_name_for_profile` returns `mrereview_gh_local_big.md` for the `big` profile (`cure.py:4240`).
- `pyproject.toml:16-18` uses explicit setuptools lists (`py-modules = [...]`, `packages = ["prompts"]`), so `cure_pr_context` must be added explicitly to `packages`.
- `write_pr_context_file` in `cure.py` already writes to `work/pr_context.json` — follow that pattern for the debug artifacts.
- `PullRequestRef` (`cure.py:2953-2962`) does not contain SHA, and `compute_pr_stats` (`cure.py:4162-4197`) returns `head_ref` but not SHA; therefore `head_sha` must be an explicit parameter of `build_pr_context()` instead of being inferred from `pr` or `pr_stats`.
- Live CLI does not have a generic `--dry-run` for `cure pr`; the related flag is `--dry-run-chunkhound` (`cure.py:14882`). TAP-07 must use monkeypatch/helper seams if it needs a fallback without running a real review.

## Implementation Log

- 2026-06-20T08:20:00Z Story claimed and implemented in worktree `/home/vscode/add-worktrees/CURe-simple-pr-context-impl`.
  - Added `cure_pr_context` package (`fetcher`, `corpus`, `orient`, public `build_pr_context`) and setuptools package metadata.
  - Added `cure.py::gh_api_list`, `_pr_flow_impl` context build phase after `compute_pr_stats`, effective `head_sha=review_head_sha or head_sha`, and always-present `PRIOR_CONTEXT` prompt vars for singlepass and multipass synth; plan and step entries intentionally exclude prior context.
  - Added `$PRIOR_CONTEXT` to the 3 synthesis templates (normal singlepass, big singlepass, multipass synth); plan and step templates exclude it.
  - Verification passed: `python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q` (15 passed), `python -m pytest tests/test_reviewflow_unittest.py -q` (433 passed, 13 subtests), `python -m pytest tests/ -q` (635 passed, 13 subtests), `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py tests/_reviewflow_unittest_grounding_impl.py`, `mypy cure_pr_context`, and wheel/install import smoke.

- 2026-06-20T17:45:00Z Story resumed after implementation review request-changes.
  - Fixed A4 remote footer trust: `parse_footer_metadata()` now requires a valid non-empty `sha` token inside official footer markers before an event can become a past review; added marker-only footer regression coverage.
  - Fixed fail-hard local session handling: corpus scan validates local `meta.json` parseability/object shape before delegating to `scan_completed_sessions_for_pr`, so corrupt session metadata aborts PR context build.
  - Fixed TAP-07 proof maturity: added a runtime `_pr_flow_impl` monkeypatch test proving `compute_pr_stats` -> `build_pr_context` order, effective `review_head_sha` propagation, and rendered `PRIOR_CONTEXT`; A7 proof row is final.
  - Fixed meta shape: `build_pr_context().meta` now includes `n_comments`, `n_reviews`, and `n_review_comments` alongside aggregate counts; unit/integration tests assert the split.
  - Verification passed: `python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q` (18 passed), `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py`, and `mypy cure_pr_context`.

## Plan Review Log

- 2026-06-20T06:57:37Z Plan feedback addressed and log compressed by `/openspec-story-plan-resume`
  - Original plan review entries: 2026-06-20T00:00:00Z, 2026-06-20T06:38:04Z, 2026-06-20T06:54:21Z
  - Sections edited: story.md (Scope, Scenarios, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes), proposal.md, design.md, tasks.md, initiative.md
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Changes: normalized discussion fetching to list-capable `gh_fetch`/`gh_api_list`; kept `PRIOR_CONTEXT` always present in `extra_vars`, injected into 3 synthesis templates (plan and step intentionally exclude it); clarified dedup ownership so `past_reviews` is retained and duplicate discussion events are pruned from output/debug/LLM input; added explicit `head_sha` to `build_pr_context()` and `_pr_flow_impl` wiring for remote footer compatibility; updated TAP-02/TAP-05/TAP-07 proof obligations and replaced the nonexistent generic `--dry-run` fallback with helper/monkeypatch seams; refreshed initiative-level decisions from the old `sessions_root`/`gh_api_json`/4-template contract.
  - Evidence anchors preserved: `cure.py:7401-7418` (`gh_api_json` dict-only), `cure.py:2953-2962` (`PullRequestRef` has no SHA), `cure.py:4162-4197` (`compute_pr_stats` has no SHA), `cure.py:9371-9375` + `cure.py:9730-9734` (`head_sha`/`review_head_sha` available in `_pr_flow_impl`), `cure.py:4240`/`cure.py:9847-9867` (big singlepass), `cure.py:14882` (`--dry-run-chunkhound` only), `cure_flows.py:1437-1491` (extra-vars replacement only for present keys), `cure_output.py:22`/`cure_output.py:1547-1549` (current footer markers), `cure_sessions.py:954-980` and `paths.py:37-38,75-77` (`sandbox_root`), `pyproject.toml:16-18` (explicit packages list).

- 2026-06-20T07:09:45Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative `openspec/initiatives/simple-pr-context/initiative.md`; old branch `cure-subsequent-pr-review/story-01-intake` snippets for `gh_api_list`, `collect_pr_discussion`, and `prior_corpus`; no GitHub/Jira ticket anchor found
  - Traceability: forward complete; backward complete
  - Design trace: complete
  - Code surfaces searched: `cure.py`, `cure_flows.py`, `cure_output.py`, `cure_sessions.py`, `paths.py`, `pyproject.toml`, `prompts/mrereview_gh_local*.md`, `tests/`, old branch `cure_subsequent_review/{github_history.py,prior_corpus.py}`
  - Risk lenses reviewed: external GitHub/subprocess I/O, filesystem/generated artifacts, prompt/template substitution, packaging/install, LLM scan boundary; persistence/cache and UI/TUI excluded by scope
  - Evidence quality: confirmed live source anchors and scaffold shape; inferred none material; unknown no external ticket beyond the recorded old branch reference; provisional A7 live-PR proof remains bounded to implementation review
  - Finding closure: prior plan blockers verified addressed in the active contract (`gh_fetch` list-capable, explicit `head_sha`, retained-side dedup, five-template prompt coverage, TAP-07 helper/monkeypatch fallback)
  - Key findings:
    - No blocking findings. Acceptance A1-A11 are atomic enough for this feature and every A-id maps to TAP/APM proof (`story.md:89-99`, `story.md:193-217`).
    - TAP-07 remains the main implementation hotspot because multipass step prompts are built through `_build_multipass_step_entries` before execution (`cure.py:6417-6451`), but the plan names the branch proof and fallback seam (`story.md:199`).
    - Non-blocking source-fit note: `cure.py` imports the live `compute_pr_stats`, `prompt_template_name_for_profile`, and `render_prompt` bindings from `cure_flows.py` (`cure.py:14712-14723`; `cure_flows.py:316`, `cure_flows.py:388`, `cure_flows.py:1437`); the plan already references `cure_flows.py` in verification/discovery, so no contract edit is required before implementation.
  - Hypothesis triage: none material after source checks
  - Debt Friction: none
  - Next action: `/openspec-story-claim simple-pr-context simple-pr-context` from a fresh session
