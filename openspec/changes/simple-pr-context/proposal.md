# Proposal: simple-pr-context

## Goal / Context

`cure pr` currently reviews PRs blind to discussion history — it sees only the PR description and the diff. This change adds a `cure_pr_context` package that fetches all PR discussion (comments, reviews, review comments) and past CURe reviews, deduplicates them, and runs a single LLM orientation scan. The resulting structured brief is delivered according to the actual review topology: multipass synth receives `$PRIOR_CONTEXT`; singlepass with context uses two real LLM calls (draft review without context, then `_reconcile_prior_context(draft_review, orientation_brief, run_llm)`); singlepass without context remains the current one-call path. The feature runs automatically on `cure pr` review runs with no operator flags required.

## Story Candidates

Single story — this change workspace is the full scope of the `simple-pr-context` initiative.

## Decisions & Constraints

A single `cure_pr_context/` package with 4 files. The public API is `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)`, which returns a dict with the orientation brief, deduplicated debug data, and metadata. `head_sha` is the effective PR/review SHA passed explicitly from `_pr_flow_impl` to verify remote footer compatibility; `gh_fetch` is list-capable (`gh_api_list`), `sandbox_root` is the real sessions/sandboxes root, `work_dir` is the current session's `work/`, and `pr_stats` is the result already computed by `compute_pr_stats`. The brief is produced by a single LLM scan with fixed sections and inline usage instructions. `$PRIOR_CONTEXT` appears only in the multipass synth template; normal/big singlepass, multipass plan, and multipass step templates have no token. Singlepass with non-empty context runs the ordinary singlepass prompt first, then `_reconcile_prior_context(draft_review, orientation_brief, run_llm)` performs the second LLM call and returns the final review. Singlepass with `orientation_brief == ""` remains one call. Multipass is unchanged: plan and step are independent calls and synth reconciles with `$PRIOR_CONTEXT`. Past-review deduplication uses char n-grams + Jaccard with no external dependencies; `past_reviews` is the retained side and duplicate events are removed from the returned/written/LLM-passed `discussion`. The LLM is received as a `Callable` injected from `cure.py`. Any error aborts the review. No cache, no new CLI flags, no changes to `cure_flows.py`.

## External Resources

- Old initiative branch (historical reference): `cure-subsequent-pr-review/story-01-intake` (38 commits, preserved in this repo)
