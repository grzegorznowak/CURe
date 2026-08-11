# Story — Cure Explain Command

Plan: 🟢 PLAN APPROVED
Status: 🟣 IN REVIEW

> Story scaffolded from the agentic-workflow-cycle protocol run (2026-08-10):
> planning via Gate 1 human decisions; implementation complete and verified.

## Purpose
Users can run `cure explain <PR_URL> [--explain-prompt <text>]` to get a
human-friendly, LLM-generated explanation of the final synthesized review of a
completed review session — grounded in the review's full context (codex resume-fork
mode) without disturbing the pristine post-review session state that `interactive`
gates on.

## Actors
- Primary: CURe CLI user asking questions about a completed PR review
- Secondary: PR author reading the explanation
- Reviewer: CURe maintainer verifying the command contract
- System: CURe (parser/dispatch/flow), codex CLI (provider), codex session store

## Triggering Need
Review artifacts are dense; users need plain-language explanations and follow-up
questions about *why* findings were raised, with the backing knowledge the review
used. Resuming the original codex session directly would pollute the pristine
post-review state used by `cure interactive`, so explanations must run on a fork.

## Expected Prerequisites
None (standalone change; no dependency story workspaces).

## Scope
- New visible `explain` CLI command: argparse subparser, `main()` dispatch,
  `explain_flow` wrapper, `cure commands` catalog entry
- Target selection: positional `<PR_URL>` → most recent completed session
  (`scan_completed_sessions_for_pr`)
- Prompt: builtin `prompts/explain.md` default, overridable via `--explain-prompt`
- Streaming output (unless `--quiet`/`--no-stream`); explanation printed + artifact
  path; artifact at `<session>/explain/explain-<ts>.md`
- Codex resume-fork mode: fork base codex session (byte-copy + id rewrite) and
  `codex exec resume <fork>`; base rollout byte-identical; `meta.llm.resume` untouched
- Inline fallback (review text appended to prompt) for non-codex providers, missing
  resume info, or unforkable base session
- Meta recording: `explains[]` entries (prompt_source, output_path, timestamps,
  optional `resume: {mode, base_session_id, fork_session_id}`), `llm` usage

## Out of Scope
- `--prompt-file`, interactive stdin prompt, session-id targeting
- followup-style chunkhound/review-intelligence/PR-context wiring
- Non-codex provider resume; codex session store GC/cleanup
- TUI rendering; changes to `interactive`, `followup`, or the pr flow

## Scenarios / Behavior Examples
- S1: User runs `cure explain <url>` after a completed review → prints the
  explanation of the review and the artifact path. Covers: A2
- S2: User passes `--explain-prompt "Why was X flagged?"` → question appended
  to the builtin prompt; answer addresses X. Covers: A3
- S3: User runs explain with no completed session for the PR → clean exit-2 error.
  Covers: A4
- S4: Codex provider with recorded resume info → explanation shows backing
  knowledge; base codex session sha256 unchanged. Covers: A6
- S5: Non-codex provider (or missing base session) → inline explanation from review
  text; no fork created; exit 0. Covers: A7
- S6: `cure commands` lists explain with a recommended invocation. Covers: A8
- S7: User asks explain (codex) to modify a file or call gh → the agent reports the
  sandbox denied the action; the run completes read-only. Covers: A9
- S8: Non-quiet, non-no-stream run → live event lines (session/turn started,
  codex notices) reach the terminal as they arrive; answer text appears as each
  codex item is delivered. Covers: A5
- S9: Fork-mode run prints an explicit resume line (fork id + full-context replay
  notice) before the LLM call. Covers: A5

## Acceptance
- A1: `cure explain --help` shows the `pr_url` positional (like `cure pr`) and
  `--explain-prompt`; `cure explain <PR_URL>` requires no flags.
- A2: Default-prompt run against a completed session exits 0, prints explanation
  + artifact path, writes `explain/explain-<ts>.md`, records an `explains` entry
  with `prompt_source: builtin:explain.md`.
- A3: `--explain-prompt` appends the user's question to the builtin explain
  prompt (`## User's question` block, landing after the review in inline mode);
  the builtin loader IS called (template stays the base); entry
  `prompt_source: user:explain_prompt` and records the `question` text.
- A4: No completed session or invalid PR URL → exit 2 with a ReviewflowError message.
- A5: Live output unless `--quiet`/`--no-stream` (active output controller
  registered; display lines reach stderr while the LLM runs). Delivery is
  codex-item-granular, not per-token: codex `exec --json` emits whole completed
  items, so a single-message answer arrives as one chunk at the end; per-item
  messages and codex `error` items (rendered as `Codex notice: …`) surface live.
  The codex CLI is the only LLM backend (OpenAI/OpenRouter HTTP providers were
  removed and are rejected with a clear error).
