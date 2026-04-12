# Changelog

All notable changes to CURe are recorded here.

Release notes should be curated from merged PRs since the previous `vX.Y.Z` tag. Keep published entries user-facing and grouped by impact rather than by raw commit order. Story or epic IDs may help drafting internally, but they should not be published by default.

## Unreleased

### Added

- A repo-owned `cure_release` workflow now documents the maintained release path for Claude and Codex sessions.

### Changed

- Releases now update this changelog before the release commit and carry forward curated notes derived from merged PRs.

## [0.3.3] - 2026-04-09

### Changed

- Improved provider-aware model and effort selection so agent sessions choose Codex and Claude settings more predictably.

## Historical Note

- Releases before changelog adoption were still verified through `public_release_evidence/` and GitHub Releases.
