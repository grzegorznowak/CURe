# Design: simple-pr-context

## Package structure

```
cure_pr_context/
  __init__.py   # build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)
                # → { orientation_brief, discussion, past_reviews, meta }
  fetcher.py    # fetch_pr_discussion(owner, repo, number, gh_fetch) → list[dict]
  corpus.py     # find_past_reviews(sandbox_root, pr, discussion_events, head_sha) → list[dict]
                # deduplicate(past_reviews, discussion_events) → (kept_past_reviews, pruned_discussion_events, deduped_count)
  orient.py     # build_orientation_brief(discussion, past_reviews, pr_stats, run_llm) → str
```

`cure_pr_context` must also be listed in `pyproject.toml` because CURe uses explicit setuptools package metadata.

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
  find_past_reviews(..., head_sha) ─→ list[dict]  (past reviews)
        │     ▲
        │     └── sandbox_root completed sessions + remote official footer blocks
        ▼
  deduplicate(past, discussion)  ──→  (kept_past_reviews, pruned_discussion_events, deduped_count)
        │                                    │
        │                                    ├──→  JSON → work/pr_context_discussion.json (pruned discussion)
        │                                    └──→  JSON → work/pr_context_past_reviews.json (retained past reviews)
        ▼
  build_orientation_brief()      ──→  str  (pruned discussion + retained past reviews → $PRIOR_CONTEXT)