- A6: Codex provider + recorded `meta.llm.resume` → a forked rollout with a new id
  is created; `codex exec resume <fork>` runs; base rollout is byte-identical;
  `meta.llm.resume` still names the base; entry records `resume.mode=fork`.
- A7: Non-codex provider, no resume info, or missing/unforkable base → inline mode
  (prompt contains the review text), no fork created, exit 0. Fork I/O failures
  (unreadable/unwritable store) also fall back inline.
- A8: `cure commands` catalog contains an `explain` entry.
- A9: Codex runs are read-only: no `--dangerously-bypass-approvals-and-sandbox`;
  `--sandbox read-only` (inline) / `-c sandbox_mode="read-only"` (resume); config
  `--sandbox`/`--search` flags are filtered out of the resume command; staged
  credentials are cleaned up on any failure path.
- A10: Repository selftest (`selftest.sh` Story 26 smoke) passes with the new
  catalog; `explain_flow` is exported via `cure_commands.__all__`, the `cure`
  re-export, and the reexport contract test.

## Verification

### Verification Commands
```
python3 -m unittest tests.test_reviewflow_unittest.ExplainCommandTests -v   # 31 obligations
python3 -m unittest discover -s tests -p 'test_*.py'                        # full suite (762)
ruff check cure.py cure_llm.py cure_commands.py tests/_reviewflow_unittest_explain.py
python3 -m py_compile cure.py cure_llm.py cure_commands.py
# Real-run evidence (codex-cli, completed PR21 session):
sha256sum ~/.codex/sessions/2026/08/04/rollout-*019fcb76*.jsonl   # before == after (a3711ee6…)
cure explain https://github.com/grzegorznowak/CURe/pull/21 \
  --explain-prompt "In one sentence: what must the author fix, and why?"
python3 -c 'import json;m=json.load(open("<session>/meta.json"));print(m["explains"][-1])'
```

### Test Architecture Plan
| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|---|---|---|---|---|---|---|---|---|---|
| TAP-1 | unit / flow | default prompt, stdout, artifact, meta (A2) | tests/_reviewflow_unittest_explain.py::ExplainCommandTests | `_explain_flow_impl` with mocked `run_llm_exec` | rc=0, artifact content, stdout, explains entry | tmp sandbox session + fake LLM writing output file | `unittest` ExplainCommandTests | manual CLI run | core contract in one owner |
| TAP-2 | unit / flow | user question appended (A3) | same owner | prompt assembly | loader called; question block after review; entry source + question | same fixtures | same | — | split from TAP-1 for the branch |
| TAP-3 | unit / flow | error paths + parser (A1, A4) | same owner | parse_pr_url, scan, subparser | ReviewflowError regexes; SystemExit; args mapping | empty sandbox; bad URL | same | — | CLI surface owner |
| TAP-4 | unit / flow | resume-fork + fallbacks (A6, A7) | same owner | fork_codex_session + run_llm_exec kwarg | fork rollout exists, ids rewritten, base byte-equal, resume_session_id set/None, prompt mode | tmp CODEX_HOME + fake base rollout | same | — | fork mechanics owner |
| TAP-5 | unit / helpers | fork helper, catalog, wrapper (A6, A8) | same owner | fork_codex_session; catalog payload; wrapper delegation | raise when base missing; catalog contains explain; delegation rc | tmp codex store; parser | same | — | helper-level proof |
| TAP-8 | unit / runner | read-only + resume flags (A9) | same owner | build_codex_exec_cmd both branches | `--sandbox read-only` / `-c sandbox_mode=...`; no bypass; `--sandbox`/`--search` filtered; skip-git-repo-check present on retry | direct cmd assertions | same | — | command-shape owner |
| TAP-9 | unit / flow | cleanup scope, unique artifacts, meta lock, fork rollback (A7, A9) | same owner | early-failure cleanup; same-second runs; file_lock; LLM-failure fork deletion | cleaned staged dict; distinct artifact names; lock on meta path; fork removed on failure | fake staged dict; recorder lock | same | — | lifecycle owners |
| TAP-10 | selftest / repo | installed-package catalog (A10) | tests/story26_cli_smoke.py + selftest.sh | editable-install venv smoke | smoke rc=0 with 6-command catalog | pip venv install | `python3 tests/story26_cli_smoke.py --cli-bin <venv>/bin/cure` | CI selftest.sh | install-contract gate |
| TAP-11 | real-run / e2e | read-only + streaming + pristine base (A5, A6, A9) | manual evidence (PR21, 2026-08-10 12:08Z) | real codex resume with sandbox + active output | stderr shows live event lines + per-item agent text; write/gh probes denied; rc=0; base sha unchanged | PR21 session + codex 0.144.6 | manual | TAP-8/9 | real-provider proof |
| TAP-6 | regression / repo | all suites + lint + compile (A2–A8) | full tests/ + ruff + py_compile | whole-repo | 762 tests OK; ruff clean | repo fixtures | full unittest discover | CI selftest.sh | regression gate |
| TAP-7 | real-run / e2e | live fork + pristine base (A2, A6) | manual evidence (PR21, 2026-08-10) | real codex exec resume | rc=0, answer grounded, base sha unchanged, meta resume block | completed PR21 session + codex 0.144.6 | manual | mocked owners TAP-1/4 | real-provider proof |

