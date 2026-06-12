# Design: story-01-subsequent-review-intake

## Architecture Overview
See `story.md` for the canonical story contract. Critical files/surfaces for this change:

| File | Role |
|---|---|
| `projects/CURe/pyproject.toml` | Packaging and mypy configuration; must include/check the new `cure_subsequent_review` package |
| `projects/CURe/cure_subsequent_review/__init__.py` | Package marker/export surface for installed-package import smoke checks |
| `projects/CURe/cure_subsequent_review/contracts.py` | Domain models: `SubsequentReviewModules` enum, `EvidencePolicy`, `ModuleStatus`, `PriorFindingCandidate`, `DiscussionEvent`, `ReconciledFinding`, ledger schemas |
| `projects/CURe/cure_subsequent_review/control_plane.py` | Top-level switch, per-module toggles, run manifest, branch-safe preflight summary, evidence-policy recording |
| `projects/CURe/cure_subsequent_review/github_history.py` | GitHub discussion ingestion: issue comments, reviews, review comments, best-effort thread state, pagination/completeness/degraded status |
| `projects/CURe/cure_subsequent_review/prior_corpus.py` | Prior CURe session + CURe-authored PR comment corpus builder; wraps `scan_completed_sessions_for_pr` |
| `projects/CURe/cure_subsequent_review/prior_findings.py` | Prior finding extraction from CURe artifacts/comments, including parse-degraded status |
| `projects/CURe/cure_subsequent_review/finding_identity.py` | Fingerprinting, matching, deduplication, supersession, reconciliation ledger |
| `projects/CURe/cure.py:7389–7438` | Public GitHub fallback and `gh_api_json` are dict-only; new list helper/generalization must not break existing callers |
| `projects/CURe/cure.py:9351–9534` | `_pr_flow_impl`; branch-aware integration must respect `--if-reviewed` exits and run intake only for new sandboxes |
| `projects/CURe/cure.py:15385–15404` | CLI parser choices for `--if-reviewed prompt/new/list/latest`; compatibility proof anchor |
| `projects/CURe/cure_flows.py:1647–1701` | Split-module GitHub helper compatibility seam; tests may patch through `cure`/`cure_flows` |
| `projects/CURe/cure_sessions.py:123–133` | `PullRequestRef` shared PR identity model |
| `projects/CURe/cure_sessions.py:934–943` | `HistoricalReviewSession` dataclass with `review_md_path` and `review_head_sha` fields |
| `projects/CURe/cure_sessions.py:1026–1057` | `scan_completed_sessions_for_pr` split-module owner reused by Prior Review Corpus Builder |
| `projects/CURe/meta.py:82–87` | `write_json` parent-dir creation/JSON write helper for `work/subsequent/` artifacts |
| `projects/CURe/tests/_reviewflow_test_support.py` | Existing test support — may need fixture helpers for subsequent-review tests |
| `projects/CURe/tests/_reviewflow_unittest_grounding_impl.py` | Existing `_pr_flow_impl` tests and patch seams that branch-compatibility tests should preserve/update |
| `projects/CURe/tests/test_subsequent_review.py` | Public wrapper for subsequent-review tests; imports private split suites for discovery compatibility |
| `projects/CURe/tests/_subsequent_review_test_support.py` | Shared `PR`/`Session` fixtures and readable helper methods for subsequent-review tests |
| `projects/CURe/tests/_subsequent_review_unit_*_unittest.py` | Unit/domain suites split by contracts/CLI, GitHub history, prior corpus, prior findings, and reconciliation |
| `projects/CURe/tests/_subsequent_review_functional_control_plane_unittest.py` | Functional/component control-plane artifact and status tests |
| `projects/CURe/tests/_subsequent_review_integration_pr_flow_unittest.py` | Integration-style `_pr_flow_impl` branch and session-lifecycle tests |
| `projects/CURe/tests/fixtures/subsequent_review/` | Deterministic fixture data derived from `docs/examples/subsequent-review-simulation.md` using PR `#9999` convention |

