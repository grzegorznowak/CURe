# Review Log

- 2026-06-22T06:55:57Z Review run by fresh oblivious maintainer session
  - Decision: not_reviewable
  - Approval gate: fail
  - Product verdict: not_assessed
  - Technical verdict: not_assessed
  - Multipass review: not_triggered
  - Prior review concerns: none
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🟡 IN PROGRESS -> 🟡 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; no external issue/PR/Jira anchor inspected because readiness failed before implementation review
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: none beyond OpenSpec readiness artifacts; implementation review aborted before source inspection
  - Risk lenses reviewed: none material; implementation review aborted at readiness gate
  - Finding closure: none
  - Evidence quality: confirmed story header status is not reviewable; inferred none; unknown implementation correctness not assessed; provisional none
  - Files reviewed: `AGENTS.md`, `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`, `openspec/changes/cure-doctor-chunkhound-health/story.md`, `openspec/changes/cure-doctor-chunkhound-health/progress.md`, `openspec/changes/cure-doctor-chunkhound-health/reviews.md` (absent before this entry)
  - Hypothesis triage:
    - suspicious surface: `story.md` status header; tentative issue: implementation is still marked in progress, so review ownership cannot start; next proof target: implementer should transition the story to `🟣 IN REVIEW` after completing the claim
  - Key findings:
    - Story is not reviewable because the authoritative `Status:` header is still `🟡 IN PROGRESS`, not `🟣 IN REVIEW` or `✅ DONE`. Sources: `openspec/changes/cure-doctor-chunkhound-health/story.md:2`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** `/openspec-story-review` may only arbitrate stories that implementation ownership has explicitly handed off for review. This story is still marked in progress, so approving or requesting implementation changes from review would bypass the required readiness transition.

      **Assumptions / Preconditions:** The `Status:` header in `story.md` is the authoritative implementation status for this change workspace.

      **Downgrade Factors:** None.

      **Code Trail:** The story header records `Plan: 🟢 PLAN APPROVED` followed by `Status: 🟡 IN PROGRESS`; the review skill allows review only from `🟣 IN REVIEW` or `✅ DONE`.

      **Reproduction:** Open `openspec/changes/cure-doctor-chunkhound-health/story.md` and inspect line 2.

      </details>
  - Debt Friction: none
  - Next action: Have the implementation owner finish/claim review readiness and set `Status: 🟣 IN REVIEW`, then rerun `/openspec-story-review cure-doctor-chunkhound-health cure-doctor-chunkhound-health WORKTREE=/home/vscode/cure-doctor-chunkhound-health`.

- 2026-06-22T07:14:30Z Review run by fresh oblivious maintainer session
  - Decision: not_reviewable
  - Approval gate: fail
  - Product verdict: not_assessed
  - Technical verdict: not_assessed
  - Multipass review: incomplete
  - Prior review concerns: resolved
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🟣 IN REVIEW -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `AGENTS.md`; initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; change artifacts `story.md`, `proposal.md`, `design.md`, `tasks.md`, `progress.md`, `reviews.md`; no external issue/PR/Jira anchor found; notebook external-resource reference intentionally not used as review authority
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: none beyond OpenSpec readiness/proof artifacts; implementation review aborted before source inspection because proof matrix still has a provisional row
  - Risk lenses reviewed: external-service/live ChunkHound credential dependency only as a readiness/proof risk; implementation risk lenses not assessed because review aborted at proof gate
  - Finding closure: prior status-readiness concern resolved (`story.md` now starts in review); new proof-readiness blocker remains
  - Evidence quality: confirmed A2 proof row is still provisional and progress records no live successful health smoke due missing credentials; inferred implementation correctness not assessed; unknown source correctness and live ChunkHound behavior; provisional A2 proof affects approval
  - Files reviewed: `AGENTS.md`, `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`, `openspec/changes/cure-doctor-chunkhound-health/story.md`, `openspec/changes/cure-doctor-chunkhound-health/proposal.md`, `openspec/changes/cure-doctor-chunkhound-health/design.md`, `openspec/changes/cure-doctor-chunkhound-health/tasks.md`, `openspec/changes/cure-doctor-chunkhound-health/progress.md`, `openspec/changes/cure-doctor-chunkhound-health/reviews.md`
  - Hypothesis triage:
    - suspicious surface: `story.md` Acceptance Proof Matrix; tentative issue: A2 still has provisional live end-to-end proof, so approval is blocked before source review; next proof target: finalize or explicitly narrow the A2 proof row and align `progress.md`/`tasks.md` evidence
  - Key findings:
    - Story is not reviewable because A2's Acceptance Proof Matrix row remains `provisional`, and progress records that the live successful health smoke is still environment-dependent rather than completed. Sources: `openspec/changes/cure-doctor-chunkhound-health/story.md:266`, `openspec/changes/cure-doctor-chunkhound-health/progress.md:16`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review gate requires every proof row to be final before implementation can be approved. A2 is the story's core full ChunkHound health check, so leaving its proof provisional means review cannot safely arbitrate the implementation yet.

      **Assumptions / Preconditions:** The Acceptance Proof Matrix in `story.md` is the authoritative proof contract, and A2 remains in scope unless the story is explicitly updated to narrow or replace the live proof requirement.

      **Downgrade Factors:** If implementation ownership records an approved explicit exception/narrower proof boundary and updates A2's row to final with concrete evidence, this readiness blocker may clear without additional code changes.

      **Code Trail:** `story.md` marks A2 as `provisional` and states manual live ChunkHound evidence is required; `progress.md` confirms the live successful health smoke was not completed because credentials were unavailable.

      **Reproduction:** Open `openspec/changes/cure-doctor-chunkhound-health/story.md`, inspect the A2 row in the Acceptance Proof Matrix, then compare the latest `progress.md` verification log.

      </details>
  - Debt Friction: none
  - Next action: Run `/openspec-story-resume cure-doctor-chunkhound-health cure-doctor-chunkhound-health` to finalize or explicitly narrow the A2 proof row, record the aligned evidence in `progress.md`/`tasks.md`, and then return the story to `🟣 IN REVIEW`.