### Acceptance Proof Matrix
| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|---|---|---|---|---|---|---|
| A1 | final | automated TAP-3 | run subparser tests | args mapping + required pr_url positional | build_parser | — |
| A2 | final | automated TAP-1 + real TAP-7 | run TAP-1; inspect 2026-08-10 run log | rc=0, artifact, entry builtin:explain.md | _explain_flow_impl | — |
| A3 | final | automated TAP-2 | run TAP-2 | loader called, question block after review, entry source + question | prompt assembly | — |
| A4 | final | automated TAP-3 | run TAP-3 | ReviewflowError exit-2 paths | parse_pr_url, scan_completed_sessions_for_pr | — |
| A5 | final | automated TAP-1 + real TAP-11 | run stream tests; inspect 12:08Z stderr | stream flag; live event lines + item-complete text on stderr during run | ReviewflowOutput wiring | codex delivers whole items, not tokens |
| A6 | final | automated TAP-4/5 + real TAP-7/11 | run TAP-4; re-hash base rollout | fork rollout, base sha a3711ee6…, meta.llm.resume unchanged, entry fork ids | fork_codex_session, resume cmd | — |
| A7 | final | automated TAP-4/9 | run fallback + I/O-failure tests | inline prompt, no fork, rc=0; ReviewflowError conversion | fork fallback | — |
| A8 | final | automated TAP-5 + selftest TAP-10 | run catalog + smoke tests | explain entry; smoke rc=0 | catalog, story26 smoke | — |
| A9 | final | automated TAP-8/9 + real TAP-11 | run cmd-shape tests; inspect recorded command | read-only flags, no bypass, filtered sandbox/search, cleanup on failure, probes denied | build_codex_exec_cmd, flow policy | — |
| A10 | final | automated TAP-10 + reexport test | run story26 smoke; run reexport test | smoke rc=0; rf.explain_flow is cure_commands.explain_flow | exports, selftest | — |

## Discovery Notes
- Codex sessions are single rollout JSONL files: `CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl`; first line `session_meta` carries `payload.id`/`cwd`/`originator`; resume locates by scanning (no index dependency).
- codex 0.144.6 has no `--fork`; a fork is a byte-copy with every occurrence of the base uuid rewritten. `codex exec resume <id> [flags] --json -o <out> <prompt>` works with the prompt as a trailing positional (no `--`, `-C`, or `--add-dir` on the resume subcommand).
- `run_llm_exec` in cure.py:2256 is a dead local copy shadowed by the bottom-of-file `from cure_llm import run_llm_exec`; the effective implementation lives in cure_llm.py.
- `load_builtin_prompt_text(name)` joins the name as-is — the prompts package files carry `.md`, so callers must pass `"explain.md"`.
- The pr flow records resume info at `meta.llm.resume.session_id` (and `meta.codex.resume`); explain must read it but never overwrite it (`interactive` gates on it).
- `_find_codex_session_log_by_id` (cure_llm.py) already locates base rollouts via created/completed date windows.

## Critical Files
| Path | Planned role |
|------|--------------|
| `cure.py::_explain_flow_impl` + `_recorded_resume_session_id` | command flow: target resolution, fork decision, prompt modes, explains entry |
| `cure.py::build_parser` / `main()` | explain subparser (`pr_url`, `--explain-prompt`, llm overrides) + dispatch |
| `cure_llm.py::fork_codex_session` | session-store fork (copy + uuid rewrite), ReviewflowError on missing base |
| `cure_llm.py::{build_codex_exec_cmd,run_codex_exec,run_llm_exec}` | `resume_session_id` plumbing → `codex exec resume` branch |
| `cure_commands.py::{explain_flow,build_commands_catalog_payload}` | wrapper + catalog entry |
| `prompts/explain.md` | builtin default prompt (new) |
| `tests/_reviewflow_unittest_explain.py` | 31 obligations incl. fork/fallback owners (new) |

