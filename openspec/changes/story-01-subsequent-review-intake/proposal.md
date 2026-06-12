# Proposal: story-01-subsequent-review-intake

## Goal / Context
Give `cure pr` the ability to collect and normalize PR discussion history plus prior CURe review findings into a single reconciled prior-finding ledger. When subsequent review is enabled (via the Control Plane), the operator sees a preflight summary of what was found; when it is disabled, legacy fresh `cure pr` behavior is preserved unchanged. Disabled or degraded modules must never produce silent suppressions or source-resolution claims.

## Story Candidates
Single story — this change workspace is the full scope. See `story.md` for actors, acceptance, verification, and proof contract.

## Decisions & Constraints
Inherits initiative-level decisions from `../../initiatives/cure-subsequent-pr-review/initiative.md`.

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

## External Resources
- Initiative: `../../initiatives/cure-subsequent-pr-review/initiative.md`
- Legacy coordination source: `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/story-01-subsequent-review-intake.md`
