# Tasks: cure-chunkhound-daemon-aware-research-calls

## Setup & Prerequisites

- [x] Add public-facade RED tests for A1–A25 through `tests/_reviewflow_unittest_daemon_aware_impl.py`.
- [x] Add executable fake ChunkHound and fake provider fixtures recording bootstrap, pre-existing/unattested/newly-owned generation state, exact probed config/runtime identity, concurrency, environment, failure, close, and cleanup.
- [x] Add RED tests for static eligibility, explicit environment, receipt schema/projection identity, sealed lossless final-index capture in normal/public-quiet/explicit-no-stream modes, strict all-occurrence summary/native payload shapes, bounded-memory capture/replay, unchanged live/no-live display, keeper state transitions, helper parity, and targeted Ctrl-C process-group ownership.
- [x] Define tested route eligibility, required `search`/`code_research`/`daemon_status` capability, per-startup rejection of pre-existing/unattested same-root generations, post-open newly opened CURe-owned generation proof under the probed exact config/runtime identity, `ExpectedSessionReceiptV1`, raw summary failure matrix, non-empty witness, zero-chunk adjudication, DB-release, and redaction contracts.
- [x] Add real subprocess fixtures for provider/direct-preflight Ctrl-C after child creation before publication, deterministic spawn-lock-first and close-lock-first interleavings, cooperative/TERM-ignoring/pipe-holding descendants, and an untagged sentinel.

## Core Implementation

- [x] Extend `JsonRpcSession` with an immutable explicit environment and curated-PATH executable resolution.
- [x] Extract canonical MCP bootstrap and refactor ordinary preflight through it.
- [x] Implement `ChunkHoundDaemonLease` in `cure_chunkhound_lifecycle.py`.
- [x] Add explicit route classification: supported Linux Codex helper routes require the keeper, unsupported helper-bearing routes fail before model work, and keeper-ineligible routes bypass unchanged.
- [x] Complete supported indexed helper route readiness on one retained owned lease/generation: boundedly wait only for exact transient `status="initializing"` plus `query_ready=false`, rechecking liveness and generation on every probe, before witness search, helper preflight, optional orientation, or any other model dispatch; do not close/reopen or rerun daemon-log startup preconditions after native creation.
- [x] Add the final-index-only optional `lossless_capture` forwarding seam through `ReviewflowOutput.run_logged_cmd`/`run_cmd`; make capture presence force stdout/stderr pump transport independently of the user-visible `stream` boolean, tee to separate mode-0600 private spools before bounded-tail eviction, forward live only when `stream=True`, replay sealed silent-mode output in bounded chunks through the existing post-completion log/progress path, seal after both pumps join/exit, consume only the final successful attempt, and dispose every attempt on all paths without complete in-memory materialization.
- [x] Keep bounded `CommandResult` tails and permissive `ChunkhoundLiveProgressReporter` summaries display-only; reject capture write/pump/seal/read/replay-integrity/disposal faults and missing/conflicting/malformed/error recognized occurrences anywhere in the complete streams, plus malformed native status/search payloads, at the authoritative receipt/readiness boundary.
- [x] Integrate one keeper into fresh standard, big, and multipass `_pr_flow_impl`.
- [x] Retain the keeper across concurrent workers, retries, gaps, and synthesis.
- [x] Preserve safe-boundary health checks and post-dispatch no-replay handling while making readiness timeout, degraded/malformed payload, transport/liveness loss, and generation change terminal fail-closed paths with one owned cleanup; retain exactly one retry only for typed `PreNativeSpawnLeaseOpenError` before native spawn and before any helper/model dispatch, never for a retained transiently initializing generation.
- [x] Add `OwnedProcessRegistry` OPEN/CLOSING/CLOSED lock-and-condition ownership in `run.py` for exactly `review-provider` and `chunkhound-helper`: serialize state check + Linux process-group creation + publication against the terminal snapshot, locally drain a child interrupted before publication, reject close-first spawn before `Popen`, make the first terminator own cleanup, and retain fixed 5s TERM/2s KILL/2s drain behavior.
- [x] Thread the optional registry only through supported fresh `_pr_flow_impl` → `cure_llm.py` → `cure_output.py`/`run.py` provider calls and direct helper preflight; prove resume/follow-up, HTTP, indexing, Git, Jira, and untagged `run_cmd` behavior unchanged.
- [x] Implement nested ordered cleanup with idempotent close, bounded release observation, and unconditional sensitive cleanup.
- [x] Preserve helper interface, timeout, heartbeat, output, prompt, and proof contracts.