## Technical Decisions
- D1 — Module package location: New package at `projects/CURe/cure_subsequent_review/` with flat module files (`contracts.py`, `control_plane.py`, `github_history.py`, `prior_corpus.py`, `prior_findings.py`, `finding_identity.py`), not inline in `cure.py`. Rejected: expanding `cure.py` monolith further.
- D2 — Artifact subdirectory: Subsequent-review artifacts live under `work/subsequent/` to avoid colliding with existing `work/pr_context.json`, `work/review.md`, etc. Rejected: mixing with root `work/` artifacts and risking name collisions.
- D3 — Evidence policy modes: `EvidencePolicy` enum has exactly two members: `TRUSTED` and `UNTRUSTED`, matching the epic constraint. Rejected: adding a third "balanced" or "conservative" mode.
- D4 — Module toggle mechanism: Module enable/disable is a plain `dict[str, ModuleStatus]` config mapping, passed through the Control Plane, not per-module CLI flags. The exact top-level config source is intentionally left to implementation discovery but must be test-injectable. Rejected: CLI flag explosion (13 flags) and flag/contract drift risk.
- D5 — GitHub API generalization: Add a `gh_api_list` helper (or generalize `gh_api_json` to accept expected return type) for array-returning endpoints (comments, reviews), rather than silently casting arrays to dicts in the existing `gh_api_json`. Rejected: overloading `gh_api_json` return type without shape proof; dict-only contract is load-bearing in existing callers.
- D6 — Finding identity strategy: Use deterministic structural heuristics for fingerprinting (section + severity + headline text hash) rather than LLM-dependent semantic matching. Rejected: LLM-based identity matching would be unstable across prompt/template changes and untestable without live LLM runs.
- D7 — Disabled-module output contract: When a module is disabled, its output getter returns `None` (or a status-only wrapper with `status: DISABLED`), never an empty-but-valid artifact. The run manifest records the disabled status. Rejected: returning empty artifacts would make "no findings" indistinguishable from "module disabled."
- D8 — Fixture naming: Local deterministic fixtures use PR `#9999` convention from `docs/examples/subsequent-review-simulation.md`, not the live PR `#21`. Rejected: depending on live GitHub state for routine test success, which the epic explicitly forbids.
- D9 — Package/typecheck visibility: Adding `cure_subsequent_review` requires updating `pyproject.toml` so the package is included in installed distributions and the plain project `mypy` run checks it. Rejected: relying on source-checkout imports or unconfigured mypy silence.
- D10 — Thread-state semantics: PR review-thread state is best-effort discussion metadata (`resolved`, `unresolved`, `unknown`, or unavailable), never source truth and never a suppression/source-resolution trigger in Story 01. Rejected: treating resolved-thread hints as proof of source resolution.
- D11 — `--if-reviewed` integration placement: Persistent subsequent-review intake runs only after existing routing chooses a new sandbox (`new` or non-interactive prompt fallback). `list`, `latest`, and prompt-selected historical exits create no new sandbox and no `work/subsequent/` artifacts. Rejected: pre-branch artifact writes that would force session creation for historical-view commands.
- D12 — Fixture semantic boundary: Story 01 fixture goldens cover raw A/B/C/S inputs and intake/extraction/reconciliation/degraded expectations only. Source verification, authority/discussion resolution, disposition, final report, and memory reuse goldens are deferred to Stories 02/03. Rejected: making Story 01 assert later-story source/disposition semantics.
- D13 — CURe-authored PR comments: Prior Review Corpus Builder includes PR comments only when CURe authorship/provenance can be established by the implemented strategy; unknowns are recorded as degraded or ignored-with-reason. Rejected: silently omitting unknown comments while claiming complete corpus coverage.
- D14 — Local display ID namespace: Finding IDs parsed from reports/comments are local to their corpus entry unless explicitly globally namespaced. Reconciler identity and supersedes resolution must preserve origin namespace and full provenance; ambiguous display-ID targets are recorded instead of resolved by last-write wins. Rejected: treating `CURE-01`, `A-01`, or similar IDs as globally unique across completed sessions.
- D15 — GitHub list fallback/cause contract: `gh api --paginate --slurp` failures are classified with stderr/stdout/exit and endpoint context. Recoverable compatibility failures may retry through a documented compatible list path; otherwise the artifact is degraded-with-cause. Rejected: interpreting command failure as successful empty discussion or hiding stderr/cause detail.
- D16 — Prior generated report compatibility: Story 01 must either parse CURe's generated human-review `review.md` finding format or consume a machine-readable prior-finding ledger emitted by CURe reviews. Rejected: relying only on synthetic canonical markdown while real generated reports produce zero prior findings.