## Implementation Notes
- Executed under the agentic-workflow-cycle protocol: A_I (decomposition + research +
  Gate 1 human decisions), A_R (design + obligations), B (RED 9 → GREEN 10, then
  fork mode RED 3 → GREEN 16). Full suite 756 → 762; ruff + py_compile clean.- Red-first seams: `_explain_flow_impl` tests with mocked `run_llm_exec`; fork tests
  against a tmp `CODEX_HOME` with a fake base rollout.
- Real verification: one-shot inline run (07:12, builtin prompt) and resume-fork run
  (07:56, custom prompt) against the completed PR21 session; base rollout sha256
  unchanged; meta entries recorded.
- Constraints: fork mode requires codex provider + intact base rollout; env
  `CODEX_HOME` honored (else `~/.codex`).
- PR #37 review remediation (2026-08-10): RED 9 → GREEN after read-only runtime
  (sandbox_mode + no bypass + approval None), output-controller streaming, fork
  I/O fallback, resume flag whitelist + skip-git retry, extended cleanup span +
  staging rollback, unique artifact names + meta file_lock, story26 smoke catalog,
  exports, and failure-scoped fork deletion. Suite 762 → 770; selftest smoke rc=0;
  real-run probes (write + `gh api user`) denied by sandbox, live stderr streaming,
  base sha unchanged.

## Locked Decisions
- D1 (Gate 1): target = positional `<PR_URL>` → most recent completed review session.
- D2 (Gate 1): builtin default prompt (`prompts/explain.md`), overridable via
  `--explain-prompt`; prompt optional. Rejected: `--prompt/--prompt-file` mirror of `cure pr`.
- D3 (Gate 1): output always streams unless `--quiet`/`--no-stream`. Rejected: one-shot print.
- D4 (human): explain must run on a **fork** of the base codex session, never the
  base, so `interactive` keeps gating the pristine post-review state. Rejected:
  direct `codex resume <base>` (would consume the pristine state).
- D5: fork failure (missing base, non-codex provider, no resume info) → transparent
  inline fallback (review text appended), not an error.
- D6: explains entries record `resume: {mode, base_session_id, fork_session_id}`;
  `meta.llm.resume`/`meta.codex.resume` are never modified by explain.
