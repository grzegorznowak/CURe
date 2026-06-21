# Review Log

- 2026-06-20T13:32:30Z Review run by fresh oblivious maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: none (no prior `reviews.md` existed)
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🟢 DONE -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `openspec/initiatives/simple-pr-context/initiative.md`, `proposal.md`, `design.md`, story Discovery Notes; no GitHub/Jira issue anchor found
  - Traceability: forward gaps (A4/proof issues below); backward complete for reviewed changed surfaces
  - Design trace: gaps; rendered evidence not applicable
  - Code surfaces searched: `cure_pr_context/*`, `cure.py` PR flow/API helpers/multipass prompt paths, `cure_flows.py` prompt rendering, `cure_sessions.py` session scan, `cure_output.py` footer generation, `prompts/mrereview_gh_local*.md`, `pyproject.toml`, `tests/cure_pr_context/*`, `tests/test_cure_pr_flow.py`, `tests/_reviewflow_unittest_grounding_impl.py`
  - Risk lenses reviewed: external GitHub/subprocess I/O, filesystem/session scanning, generated debug artifacts, prompt/template substitution fail-open, packaging/install, LLM orientation boundary; cache/persistence and UI/TUI excluded by story scope
  - Finding closure: first implementation review; plan-review hotspot TAP-07 checked and remains proof-gapped
  - Evidence quality: confirmed direct code/spec reads, targeted repros, and `python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q -p no:cacheprovider` (15 passed); inferred no live PR execution; unknown no external ticket beyond old-branch reference; provisional A7 proof remains in story matrix
  - Files reviewed: `openspec/initiatives/simple-pr-context/initiative.md`, `openspec/changes/simple-pr-context/{story.md,proposal.md,design.md,tasks.md}`, `cure_pr_context/{__init__.py,fetcher.py,corpus.py,orient.py}`, `cure.py`, `cure_flows.py`, `cure_sessions.py`, `cure_output.py`, `prompts/mrereview_gh_local.md`, `prompts/mrereview_gh_local_big.md`, `prompts/mrereview_gh_local_big_plan.md`, `prompts/mrereview_gh_local_big_step.md`, `prompts/mrereview_gh_local_big_synth.md`, `pyproject.toml`, `tests/cure_pr_context/*`, `tests/test_cure_pr_flow.py`, `tests/_reviewflow_unittest_grounding_impl.py`
  - Hypothesis triage:
    - suspicious surface: `cure_pr_context/corpus.py` remote footer parsing; tentative issue: marker-only footer blocks become trusted past reviews and prune discussion; next proof target: `story.md:92`, `design.md:112-116`, `corpus.py:49-57`, `corpus.py:117-134`
    - suspicious surface: `cure_sessions.py` completed-session scan; tentative issue: corrupt `meta.json` is skipped instead of fail-hard; next proof target: `design.md:76`, `design.md:158`, `cure_sessions.py:190-196`, `cure_sessions.py:954-964`, `corpus.py:90`
    - suspicious surface: story proof matrix/TAP-07; tentative issue: approval proof remains provisional and tests source-inspect flow instead of exercising `_pr_flow_impl` seam; next proof target: `story.md:199`, `story.md:213`, `tests/test_cure_pr_flow.py:8-26`
  - Key findings:
    - A7 cannot be approved while its Acceptance Proof Matrix row is still `provisional`, and the checked-in TAP-07 test mostly source-inspects `_pr_flow_impl` instead of exercising the mocked flow seam promised by the TAP. Sources: `openspec/changes/simple-pr-context/story.md:199`, `openspec/changes/simple-pr-context/story.md:213`, `tests/test_cure_pr_flow.py:8`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review gate requires every proof row to be final before approval. A7 is the core integration point for automatic PR context, so leaving it provisional means the story contract itself says this acceptance is not fully proven.

      **Assumptions / Preconditions:** The story’s Acceptance Proof Matrix remains authoritative for review proof maturity.

      **Downgrade Factors:** Direct code review indicates the intended call order and `head_sha` wiring are present, so this is a proof-contract blocker more than evidence of a broken runtime path.

      **Code Trail:** `story.md` defines TAP-07 as a flow proof with mocked `build_pr_context`/branch fixtures, but the proof matrix keeps A7 provisional and `tests/test_cure_pr_flow.py` starts by using `inspect.getsource(cure._pr_flow_impl)`.

      **Reproduction:** Read the A7 proof row in the story matrix; it still says `provisional` and requires live proof after implementation.

      </details>
    - Malformed marker-only footer blocks are trusted as past CURe reviews and removed from discussion. Sources: `openspec/changes/simple-pr-context/story.md:92`, `openspec/changes/simple-pr-context/design.md:112`, `cure_pr_context/corpus.py:49`

      <details open>
      <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A4 requires official remote CURe footers with a `sha <short>` token. The implementation accepts any body containing only the start/end markers, so spoofed or malformed comments can be treated as past reviews and pruned out of the discussion sent to the orientation scan.

      **Assumptions / Preconditions:** A PR comment/review body contains `CURE_REVIEW_FOOTER_START` and `CURE_REVIEW_FOOTER_END` without a valid footer line containing `sha`/`session` metadata.

      **Downgrade Factors:** A genuine CURe footer normally includes both metadata fields, so well-formed CURe output works.

      **Code Trail:** `parse_footer_metadata()` returns a non-empty dict whenever markers exist, even when `sha_match` and `session_match` are absent; `_remote_review_from_event()` treats any non-empty metadata dict as a retained past review.

      **Reproduction:** Calling `find_past_reviews()` with one issue-comment event whose body is `CURE_REVIEW_FOOTER_START` + arbitrary text + `CURE_REVIEW_FOOTER_END` returns one `past_reviews` entry and an empty `discussion` list.

      </details>
    - Corrupt local session metadata is silently skipped instead of failing hard. Sources: `openspec/changes/simple-pr-context/design.md:76`, `openspec/changes/simple-pr-context/design.md:158`, `cure_sessions.py:190`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** The design says corrupt local sessions should make `build_pr_context()` fail hard. The current implementation delegates to a scanner that returns `None` on malformed `meta.json`, so broken historical-review data can be missed silently and the review agent can remain blind to prior CURe feedback.

      **Assumptions / Preconditions:** A directory under `sandbox_root` has a malformed or unreadable `meta.json` that would otherwise identify a completed session for the PR.

      **Downgrade Factors:** If the operator’s sandbox root never contains corrupt session directories, this does not affect runtime behavior.

      **Code Trail:** `find_past_reviews()` calls `scan_completed_sessions_for_pr()`. That scanner calls `_load_session_meta()`, which catches parse/read exceptions and returns `None`, causing the session directory to be skipped.

      **Reproduction:** Create a sandbox subdirectory with invalid `meta.json` and a `review.md`; `find_past_reviews()` returns no past reviews and raises no error.

      </details>
    - The returned `meta` shape does not include the per-kind discussion counts documented by the API design. Sources: `openspec/changes/simple-pr-context/design.md:68`, `cure_pr_context/__init__.py:55`

      <details open>
      <summary><b>Low</b> severity · <b>High</b> likelihood</summary>

      **Why:** Operators and later diagnostics lose the split between issue comments, PR reviews, and inline review comments that the design promised in `meta`.

      **Assumptions / Preconditions:** Downstream diagnostics or progress metadata rely on the documented `n_comments`, `n_reviews`, and `n_review_comments` keys.

      **Downgrade Factors:** The story acceptance only requires a `meta` key at top level, and aggregate counts are returned.

      **Code Trail:** The design’s return schema lists `n_comments`, `n_reviews`, and `n_review_comments`; `build_pr_context()` instead returns `n_discussion_fetched`, `n_discussion`, `n_past_reviews`, and `n_deduped`.

      **Reproduction:** Inspect `build_pr_context()`’s `meta` literal; the per-kind keys are absent.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume simple-pr-context simple-pr-context` to fix A4/fail-hard behavior and update proof rows/tests before requesting review again

- 2026-06-21T04:16:17Z Review run by fresh oblivious maintainer session
  - Decision: not_reviewable
  - Approval gate: fail
  - Product verdict: not_assessed
  - Technical verdict: not_assessed
  - Multipass review: completed
  - Prior review concerns: resolved
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🟢 DONE -> 🟢 DONE
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `openspec/initiatives/simple-pr-context/initiative.md`, `openspec/changes/simple-pr-context/proposal.md`, `openspec/changes/simple-pr-context/design.md`, story Discovery Notes; no GitHub/Jira issue anchor found
  - Traceability: forward complete; backward complete
  - Design trace: complete; rendered evidence: not applicable
  - Code surfaces searched: `cure_pr_context/*`, `cure.py` PR flow/API helpers/multipass prompt paths, `cure_flows.py` prompt rendering, `cure_sessions.py` session scan, `cure_output.py` footer generation, `prompts/mrereview_gh_local*.md`, `pyproject.toml`, `tests/cure_pr_context/*`, `tests/test_cure_pr_flow.py`, `tests/_reviewflow_unittest_grounding_impl.py`
  - Risk lenses reviewed: external GitHub/subprocess I/O, filesystem/session scanning, generated debug artifacts, prompt/template substitution fail-open, packaging/install, LLM orientation boundary; cache/persistence and UI/TUI excluded by story scope
  - Finding closure: prior review concerns resolved by final proof rows, code/test changes, focused pytest, ruff, mypy, and full test-suite verification; approval not assessed because the story status gate failed before approval eligibility
  - Evidence quality: confirmed direct code/spec reads and commands (`python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q -p no:cacheprovider`, `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py && mypy cure_pr_context`, `python -m pytest tests/ -q -x --timeout=120 -p no:cacheprovider`); inferred none; unknown no live GitHub/LLM/coverage proof; provisional none
  - Files reviewed: `openspec/initiatives/simple-pr-context/initiative.md`, `openspec/changes/simple-pr-context/{story.md,proposal.md,design.md,tasks.md,reviews.md}`, `cure_pr_context/{__init__.py,fetcher.py,corpus.py,orient.py}`, `cure.py`, `cure_flows.py`, `cure_sessions.py`, `cure_output.py`, `prompts/mrereview_gh_local.md`, `prompts/mrereview_gh_local_big.md`, `prompts/mrereview_gh_local_big_plan.md`, `prompts/mrereview_gh_local_big_step.md`, `prompts/mrereview_gh_local_big_synth.md`, `pyproject.toml`, `tests/cure_pr_context/*`, `tests/test_cure_pr_flow.py`, `tests/_reviewflow_unittest_grounding_impl.py`
  - Hypothesis triage:
    - suspicious surface: `openspec/changes/simple-pr-context/story.md` status header; tentative issue: story is not in a reviewable status for `/openspec-story-review`; next proof target: `openspec/changes/simple-pr-context/story.md:1-2`, `/workspaces/cure_workspace/projects/add/claude/skills/openspec-story-review/SKILL.md:399`
  - Key findings:
    - Story status is not reviewable by the review skill's status gate. Sources: `openspec/changes/simple-pr-context/story.md:1-2`, `/workspaces/cure_workspace/projects/add/claude/skills/openspec-story-review/SKILL.md:399`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** The story header says `Status: 🟢 DONE`, but the review command only treats `🟣 IN REVIEW` or `✅ DONE` as reviewable. This run therefore cannot approve or request implementation changes from the review lane, and the status must remain unchanged.

      **Assumptions / Preconditions:** The `/openspec-story-review` status gate is authoritative for this write-back, and no operator instruction explicitly overrides that readiness policy.

      **Downgrade Factors:** The implementation-focused passes found the prior review concerns resolved, but readiness gating is independent of implementation quality.

      **Code Trail:** `story.md` records `Plan: 🟢 PLAN APPROVED` and `Status: 🟢 DONE`; the review skill says a story whose `Status:` is not `🟣 IN REVIEW` or `✅ DONE` must be treated as `not_reviewable` and left unchanged.

      **Reproduction:** Open `openspec/changes/simple-pr-context/story.md` and compare the `Status:` header with the allowed statuses in `/workspaces/cure_workspace/projects/add/claude/skills/openspec-story-review/SKILL.md:399`.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume simple-pr-context simple-pr-context` to move the story through the implementation-owned review request state (`🟣 IN REVIEW`) or otherwise correct the OpenSpec lifecycle state, then rerun `/openspec-story-review simple-pr-context simple-pr-context WORKTREE="/home/vscode/add-worktrees/CURe-simple-pr-context-impl"`

- 2026-06-21T04:26:45Z Review run by fresh oblivious maintainer session
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Multipass review: completed
  - Prior review concerns: resolved
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: ✅ DONE -> ✅ DONE
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `openspec/initiatives/simple-pr-context/initiative.md`, `openspec/changes/simple-pr-context/{proposal.md,design.md,tasks.md,story.md}`; no GitHub/Jira issue anchor found beyond the recorded old-branch reference
  - Traceability: forward complete; backward complete
  - Design trace: complete; rendered evidence: complete for the five built-in prompt templates and not applicable for UI/TUI surfaces
  - Code surfaces searched: `cure_pr_context/{__init__.py,fetcher.py,corpus.py,orient.py}`, `cure.py`, `pyproject.toml`, `prompts/mrereview_gh_local*.md`, `tests/cure_pr_context/*`, `tests/test_cure_pr_flow.py`, prior `reviews.md`
  - Risk lenses reviewed: external GitHub/subprocess I/O, filesystem/session scanning/generated artifacts, prompt/template substitution fail-open behavior, LLM orientation boundary, packaging/install; cache/persistence, custom prompts, follow-up/resume templates, and UI/TUI excluded by story scope
  - Finding closure: first-review blockers remain fixed (official-footer `sha` trust, corrupt local-session fail-hard handling, TAP-07 runtime proof, public `meta` per-kind counts), and the previous review-only blocker is closed because `Status:` is now the valid `✅ DONE`; reran focused tests, full suite, ruff, mypy, and packaging smoke successfully
  - Evidence quality: confirmed direct code/spec reads plus commands (`python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q -p no:cacheprovider` -> 18 passed; `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py` -> passed; `mypy cure_pr_context` -> passed; `python -m pytest tests/ -q -x --timeout=120 -p no:cacheprovider` -> 638 passed, 13 subtests; wheel/install import smoke -> passed); inferred no live GitHub/LLM execution beyond deterministic mocks; unknown no external ticket beyond recorded old-branch reference; provisional none
  - Files reviewed: `openspec/initiatives/simple-pr-context/initiative.md`, `openspec/changes/simple-pr-context/{story.md,proposal.md,design.md,tasks.md,reviews.md}`, `cure_pr_context/{__init__.py,fetcher.py,corpus.py,orient.py}`, `cure.py`, `pyproject.toml`, `prompts/mrereview_gh_local.md`, `prompts/mrereview_gh_local_big.md`, `prompts/mrereview_gh_local_big_plan.md`, `prompts/mrereview_gh_local_big_step.md`, `prompts/mrereview_gh_local_big_synth.md`, `tests/cure_pr_context/{test_fetcher.py,test_corpus.py,test_orient.py,test_init.py,test_integration.py,test_templates.py}`, `tests/test_cure_pr_flow.py`
  - Hypothesis triage:
    - suspicious surface: `openspec/changes/simple-pr-context/story.md` status header; tentative issue: previous invalid `🟢 DONE` status might still make the story not reviewable; next proof target: `openspec/changes/simple-pr-context/story.md:1-2`
    - suspicious surface: prior implementation review findings; tentative issue: footer trust, fail-hard session scan, A7 proof, or meta shape regressions could remain; next proof target: `openspec/changes/simple-pr-context/story.md:308-312`, `cure_pr_context/corpus.py:50`, `cure_pr_context/corpus.py:93`, `cure_pr_context/__init__.py:24`, `tests/test_cure_pr_flow.py:11`
    - suspicious surface: dirty target worktree; tentative issue: approval with unrelated dirty state; next proof target: `git status --short` for `/home/vscode/add-worktrees/CURe-simple-pr-context-impl`
  - Key findings:
    - No blocking findings. The story is reviewable with `Plan: 🟢 PLAN APPROVED` and `Status: ✅ DONE`, and every Acceptance Proof Matrix row A1-A11 is final. Sources: `openspec/changes/simple-pr-context/story.md:1-2`, `openspec/changes/simple-pr-context/story.md:203-217`
    - Prior implementation findings are resolved and covered by regression tests: marker-only footers are ignored without `sha`, corrupt local session metadata fails hard, TAP-07 exercises `_pr_flow_impl` at runtime, and `meta` exposes per-kind discussion counts. Sources: `openspec/changes/simple-pr-context/story.md:308-312`, `tests/cure_pr_context/test_corpus.py:77`, `tests/cure_pr_context/test_corpus.py:93`, `tests/test_cure_pr_flow.py:11`, `tests/cure_pr_context/test_init.py:45`
    - The implementation matches the initiative/proposal/design contract for a four-file `cure_pr_context` package, list-capable GitHub discussion fetch, retained-side prior-review dedup, five built-in prompt insertions, fail-hard behavior, and package installability. Sources: `openspec/initiatives/simple-pr-context/initiative.md:29-33`, `openspec/changes/simple-pr-context/proposal.md:13`, `openspec/changes/simple-pr-context/design.md:43`, `openspec/changes/simple-pr-context/design.md:167-171`, `pyproject.toml:18`, `cure.py:9898`, `cure.py:10553`
  - Debt Friction: none
  - Next action: proceed with `/openspec-pr simple-pr-context simple-pr-context` or the equivalent PR delivery/evidence step; no implementation resume is required