## Implementation Strategy
Source-inspection focus: Start in `cure.py:_pr_flow_impl` around PR metadata resolution, `scan_completed_sessions_for_pr`, and the `--if-reviewed` branch. Existing `list`, `latest`, and prompt-selected historical-review paths return before session/work directories exist, so persistent `work/subsequent/` artifacts must be written only after the branch proceeds to a new sandbox. Study `gh_api_json` and its public fallback because both reject non-dict payloads; GitHub comment/review endpoints need a list-capable helper or an explicit expected-payload generalization. Prefer importing PR/session identity from the split `cure_sessions` module rather than adding new coupling to duplicate legacy definitions in `cure.py`.

Smallest red-first seam family:

1. Package + contract types (`pyproject.toml`, `cure_subsequent_review/__init__.py`, `contracts.py`): write failing tests for installed-package import, 13-member `SubsequentReviewModules`, exactly two `EvidencePolicy` members, `ModuleStatus`, and base dataclasses. Green includes pyproject package inclusion and plain `mypy` visibility (A10, A12).
2. `--if-reviewed` compatibility harness: write branch tests for enabled subsequent review with `list`, `latest`, prompt-selected historical review, `new`, and non-interactive prompt fallback before adding runtime integration. Green preserves historical exits with no sandbox/artifacts and proves new-run branches invoke intake (A15-A19).
3. Fixtures (`tests/fixtures/subsequent_review/`): convert simulation doc cases into local JSON/markdown using PR `#9999`; include raw A/B/C/S data and Story 01 extraction/reconciliation/degraded goldens only. Extend fixtures with duplicate local display IDs from different corpus entries, ambiguous `Supersedes:` targets, transitive chains, `gh api --paginate --slurp` failure/fallback cases, and real generated CURe `review.md` or machine-readable prior-finding ledger samples. Red: fixture tests reference nonexistent files/cases. Green: fixtures load and schema-validate without requiring source/disposition semantics (A11, A20-A22).
4. GitHub History Collector: red-first with mocked list endpoints, thread-state variants, pagination, unavailable paths, and `gh api --paginate --slurp` compatibility failures. Green: `pr_discussion.json` records normal thread markers, fallback/incomplete collection, stderr/exit/cause taxonomy, and degraded statuses without silent-empty/resolved or recoverable-failure-as-zero-discussion fallbacks (A3, A4, A21).
5. Prior Review Corpus Builder: red-first against fixture completed sessions and identifiable CURe-authored PR comments. Green: `prior_review_corpus.json` contains local session provenance and PR comment provenance, with conservative status for unknown author/comment shapes (A5, A6, A13).
6. Prior Finding Extractor + Finding Reconciler: red-first over well-formed canonical markdown, malformed artifacts, real generated CURe `review.md` samples or explicit prior-finding ledger artifacts, duplicate local IDs, ambiguous supersedes, and transitive supersedes chains. Green: parse-degraded artifacts preserve parseable candidates with cause/provenance, real reports/ledgers produce usable candidates, and reconciliation remains conservative while preserving the complete origin/provenance graph (A7, A8, A14, A20, A22).
7. Control Plane integration: wire toggles, run manifest, preflight, disabled/degraded behavior, and artifact writes after module seams are stable (A1, A2, A9, A18, A19).

