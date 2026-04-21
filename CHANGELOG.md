# Changelog

All notable changes to CURe are recorded here.

Release notes should be curated from merged PRs since the previous `vX.Y.Z` tag. Keep published entries user-facing and grouped by impact rather than by raw commit order. Story or epic IDs may help drafting internally, but they should not be published by default.

## Unreleased

### Changed

- Verbose finding cards are now the default review output for `cure pr`, `cure resume`, and `cure followup`; pass `--wtf off` to request the older concise finding format.

### Documentation

- Added README guidance for review output flags: default-on verbose finding detail via `--wtf`, the `--wtf off` concise-mode escape hatch, and `--cod-ledger on` for multipass hypothesis-ledger triage.

## [0.5.0] - 2026-04-21

### Added

- Verbose findings mode (`--wtf on`): opt-in enriched review output that adds Severity/Impact, Likelihood, Why, Assumptions/Preconditions, Downgrade Factors, Code Trail, and Reproduction Story to each final finding. Default review output is unchanged when the flag is omitted or off.

### Changed

- Release process now explicitly requires the GitHub Release body to mirror the curated `CHANGELOG.md` entry, keeping the Releases page in sync with the repo changelog.

## [0.4.0] - 2026-04-20

### Added

- Citation contract for review sources: follow-up and synthesis reviews now emit structured citations that trace each finding back to the originating diff chunk or prior-step artifact, via the new `cure_citations` module.

### Changed

- Multipass review phases renamed for clarity; step prompts tightened to enforce grounding against the actual diff rather than paraphrased summaries.
- Synthesis retries now preserve intermediate artifacts and cap UI retry attempts, with clearer operator feedback on retry state and effort.

### Fixed

- Synthesis finalization no longer drops findings when mixing cited and uncited sources in the same review pass.
- Resume flow correctly re-enters synthesis when the prior run was synth-only, instead of skipping to the next step.
- Omission rewrite footer and grounding rejection messaging aligned across all review modes (local, zip, follow-up).

## [0.3.9] - 2026-04-16

### Fixed

- ChunkHound tool proof recovery now handles Claude Code's persisted-output wrapper, where large Bash tool output is written to disk with only a 2 KB preview inlined. The proof JSON that falls outside the preview window is now read from the persisted file, preventing false "missing successful code_research" gate failures on Claude Code reviews with verbose helper output.

## [0.3.8] - 2026-04-16

### Fixed

- The hot-start ChunkHound base-cache prompt now pauses the active dashboard before waiting for operator input and resumes it afterward, so the TUI no longer appears stuck on "Base cache (agent is working)" while CURe is actually waiting for a hidden `/dev/tty` prompt.

## [0.3.7] - 2026-04-16

### Fixed

- The hot-start ChunkHound base-cache prompt no longer hangs silently when stdin is not a TTY. The operator prompt now uses `/dev/tty` consistently with the model/effort picker.

### Added

- `ARCHITECTURE.md` documenting the high-level structure and module responsibilities of the CURe codebase.

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