## Verification & Proof

- [x] Extend TAP-02/TAP-03 deterministic proof with exact initializing/false→ready/true status sequences on one lease/generation; assert one open and pre-spawn validation, no close/reopen or daemon-log precondition rerun, no helper/model/search before ready, one witness search after ready, and bounded timeout plus degraded/malformed/transport/liveness/generation-change fail-closed cleanup, then keep the existing A1–A15 matrices green.
- [x] Turn A16–A21 helper mapping/output/timeout/heartbeat/prompt/tool-proof parity tests green.
- [x] Turn deterministic TAP-02/TAP-03 A22 generation-rejection proof and TAP-06 static/config/manifest proof green: permit creation of the absent canonical-root `.chunkhound/` directory plus regular `daemon.log`, and add the exact parent-present/log-absent case that permits only the regular log while preserving parent type/mode/content metadata and all siblings; require a pre-existing log to remain fully immutable, reject a symlink/non-directory parent and every other pre-existing reviewed-root path/type/mode/symlink/content change, and every operator-checkout change; inject/dedupe exact `**/.chunkhound/**`; fail closed on every stale, malformed, degraded, or non-excluding startup/config/runtime effective-filter probe; reject every seeded/pre-existing/unattested same-root generation; and after open require only the newly opened CURe-owned generation under the probed exact config/runtime identity, closing/failing before helper/model on mismatch.
- [x] Prove eight-client overlap rather than sequential completion.
- [x] Replace TAP-05's test-only readiness polling with the production retained-lease primitive and rerun exactly four enabled no-LLM installed-ChunkHound clean-start cases. Preserve non-empty/zero × absent/existing-parent A22 proof while adding one open/pre-spawn validation, one lease/generation through bounded readiness, no close/reopen or pre-ready search, and final release; the prior four-case PASS remains historical, and the latest production-route rerun passed all four cases.
- [x] Extend the isolated-wheel TAP-07 lifecycle-only smoke with proportionate delayed-ready and never-ready fake MCP cases using the installed production primitive: prove initializing/false→ready/true on one lease/generation with no pre-ready search, and bounded timeout closes once with no keeper process or DB-lock residue; preserve checkout isolation and the existing separately owned A23–A25 cleanup cases without claiming installed CLI `_pr_flow_impl` execution. TAP-03 owns zero pre-ready helper/model dispatch.
- [x] Add release-workflow ownership tests.
- [x] After the readiness correction, run focused TAP-02/TAP-03/TAP-05/TAP-07 tests, full pytest, Ruff, configured mypy, scoped mypy, isolated build, Twine, and wheel smoke.

## Integration & Cleanup

- [x] Package and bundle `cure_chunkhound_lifecycle`.
- [x] Document eligibility, keeper lifetime, failure behavior, cleanup, privacy, and exclusions.
- [x] Preserve the locked 5s TERM/2s KILL/2s process-drain budgets and use the separate 600-second native-readiness deadline with a 0.5-second poll interval, calibrated against observed installed-runtime warm readiness (about 128 seconds), while retaining the separate 60-second witness-search timeout and timeout fail-closed cleanup.
- [x] Audit all lifecycle output recursively for seeded secrets.
- [x] Reconcile current completion evidence and affected A1–A25 proof rows only after deterministic retained-readiness proof, the production-primitive TAP-05 rerun, installed-wheel coverage, broad gates, and independent review pass; do not mark the story done before then.