Phases:

1. Packaging + contracts (A10, A12) — no runtime behavior yet
2. Branch compatibility tests around `_pr_flow_impl` (A2, A15-A19)
3. Fixtures and schema validation (A11)
4. PR History Collector, including thread-state normal/degraded paths and `gh api --paginate --slurp` fallback/cause taxonomy (A3, A4, A21)
5. Prior Review Corpus Builder, including CURe-authored PR comments (A5, A6, A13)
6. Prior Finding Extractor + Finding Reconciler, including parse-degraded artifacts, real generated CURe report or ledger inputs, duplicate local IDs, ambiguous supersedes, and transitive supersedes chains (A7, A8, A14, A20, A22)
7. Control Plane integration and run manifest/disabled behavior (A1, A9)

Constraints:

- Use `work/subsequent/` subdirectory for new artifacts to avoid colliding with existing `work/pr_context.json`.
- Keep modules importable with zero side effects; all I/O gated behind explicit calls.
- `gh_api_json` currently returns `dict[str, Any]`; GitHub comment/review endpoints return arrays. Either generalize or add a parallel `gh_api_list` helper — do not silently cast array responses to dicts. If public fallback is supported for list endpoints, make its return-shape check list-aware too. For `gh api --paginate --slurp` failures, preserve subprocess stderr/stdout/exit and classify the cause before deciding whether to retry without `--slurp`, use public/API-list fallback, or emit degraded-with-cause.
- Module toggles must be a plain config mapping, not CLI flags per module (the Control Plane owns the enable/disable surface). The exact top-level config source remains an implementation detail but must be test-injectable.
- CURe-authored PR comment identification is provisional: include only comments whose CURe authorship/provenance can be established by the chosen strategy; unknowns must be represented as degraded/ignored-with-reason rather than silently treated as complete coverage.
- Thread-state capture is best-effort discussion metadata. It may never set source-resolution labels or suppressions in Story 01.
- Prior finding IDs are local display IDs unless a durable namespace proves otherwise. Reconciliation must key provenance by corpus entry/origin plus display ID, not display ID alone, and must preserve all origin records when deduplicating or resolving supersedes.
- If parsing human `review.md` remains intentionally unsupported for generated CURe reports, implementation must emit and persist a machine-readable prior-finding ledger from completed reviews and consume that ledger in subsequent review; do not leave the Story 01 prior-finding memory dependent on a parser that yields success-empty output for normal CURe reports.

Activated risk lenses and idioms: external service/CLI compatibility (prove normal/degraded GitHub paths and `--slurp` fallback/cause taxonomy), parsing/generated-artifact compatibility (prove parseable subset plus real generated report or explicit ledger), finding identity/provenance graph preservation (prove local-ID reuse, ambiguous supersedes, transitive chains), module lifecycle (prove toggle respect), command routing (prove `--if-reviewed` branches), packaging/typecheck visibility (prove installed import + mypy). Compare against existing `scan_completed_sessions_for_pr` for session-discovery patterns, `write_json` for artifact-writing patterns, and existing `_pr_flow_impl` tests for branch patch seams.

