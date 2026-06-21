# Simple PR Context — Discussion & Past Review Orientation

source_of_truth: internal

## Goal / Context

*Second take on the PR-context problem — this time much simpler. The prior `cure-subsequent-pr-review` initiative built a heavy multi-stage pipeline (18 files, semantic pipeline, finding reconciliation, disposition arbitration). This initiative replaces it with a single lightweight orientation scan.*

When `cure pr` runs, the review agent currently sees only the PR description and the diff. It has no awareness of PR discussion (comments, reviews, review comments) or past CURe reviews on the same PR. This leads to repeated analysis of already-resolved areas and missed signals from prior feedback. The `simple-pr-context` initiative adds a lightweight orientation scan: fetch all PR discussion and past CURe reviews, deduplicate them, and pass them through a single LLM call that produces a structured orientation brief. The brief guides the review agent toward problematic areas and away from already-resolved ones — without overwhelming the prompt with raw discussion. "Done" means `cure pr` on any PR produces reviews informed by full discussion context and prior review history, with zero operator flags required.

### Risks / unknowns

- **LLM scan quality**: if the orientation model produces low-quality briefs (empty sections when there are signals, or the reverse), the feature can degrade the review instead of improving it. Mitigation: the usage instructions inside the orientation brief tell the review agent to ignore empty or irrelevant sections.
- **Token budget**: if the discussion is very long, the orientation scan can be expensive or exceed the context window. Future mitigation: truncate by event count or total length.
- **False positives in dedup**: Jaccard ≥ 0.85 can mark content as duplicate when it is similar but distinct. Mitigation: configurable threshold; `past_reviews` is the retained side and the worst case is pruning a discussion event that remains counted in `meta.n_deduped`.

## Story Candidates

1. **`fetcher`** — `fetcher.py`: fetch from 3 GitHub endpoints (issue comments, PR reviews, review comments), normalize to flat dicts. Simplify from the old `github_history.py`.
2. **`corpus`** — `corpus.py`: local session scan + remote CURe footer detection with `head_sha` compatibility + retained-side dedup by char n-grams/Jaccard. Based on the old `prior_corpus.py`.
3. **`orient`** — `orient.py`: LLM scan that produces the orientation brief with fixed sections (Resolved areas, Problem areas, Pending issues, Repeated patterns, Decisions made) + inline usage instructions.
4. **`cure_github` adapter** — top-level `cure_github.py`: host reusable GitHub CLI/API helpers (`gh_api_json`, `gh_api_list`, auth/public fallback helpers) so `cure.py` only imports/re-exports the seams it needs.
5. **`init + integration`** — `__init__.py` with `build_pr_context(..., head_sha, ...)`, injection in `cure.py` after `compute_pr_stats`, fail-hard on errors. Write deduplicated debug artifacts to `work/`.
6. **`prompt templates`** — add `$PRIOR_CONTEXT` to multipass synth template only. Singlepass templates intentionally exclude it — context arrives via a separate second LLM call (two-pass architecture with Option B reconciliation rules). Plan/step templates are independent review passes without context.
7. **`tests`** — unit tests per module + full pipeline integration with deterministic fixtures.

## Decisions & Constraints

**Locked-in:**
- 4-file package under `cure_pr_context/` (not 18 files like the previous initiative) plus a small top-level `cure_github.py` adapter registered in packaging
- API: `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm) -> dict`; `gh_fetch` is list-capable and based on `cure_github.gh_api_list`, not `gh_api_json`
- `head_sha` is passed explicitly from `_pr_flow_impl` (`review_head_sha` if it exists, otherwise PR API `head_sha`) to verify remote footers by prefix
- `$PRIOR_CONTEXT` in multipass synth template only; singlepass uses two-pass architecture (draft call then reconcile call with context, following Option B reconciliation rules: only inspect disputed files, code evidence wins)
- Plan and step are independent review passes without prior context
- Two-pass singlepass reconciliation rules: (1) draft+context agree → keep draft, (2) context flags missed issue → read that specific file before adding, (3) context says resolved but draft found issue → read file, code wins, (4) context blank → return draft unchanged
- Fail hard on any error (GitHub, LLM, corrupt files)
- LLM injected as `Callable[[str], str]` — no coupling to `cure.py` configs
- No cache in this iteration
- Dedup: char n-grams + Jaccard ≥ 0.85, pure stdlib; `past_reviews` retained, duplicate discussion pruned

**Explicitly NOT part of this initiative:**
- Multi-stage pipeline, semantic pipeline, disposition arbitration (from the old subsequent-review)
- Cache or persistent storage
- Trusted/untrusted evidence, signal classification
- UX changes or new CLI flags
- Changes in `cure_flows.py`; template changes live in prompt files, not flow code

## External Resources

- Old initiative branch (historical reference): `cure-subsequent-pr-review/story-01-intake` (38 commits, preserved in this repo)