```

## API contract

### gh_api_list helper (new in cure.py)

All 3 GitHub discussion endpoints return JSON **arrays**, but the existing `gh_api_json` at `cure.py:7416-7418` validates `isinstance(payload, dict)` and raises `ReviewflowError` on non-dict payloads. A new `gh_api_list` helper must be added to `cure.py` that:
- Calls `gh api --paginate [--slurp]` (retrying without `--slurp` on CLI incompatibility)
- Decodes and flattens multi-page JSON arrays into a single `list[dict]`
- Raises `ReviewflowError` on subprocess, auth, invalid JSON, or unexpected non-list payload failures

The old branch `cure-subsequent-pr-review/story-01-intake` has a list-capable implementation (`cure.py:7613-7634`) that can be ported directly, then tightened to return list payloads for this use case.

```python
def build_pr_context(
    pr: object,                       # PrUrl/PullRequestRef or compatible
    sandbox_root: str | Path,         # root containing completed review session dirs
    work_dir: str | Path,             # current session work/ dir for debug artifacts
    pr_stats: dict[str, Any] | None,  # existing compute_pr_stats result for scanner context
    head_sha: str | None,             # effective current PR/review head SHA for footer compatibility
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

`gh_api_json` remains correct for PR metadata/object endpoints and must not be reused for discussion arrays. `head_sha` is passed explicitly because `PullRequestRef` and `compute_pr_stats` do not contain a SHA.

## Module design

### fetcher.py

Calls 3 GitHub endpoints via `gh_fetch` (which must be list-capable — `gh_api_list` from `cure.py` or a bound wrapper):
- `repos/{owner}/{repo}/issues/{number}/comments`
- `repos/{owner}/{repo}/pulls/{number}/reviews`
- `repos/{owner}/{repo}/pulls/{number}/comments`

Returns a flat list of dicts with keys: `kind`, `author`, `body`, `created_at`, `url`, `path`, `line`, `review_state`.

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
3. Verify remote footer PR number using session metadata/session id when available and verify head SHA compatibility by prefix against the explicit `head_sha` parameter when both current head and footer `sha` are known; incompatible footer bodies are not past reviews and remain ordinary discussion events.
4. Do not trust author — any comment/review body with a valid official footer and compatible PR/head metadata is a past CURe review regardless of who posted it.
5. Ignore inline review comments for remote footer provenance; they remain discussion events unless separately pruned as duplicates of a retained past review.

**deduplicate():**
- For each past review, normalize body (lowercase, collapse whitespace) and compute char 3-grams.
- For each discussion event, compute the same.
- If Jaccard(past_review_ngrams, discussion_ngrams) ≥ 0.85, mark the discussion event as duplicate of that retained past review.
- Return `(kept_past_reviews, pruned_discussion_events, deduped_count)`.
- Retained side is always `past_reviews`; duplicate events are removed from the `discussion` returned by `build_pr_context()`, the debug artifact, and the LLM orientation input.

**format_past_reviews():** Convert the kept past reviews into a formatted string or JSON-safe structure for the LLM scanner and debug artifact.

### orient.py

**build_orientation_brief():**
1. Construct a prompt for the LLM with: pruned discussion events, retained past reviews, PR stats (diff size, file count).
2. Prompt instructs the LLM to produce a structured brief with fixed sections plus usage instructions for the review agent.
3. The LLM output IS the orientation brief — it includes both the sections and the usage instructions inline.
4. Returns the brief string directly. When there are zero discussion events and zero past reviews, returns `""` (empty string).

**Sections:**
- `## Áreas resueltas` — areas already addressed in prior reviews or resolved discussion threads
- `## Áreas problemáticas` — areas with unresolved concerns, repeated feedback, or CHANGE_REQUESTED
- `## Issues pendientes` — open questions or requested changes not yet addressed
- `## Patrones repetidos` — cross-cutting themes in feedback (e.g., "consistently asked for more tests")
- `## Decisiones ya tomadas` — design decisions confirmed in prior reviews that should not be re-litigated

**Usage instructions (inline in the output):**
```
INSTRUCCIONES PARA USAR EL PRIOR_CONTEXT:
- "Áreas resueltas": no dediques tiempo a re-evaluarlas, salvo que el diff las toque
- "Áreas problemáticas": priorízalas en tu plan de revisión
- "Issues pendientes": verifica si el diff los resolvió o no
- "Patrones repetidos": menciónalos como tema transversal si siguen presentes
- "Decisiones ya tomadas": no las cuestiones, acéptalas como contexto
- Si una sección está vacía, ignórala
```

### __init__.py

`build_pr_context()` orchestrates:
1. Call `fetch_pr_discussion()` — raises on error
2. Call `find_past_reviews()` with `sandbox_root` and `head_sha` — raises on corrupt sessions
3. Call `deduplicate()` — pure, never fails; returns retained past reviews plus pruned discussion events
4. Call `build_orientation_brief(..., discussion=pruned_discussion_events, past_reviews=kept_past_reviews, pr_stats=pr_stats, run_llm=run_llm)` — returns `""` for no data, raises on LLM error
5. Write debug artifacts to `work_dir / "pr_context_discussion.json"` (pruned discussion) and `work_dir / "pr_context_past_reviews.json"` (retained past reviews) when data exists
6. Return dict

### cure.py integration

After `compute_pr_stats` completes (~`cure.py:9754-9767`), before the final multipass/singlepass prompt routing:
1. Bind `gh_fetch` to `gh_api_list(host=pr.host, ...)`
2. Compute `effective_head_sha = review_head_sha or head_sha or None` and call `build_pr_context(pr, sandbox_root=paths.sandbox_root, work_dir=work_dir, pr_stats=pr_stats, head_sha=effective_head_sha, gh_fetch=gh_fetch, run_llm=run_llm)` in a new phase
3. Store result dict/meta under `progress.meta["pr_context"]`
4. When building `extra_vars` for any built-in review prompt mode, always add `PRIOR_CONTEXT`: `context["orientation_brief"] or ""`
5. Fail hard: if `build_pr_context()` raises, abort the review before prompt rendering

### Template changes

Add `$PRIOR_CONTEXT` near the top after the task description, before the main review instructions, to these 5 built-in review templates:
- `prompts/mrereview_gh_local.md` (normal singlepass)
- `prompts/mrereview_gh_local_big.md` (big singlepass when multipass is disabled)
- `prompts/mrereview_gh_local_big_plan.md` (multipass plan)
- `prompts/mrereview_gh_local_big_step.md` (multipass step)
- `prompts/mrereview_gh_local_big_synth.md` (multipass synth)

When the variable resolves to empty (S1 baseline), `render_prompt` replaces it with `""` and the agent sees nothing. Custom prompts and follow-up/resume templates are explicitly out of scope for template insertion.

### Packaging

`pyproject.toml` currently uses explicit setuptools metadata (`packages = ["prompts"]`). Add `"cure_pr_context"` to the package list and prove importability with a wheel/install smoke so installed `cure` environments can import the new package.