## Risks & Mitigations
- `pyproject.toml:17–18` — setuptools currently lists only top-level `py-modules` plus `packages = ["prompts"]`; a new `cure_subsequent_review/` package will not be included in installed distributions unless package config changes.
- `pyproject.toml:37–44` — `tool.mypy.files` currently includes selected top-level files only; plain `mypy` will not check the new package unless the file list/config changes.
- `cure.py:7389–7415` and `cure.py:7418–7435` — public GitHub fallback and `gh_api_json` are dict-only. For comment/review list endpoints a parallel `gh_api_list` or generalized expected-return helper is needed; public fallback needs the same list-shape handling if used.
- `cure_flows.py:1647–1701` — split-module GitHub helper compatibility also has dict-only behavior/delegation. New tests should patch the same seam production code uses, or deliberately add a compatibility wrapper.
- `cure.py:9351–9534` — `_pr_flow_impl` resolves PR metadata, validates `--if-reviewed`, calls completed-session scan, and returns early for `list`, `latest`, and prompt-selected historical sessions before session/work directories are created. Persistent subsequent-review intake belongs after the branch proceeds to a new sandbox and before review prompt assembly.
- `cure.py:9526–9530` — existing PR context write happens under `work/pr_context.json`; Story 01 artifacts should use `work/subsequent/` (D2) and avoid altering Story 03 prompt variables.
- `cure.py:15385–15404` — CLI choices remain `prompt`, `new`, `list`, and `latest`; no per-module CLI flags exist today, consistent with D4.
- `cure_sessions.py:123–133` — `PullRequestRef(host, owner, repo, number)` is the canonical PR identity. All new modules should accept this type, not raw URL strings.
- `cure_sessions.py:934–943` — canonical `HistoricalReviewSession` is a frozen dataclass with `review_md_path` and `review_head_sha`; Prior Review Corpus Builder should map artifact path/head from those fields.
- `cure_sessions.py:1026–1057` — `scan_completed_sessions_for_pr` filters by `meta.status == "done"`, PR match, and review artifact existence, then returns newest-first historical sessions. Can be called directly from Prior Review Corpus Builder.
- `meta.py:82–87` — `write_json` creates parent directories and writes JSON; it is a reusable artifact-writing helper for `work/subsequent/*.json`.
- `docs/examples/subsequent-review-simulation.md:1–16` — simulation is synthetic and uses PR `#9999`; deterministic fixtures should follow D8 instead of live PR #21 state.
- `docs/examples/subsequent-review-simulation.md:364–375` — visible degraded fallbacks include comments API unavailable, threads unavailable, prior artifact parse failure, and pagination incomplete; Story 01 must cover the intake/extraction status portions without claiming later disposition behavior.
- `docs/examples/subsequent-review-simulation.md:427–446` — expected engine behavior includes later source/disposition outcomes; Story 01 fixtures may store raw S facts and expected extraction/reconciliation inputs, but final source/disposition goldens are deferred by D12.
- No existing `work/subsequent/` directory, `cure_subsequent_review/` package, `tests/test_subsequent_review.py`, or `tests/fixtures/subsequent_review/` path exists — no migration/backwards-compat risk for those paths.
- Latest local PR #22 run evidence at `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac/work/subsequent/pr_discussion.json` shows all three list endpoints degraded as `discussion_unavailable` after `gh api --hostname github.com ... --paginate --slurp` failed, with only `Command failed (1)` detail and no stderr/cause taxonomy.
- Latest local PR #22 run evidence at `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac/work/subsequent/prior_review_corpus.json` shows two completed local session `review.md` bodies captured successfully with reviewed head `76712fb...`; `/work/subsequent/prior_findings.json` then has zero findings and two `parse_degraded` artifact statuses with `finding_id_without_parseable_heading`, proving a real generated-report extraction gap rather than missing corpus.
- The captured generated review bodies include normal CURe final report issue blocks under `### In Scope Issues` with `<details><summary><b>Severity</b>...` structures, not only canonical `### CURE-01` or `- [A-01][Medium]` fixture formats; A22 requires parser support for this shape or an explicit machine-readable ledger.
- Still-open implementation details: exact top-level config source, exact CURe-authored PR comment identification strategy, GraphQL/thread-state availability, robust historical markdown parser shape versus machine-readable ledger design, exact GitHub list fallback order, and ambiguity marker schema for supersedes.
