# Tasks: simple-pr-context

## Setup & Prerequisites
- [x] Create directory `cure_pr_context/` with empty `__init__.py`
- [x] Create directory `tests/cure_pr_context/` (without `__init__.py` so it does not shadow the real package during pytest)
- [x] Add `cure_pr_context` to `pyproject.toml` (`[tool.setuptools].packages`) for install/wheel
- [x] Read old `github_history.py` / old branch `cure.py` from branch `cure-subsequent-pr-review/story-01-intake` — extract `collect_pr_discussion`, endpoints, `gh_api_list`, pagination, and normalization
- [x] Read old `prior_corpus.py` from the same branch — extract official footer detection (`CURE_REVIEW_FOOTER_START/END`), `sha`, `session`, local session scan; adapt to explicit compatibility with live `head_sha`

## Core Implementation
- [x] Implement/port `cure.py::gh_api_list()` — list-capable helper for `gh api --paginate [--slurp]` with fallback without `--slurp`
- [x] Implement `fetcher.py::fetch_pr_discussion()` — 3 endpoints, list-capable `gh_fetch`, normalize to flat dicts
- [x] Implement `corpus.py::find_past_reviews(..., head_sha)` — local scan under `sandbox_root` + official remote footers in issue comments and review bodies with head compatibility by prefix
- [x] Implement `corpus.py::deduplicate()` — char n-grams + Jaccard ≥ 0.85; retain `past_reviews` and return pruned `discussion` without duplicate events
- [x] Implement `orient.py::build_orientation_brief()` — scanner prompt + LLM call → fixed sections + inline instructions
- [x] Implement `__init__.py::build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)` — orchestrate fetch → corpus/head-SHA check → retained-side dedup → orient → write pruned/retained debug artifacts → return dict
- [x] Add `$PRIOR_CONTEXT` to the 3 synthesis templates (normal singlepass, big singlepass, multipass synth) with 3-phase guardrails; intentionally exclude from plan/step templates
- [x] Inject `build_pr_context()` in `cure.py::_pr_flow_impl` after `compute_pr_stats`, passing effective `head_sha` (`review_head_sha` if it exists, otherwise PR API `head_sha`); exclude prior context from `_build_multipass_step_entries`
- [x] Always pass `PRIOR_CONTEXT` (brief or `""`) in `extra_vars` for normal singlepass, big singlepass, and multipass synth; plan/step templates have no `$PRIOR_CONTEXT` token
- [x] Register `pr_context` meta in `progress.meta` and abort before prompt rendering on GitHub/LLM/session scan errors

## Verification & Proof
- [x] `tests/cure_pr_context/test_fetcher.py` — unit tests with mock `gh_fetch`/`gh_api_list` returning arrays (TAP-01)
- [x] `tests/cure_pr_context/test_corpus.py` — unit tests with tmp `sandbox_root` session dirs + in-memory discussion with official footer; test compatible/incompatible `head_sha` and that `past_reviews` is the retained side while `discussion` is pruned (TAP-02)
- [x] `tests/cure_pr_context/test_orient.py` — unit tests with mock `run_llm` (TAP-03)
- [x] `tests/cure_pr_context/test_init.py` — unit tests for `build_pr_context` with `pr_stats` + `head_sha` fixtures, mock `gh_fetch`, mock `run_llm`, tmp `sandbox_root`, and tmp `work_dir`; assert debug artifacts use pruned discussion/retained past_reviews (TAP-04)
- [x] `tests/cure_pr_context/test_integration.py` — end-to-end with JSON fixtures for the 3 endpoints, compatible/incompatible footer SHA, retained-side dedup, and pruned discussion output (TAP-05)
- [x] `tests/cure_pr_context/test_templates.py` — verify `$PRIOR_CONTEXT` in 5 rendered templates, with brief and with `""`, without raw tokens (TAP-06)
- [x] `tests/test_cure_pr_flow.py` — verify injection point, effective `head_sha` passed to `build_pr_context`, and `extra_vars` always with `PRIOR_CONTEXT` in normal singlepass, big singlepass, multipass plan/step/synth; fallback with helper seams/monkeypatch, no generic `--dry-run` (TAP-07)
- [x] Packaging smoke — build wheel/install target and `import cure_pr_context` from installation (TAP-09)

## Integration & Cleanup
- [x] Ruff check + mypy clean in `cure_pr_context/` (TAP-08)
- [x] Run full CURe test suite — verify zero regressions
- [x] `git status` — confirm only in-scope files created/modified
