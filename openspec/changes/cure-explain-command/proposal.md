# Proposal: cure-explain-command

## Goal / Context

`cure explain` gives developers a newcomer-first, plain-language explanation of a completed PR review — inline from review text, or forked from the original Codex session with full context replay, an optional `--open-in-codex` interactive handoff, and a built-in additive question mode. The change also delivers review-flow hardening for concurrent explain/resume/follow-up within the story's A11/A12 top-level merge contract: a shared lock-and-merge protocol for every session-metadata writer, strict metadata mutation, newest-first session discovery, codex-only backend enforcement, and CI that actually collects the concurrency tests.

The feature was built and hardened across six review rounds on branch `feat/explain-command` (PR #37): rounds 2–5 were remediated, the operator-directed permission-model unification (D29) and its proof were delivered at HEAD `f684f18`, round-6 findings F1–F4 and F6–F9 are absorbed into this story's scope (operator decision 2026-08-13, story A18–A25), and the round-7 regular-usage findings G2/G3/G4/G6/G7/G12/G13 are absorbed by operator decision 2026-08-15 (story A26–A32, D32–D34; findings requiring explicit operator/attacker action or crafted/imported external data — G1, G5, G8, G9, G10, G11 — remain out of scope). This change workspace absorbs the delivered work into OpenSpec governance and tracks the pending A18–A25 and A26–A32 remediation deltas so future changes hang off proper structure.

## Story Candidates
<!-- Single story — this change is the full scope of the absorbed feature + hardening. -->

## Decisions & Constraints
<!-- Inherited from the cure-explain-command initiative; full list in story.md Locked Decisions (D1–D30). -->
- Codex-only backend: HTTP/gemini providers and transports rejected at parse/exec time; positive fixtures and docs are codex-only.
- Explain follows delivered interactive runtime-policy construction exactly: bypass on, sandbox mode and approval policy `None`, and configured sandbox flags suppressed through `include_sandbox=False`; D29 adds no permission config surface. It prints a loud truthful mode line on every run and builds `--open-in-codex` through the same interactive resume semantics (ordered runtime flags/overrides, `--search`, bypass, session repository, and staged credential env); `normalize_artifact=False` and per-run private credential staging/cleanup remain.
- One lock-and-merge protocol for all session-meta writers: sidecar flock outside the session dir + fresh reload + change-gated persist; SessionProgress baseline-diff flushes with explicit `drop()`/`deleted_keys`.
- Persisted session metadata is untrusted input: `meta.paths` containment checks; newest-first discovery; unusable artifacts reported clearly, never a silent fallback.
- Accepted exclusions are owned by story D27; round-6 findings F1–F4 and F6–F9 (including nested-metadata deep merge) are absorbed into this story's scope (story D28/A18–A25).
- Delivery vehicle: PR #37, branch `feat/explain-command`; remediation rounds 2–5 landed RED→GREEN with full-suite verification, ruff/mypy/py_compile clean, and green CI; round 6 was triaged and its findings are absorbed into this story.

## External Resources
- PR #37 (feature branch + six review rounds): https://github.com/grzegorznowak/CURe/pull/37
