# Design: simple-pr-context

## Package structure

```
cure_github.py      # GitHub CLI/public API adapter: gh_api_json, gh_api_list, auth/fallback helpers

cure_pr_context/
  __init__.py   # build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)
                # → { orientation_brief, discussion, past_reviews, meta }
  fetcher.py    # fetch_pr_discussion(owner, repo, number, gh_fetch) → list[dict]
  corpus.py     # find_past_reviews(sandbox_root, pr, discussion_events, head_sha) → list[dict]
                # retains same-PR prior reviews across heads and annotates reviewed/current head metadata
                # deduplicate(past_reviews, discussion_events) → (kept_past_reviews, pruned_discussion_events, deduped_count)
  orient.py     # build_orientation_brief(discussion, past_reviews, pr_stats, run_llm) → str
```

`cure_pr_context` must be listed in `pyproject.toml` packages and `cure_github` must be listed in `py-modules` because CURe uses explicit setuptools metadata.

## Data flow

```
GitHub API arrays (3 endpoints)
        │
        ▼
  gh_api_list / gh_fetch          ──→  list[dict]  (list-capable boundary)
        │
        ▼
  fetch_pr_discussion()          ──→  list[dict]  (raw discussion events)
        │
        ▼
  find_past_reviews(..., head_sha) ─→ list[dict]  (same-PR past reviews with head metadata)
        │     ▲
        │     └── sandbox_root completed sessions + remote official footer blocks
        ▼
  deduplicate(past, discussion)  ──→  (kept_past_reviews, pruned_discussion_events, deduped_count)
        │                                    │
        │                                    ├──→  JSON → work/pr_context_discussion.json (pruned discussion)
        │                                    └──→  JSON → work/pr_context_past_reviews.json (retained past reviews)
        ▼
  build_orientation_brief()      ──→  str  (`orientation_brief`)
        │
        ├──→ singlepass with context: draft review → _reconcile_prior_context(draft, brief, run_llm) → final review
        ├──→ singlepass without context: one review call, unchanged
        └──→ multipass synth: render `$PRIOR_CONTEXT` in the shared synth prompt
               ├── fresh `_pr_flow_impl`: current orientation brief or `""`
               └── resumed `_resume_flow_impl`: persisted `work/pr_context_orientation.md` or `""`
```

## API contract

### GitHub API helper module (`cure_github.py`)

All 3 GitHub discussion endpoints return JSON **arrays**, while `gh_api_json` intentionally validates `isinstance(payload, dict)` and raises `ReviewflowError` on non-dict payloads. GitHub API subprocess/public-fallback concerns live in `cure_github.py`, which exports `gh_api_json`, `gh_api_list`, auth/fallback helpers, and decode helpers. `cure.py` imports/re-exports those names for existing call sites and tests, but new GitHub API behavior belongs in `cure_github.py`, not in the already-large CLI orchestration module.

`gh_api_list` must:
- Call `gh api --paginate [--slurp]` (retrying without `--slurp` on CLI incompatibility)
- Decode and flatten multi-page JSON arrays into a single `list[dict]`
- Raise `ReviewflowError` on subprocess, auth, invalid JSON, or unexpected non-list payload failures

The old branch `cure-subsequent-pr-review/story-01-intake` has a list-capable implementation (`cure.py:7613-7634`) that can be ported directly, then tightened to return list payloads for this use case.

```python
def build_pr_context(
    pr: object,                       # PrUrl/PullRequestRef-like object
    sandbox_root: str | Path,         # root containing completed review session dirs
    work_dir: str | Path,             # current session work/ dir for debug artifacts
    pr_stats: dict[str, Any] | None,  # existing compute_pr_stats result for scanner context
    head_sha: str | None,             # effective current PR/review head SHA for annotation metadata, not an inclusion criterion
    gh_fetch: Callable[[str], list[dict[str, Any]]],  # list-capable GitHub caller
    run_llm: Callable[[str], str],    # LLM executor for orientation scan
) -> dict[str, Any]:
    """
    Returns:
        {
            "orientation_brief": str,   # LLM-produced brief. "" when no data.
            "discussion": str | list,   # Formatted/normalized discussion after duplicate prior-review events are pruned
            "past_reviews": str | list, # Formatted/normalized retained past reviews for debug
            "meta": {
                "n_comments": int,
                "n_reviews": int,
                "n_review_comments": int,
                "n_past_reviews": int,
                "n_deduped": int,
            }
        }
    Raises on any error (GitHub API, LLM call, corrupt local sessions).
    """
```

`_pr_flow_impl` should bind the host-aware caller and the effective head near the integration point, for example:

