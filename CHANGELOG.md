# Changelog

All notable changes to CURe are recorded here.

Release notes should be curated from merged PRs since the previous `vX.Y.Z` tag. Keep published entries user-facing and grouped by impact rather than by raw commit order. Story or epic IDs may help drafting internally, but they should not be published by default.

## Unreleased

No entries yet.

## [0.3.6] - 2026-04-13

### Fixed

- `cure pr` no longer executes the reviewed repo's test suite on its own initiative. All review prompt templates now forbid running `pytest`, `npm test`, `go test`, `cargo test`, build scripts, linters, or formatters, and instruct the model to review test coverage and quality statically and to rely on `gh pr checks $PR_URL` (plus `gh run view`) for pass/fail status. This keeps `cure pr` focused on review intelligence instead of duplicating CI work and burning the `codex_plan` turn budget on flaky local runs.

## [0.3.5] - 2026-04-13

### Fixed

- `cure pr` with the Codex provider no longer aborts the review-intelligence gate with "missing successful code_research" on non-trivial repos. The staged `cure-chunkhound` helper now emits its first `tools/call waiting` heartbeat immediately (rather than after 10s) and repeats every 5s, so codex-cli sees a visibly live output stream during the 2–5 min LLM synthesis step of `research` and no longer surfaces the call to the model as a hang. The prompt templates used by `cure pr` also now explicitly tell the model that `research` legitimately takes 2–5 minutes per call on large repos, that the heartbeat lines are normal progress rather than a hang, and that it must issue one `research` invocation at a time and wait for its final JSON object before issuing another.

## [0.3.4] - 2026-04-12

### Changed

- Unified the bootstrap flow around `cure setup` and cleaned up the related setup follow-up behavior.

## [0.3.3] - 2026-04-09

### Changed

- Improved provider-aware model and effort selection so agent sessions choose Codex and Claude settings more predictably.

## Historical Note

- Releases before changelog adoption were still verified through `public_release_evidence/` and GitHub Releases.