- D7 (PR#37 review): codex runs are read-only — `sandbox_mode="read-only"` always,
  never `--dangerously-bypass-approvals-and-sandbox`, no `-a`; resume command
  filters config flags to the `codex exec resume`-compatible subset (`-m`/`-c`)
  and honors `--skip-git-repo-check` on the retry path.
- D8 (PR#37 review): staged-credential cleanup spans the whole post-staging span;
  `_stage_review_auth_support` rolls back partial staging on failure; fork rollouts
  are deleted when the run fails; artifacts use `explain-<ts>-<uuid8>.md` and the
  meta append runs under `file_lock` with a fresh reload.
- D9 (PR#37 review): streaming requires an active output controller — the flow
  registers `ReviewflowOutput` (ui off) so display lines reach stderr during runs.
- D10 (PR#37 re-review 2026-08-11): explain is checkout-read-only — auth staging
  skips `rf-jira` (`stage_rf_jira=False`); explanation artifacts bypass the
  review normalizer (`normalize_artifact=False`); persisted session paths are
  validated for session-dir containment before any read/stage.
- D11 (PR#37 re-review 2026-08-11): explanation provenance lives per `explains[]`
  entry (provider/model/preset/transport/usage); the review's top-level
  `meta.llm` block is never mutated by explain.
- D12 (PR#37 re-review 2026-08-11): explain progress uses `SessionProgress`
  merge-under-lock mode (cross-process safe flushes); `fork_codex_session`
  removes partially written rollouts on I/O failure; codex `error` items render
  as `Codex notice:` live lines.
- D13 (PR#37 follow-up 2026-08-11): fork-mode prompts are prepended with
  `EXPLAIN_RESUME_CONTEXT_NOTE` (review already in context; never re-produce it)
  because the inline template's "below" framing is false in resume mode.
- D14 (PR#37 follow-up 2026-08-11): `CodexJsonEventSink` never force-consumes
  partial lines in `flush()` (run.py flushes after every pipe read); the final
  partial line is consumed by `drain()` when the stream ends — huge single-line
  JSON events render as compacted text instead of raw-JSON fragments.
- D15 (PR#37 review 2026-08-11): the read-only flows never touch the repo
  checkout — the rf-jira helper is staged at `work_dir / "rf-jira"` (it is
  invoked by absolute path and reads credentials purely from env), never at
  `<repo>/rf-jira`; `_stage_review_auth_support` no longer takes a `repo_dir`
  param at all, so a future staging step cannot silently write into the repo.
- D16 (PR#37 review 2026-08-11): meta.json cross-process exclusion lives on a
  stable sidecar `meta.json.lock` (never replaced), because flushing replaces
  meta.json with a new filesystem object and a lock on the file itself would
  let concurrent processes lock different versions of the same path; every
  meta write uses a unique temp file (mkstemp) + atomic os.replace so
  concurrent `explains[]` appends can never truncate each other's pending
  write.
- D17 (PR#37 review 2026-08-11): credentials are staged per run into a
  private `work_dir/.auth-<uuid>` dir registered before copying — concurrent
  explains of the same session cannot delete each other's live credentials
  (prepare steps rmtree their destination), and partial copies are always
  cleaned.
- D18 (PR#37 review 2026-08-11): codex stderr never enters the JSON event
  stream — `run_cmd(stderr_stream=...)` routes diagnostics to the display
  log/terminal, so a warning landing between chunks of a large JSON event
  cannot corrupt parsing, live callbacks, artifact recovery, or the events
  log.
- D19 (PR#37 review 2026-08-11): malformed codex rollouts (valid JSON that is
  not an object) are unusable rollouts — inline fallback, never a
  programming error; every `transport = "http"` preset block gets the HTTP
  removal message regardless of provider name; read-only denial is proven by
  a fake-sandbox unit test through the real exec path plus a live gated
  proof (`CURE_RUN_LIVE_READONLY=1`) that a real `codex exec --sandbox
  read-only` blocks a write; the pre-HTTP-removal remediation history is
  marked superseded.

## PR #37 Review Remediation (2026-08-11)
> SUPERSEDED (2026-08-11, 2a47962): this section predates the HTTP provider
> removal — statements about HTTP providers staying available and about
> `run_http_response_exec` describe behavior that no longer exists. CURe is
> codex-only; every HTTP transport block (any provider name) is rejected with
> the removal message, and `run_http_response_exec` was deleted.
- Streaming reality: codex `exec --json`/`exec resume --json` emits whole completed
  items, not token deltas — a single-message explain run has nothing to render
  until the answer item completes (observed 5-event run). Amended A5/S8 to
  item-granular wording; sink now renders codex `error` items as `Codex notice:`
  lines (surfaced the model-mismatch warning live). HTTP providers stay one-shot
  (superseded: removed in 2a47962 — see note above).
- Read-only fix: explain stages auth with `stage_rf_jira=False` — no `rf-jira`
  write into the sandbox repo checkout, no risk of overwriting/deleting a
  pre-existing root `rf-jira` (RED → GREEN).
- Prose preservation: `run_llm_exec`/`run_codex_exec`/`run_http_response_exec`
  gained `normalize_artifact` (default True for the review pipeline); explain
  passes False so the free-form explanation is never rewritten by the
  review-shaped normalizer. (`run_http_response_exec` was later removed in
  2a47962 — see the superseded note above.)
- Provenance: each `explains[]` entry records provider/model/preset/transport and
  normalized usage; explain no longer merges usage into the review's top-level
  `meta.llm`.
- Input containment: persisted `meta.paths` repo_dir/work_dir/review_md must
  resolve inside the session dir (`_session_path_within`), else ReviewflowError.
- Concurrency: `SessionProgress(merge_under_lock=True)` for explain — progress
  flushes overlay only progress-owned keys on a fresh reload under `file_lock`,
  so a stale snapshot can no longer erase a concurrent `explains[]` append.
- Fork hygiene: `fork_codex_session` unlinks a partially written rollout on
  write failure (partial file never left in CODEX_HOME).
- OpenSpec: `--pr` examples corrected to the positional shape; suite counts
  16 → 31. Suite 770 → 771; ruff + py_compile clean.
- Follow-up (2026-08-11, second user report): fork-mode prompt now carries
  `EXPLAIN_RESUME_CONTEXT_NOTE` (review is in context, must not be re-produced —
  the model had re-emitted the whole review); `CodexJsonEventSink.flush()` no
  longer force-consumes partial lines so large events split across pipe reads
  render as compacted text, with `drain()` for the stream tail. Suite 771 → 774.

## Plan Review Log
<!-- Empty; plan review pending operator's checkpoint approval of this draft. -->