```python
def gh_fetch(path: str) -> list[dict[str, Any]]:
    return gh_api_list(host=pr.host, path=path, allow_public_fallback=True)

effective_head_sha = review_head_sha or head_sha or None
```

`cure_github.gh_api_json` remains correct for PR metadata/object endpoints and must not be reused for discussion arrays. `head_sha` is passed explicitly because `PullRequestRef` and `compute_pr_stats` do not contain a SHA; corpus uses it to annotate prior-review head metadata, not to exclude same-PR reviews from earlier heads.

## Module design

### fetcher.py

Calls 3 GitHub endpoints via `gh_fetch` (which must be list-capable — `cure_github.gh_api_list` or a bound wrapper imported by `cure.py`):
- `repos/{owner}/{repo}/issues/{number}/comments`
- `repos/{owner}/{repo}/pulls/{number}/reviews`
- `repos/{owner}/{repo}/pulls/{number}/comments`

Returns a flat list of dicts with keys: `kind`, `author`, `body`, `created_at`, `url`, `path`, `line`, `review_state`. The three REST endpoints do not provide authoritative review-thread resolution state; adding a GraphQL/thread-resolution fetch is out of scope.

Where:
- `kind`: `"issue_comment"` | `"review"` | `"review_comment"`
- `path` / `line`: only for review comments
- `review_state`: only for reviews (`APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`, etc.)

### corpus.py

**find_past_reviews():**
1. Scan local completed session dirs under the live `sandbox_root` (the same root passed to `scan_completed_sessions_for_pr`) for completed sessions on this PR. For each session with a `review.md`, treat it as a prior review.
2. Scan issue comment bodies and PR review bodies for remote CURe footer markers using the current official block:
   - `<!-- CURE_REVIEW_FOOTER_START -->`
   - footer line containing `· sha <short>` and `· session <session-id>`
   - `<!-- CURE_REVIEW_FOOTER_END -->`
3. Verify remote footer PR number using session metadata/session id when available; footer bodies whose footer/session metadata indicates a different PR are not past reviews and remain ordinary discussion events. When both current `head_sha` and footer `sha` are known, record `current_head`, `reviewed_head`, and prefix-based match status, but do not exclude same-PR reviews solely because the reviewed head differs.
4. Do not trust author — any comment/review body with a valid official footer and same-PR metadata is a past CURe review regardless of who posted it.
5. Ignore inline review comments for remote footer provenance; they remain discussion events unless separately pruned as duplicates of a retained past review.

**deduplicate():**
- First collapse duplicate local/remote representations of the same completed review to one `past_reviews` entry, using shared session identity or identical normalized review content after removing the official footer block; preserve the first retained representation.
- For each retained past review and discussion event, normalize body (remove the official footer block, lowercase, collapse whitespace) and compute character 3-grams.
- If Jaccard(past_review_ngrams, discussion_ngrams) ≥ 0.85 (inclusive), mark the discussion event as duplicate of that retained past review.
- Return `(kept_past_reviews, pruned_discussion_events, deduped_count)`; `deduped_count` counts pruned discussion events, not collapsed source representations.
- Retained side is always `past_reviews`; duplicate events are removed from the `discussion` returned by `build_pr_context()`, the debug artifact, and the LLM orientation input.

**format_past_reviews():** Convert the kept past reviews into a formatted string or JSON-safe structure for the LLM scanner and debug artifact.

### orient.py

**build_orientation_brief():**
1. Construct a prompt for the LLM with: pruned discussion events, retained past reviews, PR stats (diff size, file count).
2. Prompt instructs the LLM to produce a structured brief with fixed sections plus usage instructions for the review agent. It defines `Resolved areas` only from supplied discussion/past-review text that says an area was addressed or resolved, explicitly not from authoritative GitHub thread state.
3. The LLM output IS the orientation brief — it includes both the sections and the usage instructions inline. Normalize it by detecting actual Markdown level-2 heading lines, not arbitrary mentions of section names, and append any missing required `##` sections.
4. Returns the brief string directly. When there are zero discussion events and zero past reviews, returns `""` (empty string).

**Sections:**
- `## Resolved areas` — areas that discussion or past-review content says were addressed or resolved; this is not an authoritative GitHub thread-resolution signal
- `## Problem areas` — areas with unresolved concerns, repeated feedback, or CHANGE_REQUESTED
- `## Pending issues` — open questions or requested changes not yet addressed
- `## Repeated patterns` — cross-cutting themes in feedback (e.g., "consistently asked for more tests")
- `## Decisions made` — design decisions confirmed in prior reviews that should not be re-litigated