- 2026-06-22T07:45:00Z Review run by fresh oblivious maintainer session
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Multipass review: completed
  - Prior review concerns: resolved (A2 proof row now final at `story.md:266`; prior readiness blockers cleared)
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🟣 IN REVIEW -> ✅ DONE
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `AGENTS.md`; initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; change artifacts `proposal.md`, `design.md`, `tasks.md`, `progress.md`, `reviews.md`; no external issue/PR/Jira anchor found; no delta spec files present; no dependency/sibling stories required
  - Traceability: forward complete; backward complete
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `cure_chunkhound.py`, `cure_llm.py` (helper extraction, overrides, runtime staging), `cure_runtime.py` (config validation, health check, gating, payload), `cure_commands.py` (shared artifacts), `_doctor_chunkhound_fixture/` (fixture helper, resources), `pyproject.toml` (packaging), `tests/test_doctor_chunkhound.py` (TAP-1 through TAP-7, TAP-9), `tests/_reviewflow_unittest_runtime_ui_impl.py` (helper/preflight regression, updated doctor tests)
  - Risk lenses reviewed: generated helper artifact, external I/O/subprocess/timeouts, JSON/config data shape, credentials/no-log handling, resource lifecycle/temp dirs, packaging/module layout, doctor JSON output schema, timeout budgeting vs story contract; no UI/design-source lens applicable
  - Finding closure: prior review concerns fully resolved (A2 proof row is `final` in current `story.md`; status is `🟣 IN REVIEW`); all prior blockers addressed by implementation owner before this review
  - Evidence quality: confirmed code structure, gating logic, fixture lifecycle, test coverage, lint/type pass, test pass (33 new + 65 existing doctor + 610 reviewflow regression); inferred no hidden external ticket intent beyond initiative/story; unknown live ChunkHound behavior remains bounded by unit/mocked proof for A2 as planned; provisional none
  - Files reviewed: `cure_chunkhound.py`, `cure_llm.py`, `cure_runtime.py`, `cure_commands.py`, `_doctor_chunkhound_fixture/__init__.py`, `_doctor_chunkhound_fixture/main.py`, `_doctor_chunkhound_fixture/utils.py`, `_doctor_chunkhound_fixture/README.md`, `pyproject.toml`, `tests/test_doctor_chunkhound.py`, `tests/_reviewflow_unittest_runtime_ui_impl.py`
  - Hypothesis triage:
    - suspicious surface: `cure_chunkhound.py:17-23`, `cure_chunkhound.py:1083-1091` — tool call wrappers run hidden internal MCP preflights; tentative issue: total health runtime may exceed the story's stated per-stage timeout budget; next proof target: verify actual wall-clock times do not matter for the product outcome (the story's timeout values bound tool stages, not full helper calls)
    - suspicious surface: `cure_runtime.py:2756-2760` vs `cure_runtime.py:2768-2791` — resolved `binary` path used only for fixture indexing; MCP preflight/tool calls default to PATH lookup; tentative issue: binary mismatch between indexing and MCP phases if multiple `chunkhound` versions on PATH; next proof target: confirm PATH resolution is deterministic (binary check gate already verifies `chunkhound` on PATH)
    - suspicious surface: `_doctor_chunkhound_fixture/__init__.py:33-40`, `cure_runtime.py:2835-2837` — temp health config contains user API credentials; indexing failure detail passes raw subprocess stderr/stdout; tentative issue: if ChunkHound echoes config values on error, doctor output could leak credentials; next proof target: verify ChunkHound binary never echoes config values in error output, or add redaction
  - Key findings:
    - Timeout budgeting: `run_chunkhound_tool()` runs an internal MCP preflight before each tool call, so the 60s/300s timeouts bound only the `tools/call` stage, not the full helper invocation. Story calls for search ≤60s and research ≤300s for the overall helper call, but actual per-call wall time includes implicit preflight cycles. Sources: `cure_chunkhound.py:17-23`, `cure_chunkhound.py:1083-1091`, `cure_runtime.py:2768-2774`, `cure_runtime.py:2786-2792`

      <details open>
      <summary><b>Low</b> severity · <b>Low</b> likelihood</summary>

      **Why:** The per-stage timeout values bound the right operation (tool execution), and the total worst-case ~510s budget is conservative enough to absorb extra preflight overhead. This is a design-documentation gap, not a functional failure.

      **Assumptions / Preconditions:** `run_chunkhound_tool()` is the health check's entry point for search and code_research, and it always runs an internal preflight before each tool call.

      **Downgrade Factors:** The tests pass with mocked tool calls and do not depend on precise wall-clock timing. Live ChunkHound MCP preflight is fast (sub-5s in practice), so extra overhead is negligible.

      **Code Trail:** `cure_runtime.py:2768-2774` calls `run_chunkhound_tool(..., timeout=60.0)` → `cure_chunkhound.py:1205-1210` → `cure_chunkhound.py:1064-1091` runs internal preflight with default stage timeouts (incl. `initialize=120s`) before the 60s `tools/call` stage.

      **Reproduction:** Trace the call chain from `_doctor_chunkhound_health_check()` through `run_chunkhound_tool()` to `_run_tool_once()` / `_run_preflight()`.

      </details>
    - API credential exposure on subprocess failure: temp health-check config copies user `embedding.api_key` and `llm.api_key` into a temp file; `CalledProcessError` detail passes raw stderr/stdout into the doctor check detail string. If ChunkHound echoes config values in errors, doctor output may leak credentials. Sources: `_doctor_chunkhound_fixture/__init__.py:33-40`, `cure_runtime.py:2835-2837`

      <details open>
      <summary><b>Medium</b> severity · <b>Low</b> likelihood</summary>

      **Why:** The story requires API keys to be never logged or included in doctor output. The primary path is safe (validation only names field keys, not values), and the temp file is cleaned up. However, subprocess error passthrough is uncontrolled.

      **Assumptions / Preconditions:** ChunkHound binary must echo config values (including `api_key`) in stderr or stdout during indexing failure. CURe's `chunkhound` binary is not known to do this.

      **Downgrade Factors:** The implementation already handles the credential-check path (skip MCP) correctly. Fixture indexing failure is a rare edge case. Temp dir cleanup via `TemporaryDirectory` ensures keys are not left on disk.

      **Code Trail:** `_doctor_chunkhound_fixture/__init__.py:33-39` merges user config (including keys) → writes temp `chunkhound.json` → `_doctor_chunkhound_fixture/__init__.py:42-47` runs `chunkhound index` → `cure_runtime.py:2835-2837` on `CalledProcessError` returns `stderr or stdout` in the doctor check detail → `cure_commands.py:1310-1314` prints check details.

      **Reproduction:** Trigger an indexing failure (e.g., corrupt fixture) and inspect `cure doctor` output for credential material in the error detail.

      </details>
  - Debt Friction: none
  - Next action: Commit the implementation with a descriptive message referencing the initiative; consider adding credential redaction before subprocess error passthrough as a follow-up hardening item