**Usage instructions (inline in the output):**
```
INSTRUCTIONS FOR USING PRIOR_CONTEXT:
- "Resolved areas": do not spend time re-evaluating them unless the diff touches them
- "Problem areas": prioritize them in your review plan
- "Pending issues": verify whether the diff resolved them or not
- "Repeated patterns": mention them as a cross-cutting theme if still present
- "Decisions made": do not question them, accept them as context
- If a section is empty, ignore it
```

### __init__.py

`build_pr_context()` orchestrates:
1. Call `fetch_pr_discussion()` — raises on error
2. Call `find_past_reviews()` with `sandbox_root` and `head_sha` — retains same-PR reviews across heads, annotates head metadata, and raises on corrupt sessions
3. Call `deduplicate()` — pure, never fails; returns retained past reviews plus pruned discussion events
4. Call `build_orientation_brief(..., discussion=pruned_discussion_events, past_reviews=kept_past_reviews, pr_stats=pr_stats, run_llm=run_llm)` — returns `""` for no data, raises on LLM error
5. Write debug artifacts to `work_dir / "pr_context_discussion.json"` (pruned discussion) and `work_dir / "pr_context_past_reviews.json"` (retained past reviews) when data exists
6. Return dict

### cure.py integration

After `compute_pr_stats` completes (~`cure.py:9754-9767`), before the final multipass/singlepass prompt routing:
1. Bind `gh_fetch` to `gh_api_list(host=pr.host, ...)` imported from `cure_github`
2. Compute `effective_head_sha = review_head_sha or head_sha or None` and call `build_pr_context(pr, sandbox_root=paths.sandbox_root, work_dir=work_dir, pr_stats=pr_stats, head_sha=effective_head_sha, gh_fetch=gh_fetch, run_llm=run_llm)` in a new phase; `effective_head_sha` is used for prior-review metadata annotation and never as a same-PR exclusion criterion
3. Store result dict/meta under `progress.meta["pr_context"]`
4. For built-in singlepass (normal or big): render and run the singlepass template without `PRIOR_CONTEXT` to produce `draft_review`. If `context["orientation_brief"]` is non-empty, call `_reconcile_prior_context(draft_review, context["orientation_brief"], run_llm)` and use that result as the final review. If the brief is `""`, skip reconciliation and use `draft_review` unchanged.
5. For fresh multipass: leave plan and step calls unchanged and context-free. When `_pr_flow_impl` renders the shared synth prompt, pass `PRIOR_CONTEXT = context["orientation_brief"] or ""` in `extra_vars`.
6. For interrupted multipass resume: `_resume_flow_impl` reads the persisted `work/pr_context_orientation.md` when it exists and passes that content as `PRIOR_CONTEXT`; if it does not exist, pass `""`. Never render the shared synth template without the key.
7. Fail hard: if `build_pr_context()` or `_reconcile_prior_context()` raises, abort the review instead of silently returning an unreconciled context-aware result.

### Template changes

`$PRIOR_CONTEXT` appears only in the multipass synth template:
- `prompts/mrereview_gh_local_big_synth.md` (multipass synth reconciliation)

Remove `$PRIOR_CONTEXT` and the old in-template sequencing instructions from the singlepass templates:
- `prompts/mrereview_gh_local.md` (normal singlepass draft prompt)
- `prompts/mrereview_gh_local_big.md` (big singlepass draft prompt when multipass is disabled)

Continue to exclude `$PRIOR_CONTEXT` from the independent multipass templates:
- `prompts/mrereview_gh_local_big_plan.md` (multipass plan — independent planning)
- `prompts/mrereview_gh_local_big_step.md` (multipass step — independent code review)

Singlepass context reconciliation is not a template instruction. It is a separate prompt in `cure.py::_reconcile_prior_context()` that receives `draft_review` and `orientation_brief` after the first LLM call. The reconcile prompt should instruct the model to treat the draft review as the independent code-evidence baseline, use the orientation brief to check for missed unresolved issues and confirmed decisions, and return the final review. Current code evidence wins over unsupported context claims.

Multipass plan and step behavior is unchanged: those calls remain independent. The shared synth template reconciles their findings with `$PRIOR_CONTEXT` using the same Option B rules: inspect only disputed paths and let current code evidence win. Both `_pr_flow_impl` and `_resume_flow_impl` must supply the substitution key; resume reuses the persisted orientation artifact so interruption does not silently discard available context, and uses `""` only when that artifact is absent.

### Packaging

`pyproject.toml` uses explicit setuptools metadata. Add `"cure_pr_context"` to the package list and `"cure_github"` to `py-modules`; prove importability with a wheel/install smoke so installed `cure` environments can import the new package/module.
