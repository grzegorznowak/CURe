# Story — cure-chunkhound-daemon-aware-research-calls

Plan: 🟢 PLAN APPROVED
Status: ✅ DONE

> Story scaffolded by `/openspec-story-plan` after interactive planning.

## Purpose

Keep one initialized ChunkHound daemon generation available throughout each
supported indexed Linux standard, big, or multipass CURe review command while
retaining the generated helper and its independent native MCP calls. Successive
and concurrent research calls reuse the initialized backend without zero-client
cold restarts.

## Actors

- **Primary: CURe operator** — runs an indexed Linux standard, big, or multipass review.
- **Supporting: Review agent** — invokes generated-helper `search` and `research`.
- **Supporting: CURe review orchestrator** — owns keeper lifecycle and cleanup.
- **Supporting: Generated `cure-chunkhound` helper** — provides the existing access and policy contract.
- **Supporting: ChunkHound proxy and daemon** — provide native MCP clients and the shared backend.
- **Reviewer: CURe maintainer** — verifies lifecycle, concurrency, cleanup, packaging, and privacy evidence.

## Triggering Need

The generated helper already launches native `chunkhound mcp`, but each helper
proxy is short-lived. The installed daemon defaults to immediate shutdown after
its final client disconnects. Gaps between preflight, sequential calls,
multipass phases, and retries can therefore repeatedly cold-start the backend.

A parent-owned ordinary MCP proxy is the smallest mechanism that removes those
zero-client gaps without replacing the helper or creating a CURe-owned query
broker.

## Expected Prerequisites

- Initiative `cure-chunkhound-daemon-keeper` exists.
- Existing `cure_chunkhound.py` MCP and JSON-RPC primitives remain available.
- Existing fresh-review indexing and top-up behavior remains authoritative.
- The installed ChunkHound runtime provides supported native proxy/daemon behavior.
- Resume and follow-up are being deprecated separately and are not dependencies.

## Scope

- Fresh Linux `cure pr` with review and indexing enabled.
- Codex CLI/helper runtime.
- Standard/default, big single-pass, and initial multipass routes.
- Static eligibility before any model invocation.
- Final indexing and one versioned immutable expected-session receipt, including its exact launch-identity projection, from a lossless per-invocation raw-authority capture before keeper startup.
- Final-top-up capture transport separated from user-visible streaming: normal mode tees and displays live; public `--quiet` and explicit `--no-stream` use the same bounded-memory pump/spool authority without live user-visible lines, then preserve the existing post-completion log/progress handling.
- Required native `daemon_status` health and expected-session adjudication.
- A deterministic path-constrained search witness for non-empty indexes, with an explicit zero-chunk receipt branch.
- Existing helper preflight before optional orientation or any other model invocation.
- One parent-owned keeper across all review phases.
- Up to eight independent concurrent multipass helper clients.
- Canonical keeper/helper launch identity and curated environment.
- Startup, health, loss, cleanup, and privacy-safe lifecycle metadata.
- One bounded startup retry before any model work.
- No replay after dispatch may have occurred.
- Narrowly tagged Linux provider/helper process-group ownership, with synchronized spawn publication/registry closing and bounded TERM/KILL/drain cleanup for Ctrl-C and terminal faults.
- Real installed-ChunkHound and installed-wheel proof.
- Exact creation-only source boundary: native lifecycle may create an absent canonical indexed-root `.chunkhound/` directory as needed and its initially absent regular `daemon.log`; when the parent already exists as a real directory and the log is absent, lifecycle creates only the log while preserving parent metadata and siblings; pre-existing logs remain fully immutable and invalid parents fail closed, and every other pre-existing reviewed-root entry and every operator-checkout entry remains immutable.
- CURe-owned materialized-config injection/deduplication of exact `**/.chunkhound/**`, a fail-closed non-degraded installed-runtime effective-filter probe on every startup attempt/config/runtime identity bound to rejection of every pre-existing/unattested same-root generation and use only of the CURe-owned generation newly opened under that probed identity, and proof that daemon-log bytes cannot influence corpus, search, research, readiness, witness, receipt, or identity.

## Out of Scope

- Resume and follow-up routes.
- Interactive review.
- Windows and macOS.
- `cure doctor`.
- `--no-index` and `--no-review` keeper behavior.
- HTTP or other runtimes that do not stage the helper.
- Direct Codex-native MCP configuration.
- Generated-helper removal.
- Prompt-template changes.
- Daemon TTL.
- Private ChunkHound IPC.
- A CURe broker, proxy pool, or query serializer.
- Cross-command persistence or locking.
- PID/root-based daemon killing.
- Tool-call or model replay.
- Broad scheduler redesign.
- A new general-purpose model-write sandbox.

## Scenarios / Behavior Examples

### S1 — Keeper opens before every model boundary

Given a supported indexed helper review, when CURe prepares model work, then it
records final index/receipt readiness, keeper native-health and expected-session
readiness, independent helper preflight, and first model dispatch—including
optional orientation—in order.

Covers: A1

### S2 — Sequential calls reuse one daemon generation

Given a held keeper, when separate helper calls execute across an idle gap, then
the helper proxies observe one daemon generation without backend reinitialization.

Covers: A2

### S3 — Review phase gaps retain the keeper

Given standard, big, or multipass work, when execution crosses applicable phase
and retry boundaries, then the same keeper remains held until review-agent work ends.

Covers: A3

### S4 — Concurrent clients remain independent

Given eight effective multipass workers, when their helper calls overlap, then
eight independent proxies use one daemon generation without CURe serialization.

Covers: A4

### S5 — Keeper and helpers share one launch identity

Given one review runtime, when keeper and helper proxies launch, then their
resolved executable, canonical root, config, database, and cwd identity matches.

Covers: A5

### S6 — Keeper and helpers share one curated environment

Given unrelated parent values, when keeper and helper proxies launch, then both
receive the same immutable allowlisted environment and exclude those values.

Covers: A6

### S7 — Supported routes require the keeper

Given a fresh indexed Linux Codex helper route in standard, big, or multipass
mode, when route eligibility resolves, then CURe marks keeper acquisition mandatory.

Covers: A7

### S8 — Unsupported helper routes fail before model work

Given an indexed helper-bearing route on an unsupported platform or runtime,
when static eligibility resolves, then CURe fails before any model invocation.

Covers: A8

### S9 — Keeper-ineligible routes bypass unchanged

Given an HTTP/non-helper, `--no-index`, or `--no-review` route, when eligibility
resolves, then CURe starts no keeper and preserves that route's existing behavior.

Covers: A9

### S10 — Capability and readiness failures fail closed

Given an eligible route with missing tools, unhealthy/degraded native status,
failed expected-session adjudication, identity mismatch, any pre-existing or
unattested same-root generation, or failure to prove the newly opened CURe-owned
generation under the attempt's probed exact config/runtime identity, when dynamic
gating runs, then CURe closes any opened mismatch, dispatches no helper or model,
including optional orientation, and does not use a cold-start fallback.

Covers: A10

### S11 — The expected session is adjudicated

Given successful final indexing and keeper acquisition in normal streaming,
public `--quiet`, or explicit `--no-stream` mode, when CURe validates readiness,
then final-top-up-only capture transport uses stdout/stderr pumps in every mode
and strict parsing of their sealed lossless capture constructs one versioned
immutable receipt whose launch-identity projection exactly matches the keeper.
Normal mode alone forwards pump chunks to the live user sink; quiet/no-stream
suppress live lines and preserve the existing post-completion log/progress
handling by bounded-chunk replay from the sealed private spools. Bounded
display/command-result tails never authorize the receipt. A non-empty receipt
additionally returns the deterministic expected path/literal through well-formed
native `search`; an authoritative zero-chunk receipt uses only the bounded
receipt/identity/current-attempt newly opened CURe-owned generation branch under
the probed exact config/runtime identity. In every display mode, missing,
malformed, conflicting, or error-bearing indexing evidence, malformed native
payloads, capture-integrity or receipt-construction failure, and a non-empty
receipt without a valid witness all fail before model work; every attempt's
spools are disposed.

Covers: A11

### S12 — Mid-review loss is not replayed

Given work may already have been dispatched, when keeper or daemon continuity is
lost, then CURe records infrastructure failure without restarting or replaying work.

Covers: A12

### S13 — Cleanup follows resource ownership

Given any terminal path, including Ctrl-C during child creation or publication,
when review execution unwinds, then the registry's synchronized closing protocol
prevents post-snapshot publication and only explicitly tagged provider/helper
process groups and their descendants receive bounded TERM, KILL if needed, and
pipe/reap drain before one keeper close, followed by bounded daemon/DB release
observation. Untagged generic commands retain their existing behavior.

Covers: A13

### S14 — Teardown failure cannot skip sensitive cleanup

Given keeper close or release observation fails, when cleanup continues, then
sensitive staged state is still removed and the teardown failure remains visible.

Covers: A14

### S15 — Diagnostics remain privacy-safe

Given secret-bearing lifecycle failures, when CURe renders or persists them,
then credentials, raw environments, auth material, and sensitive stderr are absent.

Covers: A15

### S16 — Helper tool mapping remains stable

Given keeper-enabled execution, when the helper runs `search` or `research`,
then it preserves the existing mapping to native `search` and `code_research`.

Covers: A16

### S17 — Helper output remains stable

Given any helper outcome, when the helper emits its result, then its structured
JSON contract remains compatible with the pre-change contract.

Covers: A17

### S18 — Helper timeouts remain stable

Given helper preflight, search, or research work, when a stage reaches its
budget, then existing timeout behavior remains unchanged.

Covers: A18

### S19 — Helper heartbeat remains stable

Given a long helper operation, when five seconds pass without completion, then
the existing heartbeat behavior remains unchanged.

Covers: A19

### S20 — Prompt instructions remain stable

Given built-in helper-capable review prompts, when rendered, then their helper-use
instructions remain unchanged by keeper integration.

Covers: A20

### S21 — Tool-proof semantics remain stable

Given helper evidence from review work, when proof validation runs, then the
existing accepted and rejected helper-evidence behavior remains unchanged.

Covers: A21

### S22 — Lifecycle machinery preserves source boundaries

Given canonical before manifests, when keeper lifecycle paths execute, then the
only permitted reviewed-root delta is native creation of the initially absent
regular canonical indexed-root `.chunkhound/daemon.log`, creating its parent as
a directory only when absent. When the parent already exists as a real directory
and the log is absent, only the log is created while parent type, mode, content
metadata, and every sibling remain identical. A pre-existing log remains fully immutable; a symlink/non-directory parent fails
closed; every other pre-existing reviewed-root entry and every operator-checkout
entry is immutable. CURe injects/deduplicates exact
`**/.chunkhound/**`, fails closed unless a non-degraded installed-runtime
effective-filter probe demonstrates it for every startup attempt/config/runtime
identity, rejects every pre-existing/unattested same-root generation, requires
the CURe-owned generation newly opened under that probed identity, and excludes
daemon-log bytes from corpus, search, research, readiness, witness, receipt, and
identity evidence.

Covers: A22

### S23 — Installed wheel executes the lifecycle

Given an isolated installed wheel, when fake external executables drive an
eligible review, then the installed `cure` command completes the keeper lifecycle.

Covers: A23

### S24 — Installed-wheel proof is checkout-isolated

Given the wheel smoke runs outside the checkout with `PYTHONPATH` unset, when
CURe imports, then no source-checkout module is loaded.

Covers: A24

### S25 — Installed-wheel cleanup leaves no owned residue

Given the wheel lifecycle completes, fails, or receives Ctrl-C during provider
or direct helper-preflight work, when its smoke exits, then no registered
provider/helper descendant, keeper process, or database lock remains.

Covers: A25

## Acceptance

**A1:** Supported indexed helper execution records `final-index/receipt-ready → keeper-native-health/expected-session-ready → helper-preflight → first model` in order, including optional orientation as model work.

**A2:** Sequential helper calls during one held interval observe one daemon generation and no backend reinitialization.

**A3:** One keeper remains continuously held across all applicable standard, big, or multipass phases and retries.

**A4:** Eight helper clients demonstrably overlap against one daemon generation without CURe-side serialization.

**A5:** Every keeper and helper launch in one review equals the immutable receipt's complete launch-identity projection: resolved executable, canonical root, resolved config path and digest, resolved database path, cwd, curated-environment key set, and non-reversible environment equality digest.

**A6:** Every keeper and helper MCP child receives an equal immutable curated environment with unrelated inherited values absent.

**A7:** Every fresh indexed Linux Codex helper route in standard, big, or multipass mode requires keeper acquisition.

**A8:** Every indexed helper-bearing unsupported platform/runtime fails before its first model invocation.

**A9:** Every HTTP/non-helper, `--no-index`, and `--no-review` route remains keeper-free and behaviorally unchanged.

**A10:** Missing capability, unhealthy/degraded native status, failed expected-session adjudication, identity mismatch, any pre-existing/unattested same-root generation, or failure to prove the newly opened CURe-owned generation under the current attempt's probed exact config/runtime identity prevents every model dispatch without cold-start fallback; any opened mismatch is closed.

**A11:** In normal streaming, public `--quiet`, and explicit `--no-stream` fresh-review routes, readiness requires a successful final indexing invocation whose complete stdout/stderr is teed before bounded-tail eviction into a sealed, lossless, per-attempt raw-authority capture. Supplying that final-top-up-only capture forces bounded-memory pump transport independently of the existing user-visible `stream` boolean: normal streaming forwards pump chunks live, while quiet/no-stream forwards no live user lines and replays the sealed spools in bounded chunks only through the existing post-completion log/progress path. Only the capture plus exit code may construct one immutable versioned receipt; bounded `CommandResult` tails and progress summaries are display/diagnostic evidence only, and no unbounded in-memory authority path is permitted. In every mode, missing or conflicting counts, malformed recognized summary fields (including occurrences earlier than or beyond `capture_tail_chars`), missing or nonzero indexing errors, nonzero indexing exit, capture write/pump/seal/read failure, canonicalization/digest/receipt-construction failure, or malformed status/search payload fails before keeper/model work and every attempt is disposed. Healthy well-formed native `daemon_status` and exact keeper-to-receipt launch-projection equality are required. A positive final chunk count requires the deterministic expected path/literal through keeper-held native `search`; authoritative zero requires the bounded exact-identity branch plus the current attempt's newly opened CURe-owned generation under the probed exact config/runtime identity, and an empty result never proves a non-empty index.

**A12:** Keeper or daemon loss after possible dispatch records infrastructure failure without CURe-initiated restart or replay.

**A13:** Every terminal path, including Ctrl-C while a provider or direct helper-preflight child is being created or published, uses one synchronized `OwnedProcessRegistry` OPEN → CLOSING → CLOSED protocol: spawn creation/publication is serialized with the closing transition, no spawn may publish after the terminal snapshot, a child interrupted before publication is locally terminated/drained, and a spawn attempted after closing begins is rejected before `Popen`. The resulting registered `review-provider` or `chunkhound-helper` Linux process groups and descendants receive 5-second TERM, 2-second KILL, and 2-second pipe/reap-drain budgets before exactly one keeper close and bounded daemon/database release observation; untagged `run_cmd` callers are unchanged.

**A14:** Sensitive staged-state cleanup executes despite close/release failure, and the teardown failure remains reportable.

**A15:** Lifecycle diagnostics contain no credential, raw environment, daemon authentication material, or unredacted sensitive stderr.

**A16:** Helper `search` and `research` retain their existing native tool mapping.

**A17:** Helper success and failure output retain the existing structured JSON contract.

**A18:** Helper preflight, search, and research retain their existing timeout behavior.

**A19:** Long helper operations retain the existing five-second heartbeat behavior.

**A20:** Built-in helper-capable prompt instructions remain unchanged.

**A21:** Existing helper tool-proof acceptance and rejection semantics remain unchanged.

**A22:** Native daemon lifecycle may create the initially absent regular `<canonical-indexed-root>/.chunkhound/daemon.log`, creating its `.chunkhound/` parent as a directory only when that parent is absent. In the exact parent-present/log-absent case, the parent must be a real directory and lifecycle may create only the regular log while preserving parent type, mode, content metadata, and every sibling. A pre-existing log is fully immutable; a symlink or non-directory parent fails closed; every other pre-existing reviewed-root entry and every operator-checkout entry remains identical in path, type, mode, symlink target, and content, with no append, truncation, rewrite, chmod, replacement, deletion, or other child/artifact. CURe's materialized config contains exactly one deduplicated `**/.chunkhound/**`, and every startup attempt fails closed unless a non-degraded installed-runtime effective-filter probe tied to the exact config and runtime identity demonstrates exclusion, every pre-existing/unattested same-root generation is rejected, and after open the generation is newly opened and owned by CURe under that exact probed identity; otherwise CURe closes and fails before helper/model work. The daemon log contributes to no corpus/index state, search, research, readiness, witness, receipt, launch/generation identity, or expected-session identity/adjudication evidence.

**A23:** An isolated installed wheel completes an eligible keeper/helper lifecycle through the installed `cure` executable.

**A24:** Installed-wheel smoke loads no CURe module from the source checkout.

**A25:** Installed-wheel success, failure, Ctrl-C-at-publication, and spawn-versus-terminate lifecycle interleavings leave no created or registered provider/helper descendant, keeper process, or database lock.

## Verification

### Verification Commands

```bash
python -m pytest \
  tests/test_reviewflow_unittest.py::ChunkHoundKeeperRuntimeTests \
  tests/test_reviewflow_unittest.py::ChunkHoundDaemonLeaseTests \
  tests/test_reviewflow_unittest.py::DaemonAwareResearchCallFlowTests \
  tests/test_reviewflow_unittest.py::ChunkHoundToolProofValidationTests \
  -v

python -m pytest \
  tests/test_chunkhound_daemon_aware_source.py \
  tests/test_release_workflow_unittest.py \
  -k 'chunkhound or daemon_aware_research_calls' \
  -v

CURE_RUN_LIVE_CHUNKHOUND=1 \
python -m pytest tests/test_daemon_aware_chunkhound_live.py -v

python -m pytest
ruff check .
mypy
mypy cure_chunkhound.py cure_chunkhound_lifecycle.py run.py

tmp_root="$(mktemp -d)"
python -m venv "$tmp_root/build-venv"
"$tmp_root/build-venv/bin/python" -m pip install --upgrade build twine
"$tmp_root/build-venv/bin/python" -m build --outdir "$tmp_root/dist"
"$tmp_root/build-venv/bin/python" -m twine check "$tmp_root"/dist/*
python -m venv "$tmp_root/smoke-venv"
"$tmp_root/smoke-venv/bin/python" -m pip install "$tmp_root"/dist/*.whl
repo_root="$PWD"
(
  cd "$tmp_root"
  env -u PYTHONPATH PYTHONSAFEPATH=1 \
    "$tmp_root/smoke-venv/bin/python" \
    "$repo_root/tests/daemon_aware_research_calls_smoke.py" \
    --cure-bin "$tmp_root/smoke-venv/bin/cure"
)
```

### Completion Evidence

- PRE-LIVE PASS — focused daemon-aware suite: 74 passed, 72 subtests.
- PRE-LIVE PASS — full suite: 918 passed, 2 skipped.
- PRE-LIVE PASS — `ruff check .`; configured mypy (9 files); scoped mypy (3 files).
- PRE-LIVE PASS — isolated sdist/wheel build, Twine checks, and external-cwd installed-wheel smoke.
- PRE-LIVE PASS — strict OpenSpec change/schema validation. The schema graph has no blocker artifact; blocked state is workflow-owned.
- PRE-LIVE PASS — unstaged and cached `git diff --check`; only `openspec/config.yaml` staged.
- PRE-LIVE PASS — independent pre-live re-review.
- HISTORICAL — INSUFFICIENT FOR A22: the prior enabled two-case live run (non-empty and zero-chunk) did not cross absent/existing-parent state with both chunk-count branches and therefore did not close A22.
- LIVE PASS — the exact enabled four-case matrix crossed non-empty/zero-chunk × absent/existing-real-parent state and passed `4 passed in 68.54s`, closing A22.

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|---|---|---|---|---|---|---|---|---|---|
| TAP-01 | Runtime unit/process | Receipt schema/projection, display-independent lossless capture, launch identity, curated environment, redaction (A5, A6, A11, A15) | `_reviewflow_unittest_daemon_aware_impl.py` exported through public façade | Real subprocess through normal streamed pumps and capture-forced silent pumps, both teed to final-index raw-authority spools before bounded-tail eviction | Versioned frozen receipt fields; complete valid summary remains authoritative beyond `capture_tail_chars` in all display modes; early malformed/conflicting recognized fields reject despite later valid tail; capture write/pump/seal/read faults reject; normal mode emits live lines, quiet/no-stream emits none and retains complete post-completion log/progress replay; bounded memory; exact launch projection; immutable env; no secret metadata | Executable emitter with valid/invalid recognized fields separated by greater-than-bound filler, temp private spools, recording live/display/log sinks, canonical/symlink paths, minimal config/DB, sentinel environment | Focused public node IDs and full pytest | Use real pumps in both visible and silent transport, deliberately small tail/replay bounds, and owner-backed private spools; never substitute normalized dictionaries, tail-only fixtures, `subprocess.run` authority, or unbounded strings | Capture/projector and display separation are isolated here; native/route adjudication remains TAP-02 |
| TAP-02 | Keeper process integration | Ordering, retention, routing gates, strict lossless receipt/status/search boundaries in normal/quiet/no-stream modes, witness/zero-chunk branches, generation-bound filter authority, loss, close, and release (A1–A3, A7–A15, A22) | Same focused module/public façade | Sealed complete final-index capture from visible or silent pump transport plus real stdio fake MCP process and OS lifecycle | Required tools; typed status/search payloads; ready vs degraded status; exact receipt projection; mode-parity for all-occurrence grammar, greater-than-bound valid/early-conflict, integrity/disposal, witness/zero branches; reject pre-existing/unattested same-root generation; require newly opened CURe-owned generation under probed exact config/runtime identity; close mismatch; no receipt/keeper/model on faults; no replay; idempotent close; bounded release | Executable fake ChunkHound parameterized across normal stream, quiet, and explicit no-stream, emitting complete/adversarial raw summaries and native payloads, pre-existing/unattested/newly-owned generation ledger, deterministic witness corpus, and crash/hang/secret modes | Focused public node IDs and full pytest | Linux-only skip for unsupported process semantics; never substitute pre-normalized dictionaries, bounded tails, mocks, or an in-memory non-stream authority for raw/process claims | Strict external shapes and generation-bound keeper adjudication stay together; transport/display mechanics remain TAP-01 and public route orchestration TAP-03 |
| TAP-03 | Fresh PR orchestration/process ownership | Standard/big/multipass, normal/quiet/explicit-no-stream routing, concurrency, race-closed provider/helper descendant cleanup, faults, exact creation-only source boundary and generation-bound effective-filter gate (A1, A3, A4, A7–A14, A22) | Same focused module/public façade | Actual `_pr_flow_impl` through final top-up, materialized config/effective-filter startup gate, `cure_output.py`/`run.py` capture transport, `cure_llm.py`, tagged registry, direct helper preflight, worker pool, and cleanup stack | Normal route uses live pump display; `--quiet` and explicit `--no-stream` select `stream=False` yet use capture-forced pumps, emit zero live user lines, preserve post-completion logs/progress, and reach identical strict receipt/adjudication; exact directory-plus-log delta when both absent and exact log-only delta when a real parent exists, with parent metadata/siblings preserved; pre-existing-log immutability, invalid-parent rejection, and operator-checkout immutability; per-attempt/config/runtime non-degraded exclusion probe; rejection of pre-existing/unattested same-root generations; newly opened CURe-owned generation under probed exact identity or close/fail before helper/model; event ordering; eight-client overlap; deterministic publication races; bounded cleanup; untagged sentinel; one keeper close after CLOSED; no replay | Temp git repo with absent-parent, existing-real-parent/log-absent, pre-existing-log, and invalid-parent `.chunkhound` cases, recording stderr/log/progress sinks, real greater-than-bound fake indexer, fake effective-filter/runtime identities and generation ledgers, fake provider/helper descendants with PID/PGID and pipe ledger, injected publication/closing barriers, fake ChunkHound, untagged sentinel | Focused public normal/quiet/no-stream flow node IDs and full pytest | Linux-only process-group tests; use exact public CLI args, canonical manifests, and tagged spawn/publication seams with deterministic barriers rather than sleeps or broad scheduler mocks | Canonical orchestration must prove all three display routes, exact manifest/filter/generation gates, both ownership callsites/orderings, interrupt-at-publication, and unrelated generic-command invariance |
| TAP-04 | Helper compatibility | Existing helper mapping, output, timeout, heartbeat, prompt, and proof contracts (A16–A21) | Focused module plus existing helper/proof tests | Generated helper through MCP and proof boundary | Mapping, budgets, heartbeat, output shape, prompts and proof unchanged | Existing fixtures plus executable fake MCP | Focused parity node ID and full pytest | Compare normalized public behavior if internal bootstrap moves | Compatibility cannot be inferred from keeper tests |
| TAP-05 | Real ChunkHound | Installed clean-start reuse, native status, expected-session continuity, exact daemon-log exclusion, source-boundary creation, and release (A2–A5, A11, A22; not A13) | `test_daemon_aware_chunkhound_live.py` | Installed ChunkHound in four disposable cases: non-empty and zero-chunk, each with absent and existing-real-parent/log-absent state; no seeded or manipulated pre-existing native generation | Immediate pre-open and pre-spawn absence; exactly one pre-spawn validation; newly lease-owned `ExpectedGenerationEvidence`; continuity through marker, native session, readiness, ordinary-client concurrency, and pre-close; final release to absence; exact `['**/.chunkhound/**']` once with effective exclusion; marker/sibling/path absence and exact creation-only source boundary; expected witness for non-empty and no invented witness for zero | Four disposable tiny repos/configs/DBs crossing non-empty/zero × absent/existing parent; unique marker supplied through the clean-start lifecycle, preserved sibling fixtures for existing-parent cases, no pre-existing native-generation seeding/manipulation, and no LLM | Enabled opt-in four-case live command | Explicit prerequisite failure/skip remains valid in ordinary runs; completion is backed by the enabled four-case PASS, while deterministic TAP-02/TAP-03 rejection proof remains mandatory | Real clean-start capability, continuity, exclusion, and boundary proof supplements deterministic generation-rejection proof; it neither proves A13 nor owns seeded/pre-existing/unattested rejection |
| TAP-06 | Source/static contract | Unchanged helper/prompt/proof surfaces (A16–A21) plus exact creation-only source boundary/config/generation gate (A22) | `test_chunkhound_daemon_aware_source.py` | Versioned source, materialized config, installed-runtime probe seam, generation ledger, and disposable reviewed-root/operator-checkout manifests | A16–A21 parity; exact absent-parent directory-plus-log and existing-real-parent log-only additions; parent type/mode/content metadata/siblings and every other pre-existing path/type/mode/symlink/content plus all operator-checkout entries immutable; pre-existing-log immutability and invalid-parent rejection; exact exclusion injected once; stale/degraded/non-excluding probe and pre-existing/unattested/mismatched generation fail closed before helper/model, closing an opened mismatch; no direct Codex MCP migration | File type/path/mode/symlink/bytes manifests, sibling fixtures, config duplicates, runtime/config identity variants, pre-existing/unattested/newly-owned generation variants, and unique marker | Direct test and full pytest | Checked-in manifest if Git metadata unavailable; never broadly ignore `.chunkhound/**` | Static invariants need direct owners distinct from the enabled installed-runtime proof |
| TAP-07 | Packaging/release | Installed lifecycle, checkout isolation, and success/failure/Ctrl-C publication-race descendant residue cleanup (A23–A25; packaging slices of A5, A13, A16–A21) | Wheel smoke and release workflow test | Built wheel outside checkout with clean import/XDG state and tagged fake provider/helper descendant groups | Installed modules, keeper/helper/PGID ledger, interrupt-at-publication and spawn-versus-terminate outcomes, TERM/KILL path, DB unlock, cleanup, no checkout import | Disposable build/smoke venvs, fake executables with cooperative/TERM-ignoring descendants, and deterministic publication barrier/control channel | Isolated build/smoke and publish workflow | Linux release workflow remains authoritative | Installed signal inheritance and publication cleanup supplement exhaustive TAP-03 interleavings |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|---|---|---|---|---|---|---|
| A1 | final | TAP-02, TAP-03 | Run keeper/flow ordering nodes including orientation-enabled route | `final-index/receipt-ready → keeper-native-health/expected-session-ready → helper-preflight → orientation-or-first-review-model` ledger with zero earlier model events | `cure.py`, lifecycle module | Lock exact event names in RED tests |
| A2 | final | TAP-02, TAP-05 | Run fake gap test and live canary | One sanitized generation ID across sequential calls | Lease, helper, daemon observation | Finalize generation observation without auth data |
| A3 | final | TAP-02, TAP-03 | Run phase-gap cases | One lease ID spans all applicable phases/retries | `_pr_flow_impl` | Pin safe health-check boundaries |
| A4 | final | TAP-03, TAP-05 | Run eight-client barriers | Eight overlapping clients and one generation | Worker pool and helper clients | Finalize deterministic overlap barrier |
| A5 | final | TAP-01, TAP-05, TAP-07 | Run receipt-projection identity tests and smoke | Keeper/helper tuples exactly equal the receipt projection across all named fields | Receipt constructor and launches | Pin serialized schema version and digest encoding in RED tests |
| A6 | final | TAP-01 | Run sentinel-environment cases | Equal allowlists; inherited sentinel absent | Session and runtime env | Finalize required environment keys |
| A7 | final | TAP-03 | Run eligible route matrix row | Every supported fresh Linux Codex route attempts keeper acquisition | Eligibility resolver | Pin standard/big/multipass route identifiers |
| A8 | final | TAP-03 | Run unsupported helper-route cases | Zero model invocations | Static eligibility | Pin supported OS/runtime capability predicate |
| A9 | final | TAP-01, TAP-03, TAP-06 | Run keeper-ineligible route cases | No keeper and unchanged route event ledger | Provider/no-index/no-review routes | Capture pre-change route behavior |
| A10 | final | TAP-02, TAP-03 | Run missing-tool, degraded-status, receipt-mismatch, witness-failure, pre-existing/unattested same-root, and newly-opened ownership/config/runtime mismatch fault nodes | Zero helper/model dispatch, including orientation, no fallback, and opened mismatch closed | Bootstrap/native-status/expected-session/identity/filter-generation gates | Pin pre-start rejection, post-open ownership/identity proof, and retryable errors |
| A11 — normal-stream receipt construction and native health | final | TAP-01, TAP-02, TAP-05 | On the normal public route, stream valid summary plus greater-than-`capture_tail_chars` filler; separately stream early malformed/conflicting recognized fields, filler, and later valid-looking fields; inject write/pump/seal/read/disposal faults; run typed/malformed `daemon_status` cases | Pump tee precedes tail/display, live lines remain visible, and sealed complete capture alone authorizes; every conflict/malformed/integrity fault yields no receipt, keeper, or model; keeper identity equals projection | Final-index visible pump/capture/seal/projector, exit code, canonical bootstrap, lease | Pin schema serialization, all-occurrence grammar, private spools, and visible-sink order in RED tests |
| A11 — quiet and explicit-no-stream receipt construction | final | TAP-01, TAP-02, TAP-03 | Run separate public `--quiet` and explicit `--no-stream` final top-ups with the same all-occurrence valid, early-conflict, malformed, error, greater-than-bound, and write/pump/seal/read/replay/disposal fault corpus | Both routes retain `stream=False` user semantics and emit no live user lines, yet capture-forced pumps/spools produce the same authority/rejection outcomes; complete output reaches only existing post-completion log/progress handling in bounded chunks; all spools are disposed and memory remains bounded | `_pr_flow_impl`, final-index owner, `ReviewflowOutput.run_logged_cmd`, `run_cmd` silent pump transport, private spools | Lock exact CLI route ledgers, zero-live-line sentinel, bounded replay chunk size, grammar parity, and disposal in RED tests |
| A11 — non-empty witness | final | TAP-02, TAP-05 | Run deterministic non-empty fake and live witness nodes | Path-constrained native `search` returns the selected Git-tracked path and literal | Witness selector, keeper session, session DB | Lock bounded candidate/token limits in RED tests |
| A11 — zero-chunk, malformed search, and no-witness failures | final | TAP-02, TAP-05 | In TAP-02 run authoritative zero acceptance, non-empty no-witness/empty-result/wrong-path/wrong-literal, malformed search/status, and stale/unattested generation nodes; in TAP-05 run clean-start zero-chunk cases without pre-existing-generation manipulation | Zero accepted only with exact projection, the current attempt's newly opened CURe-owned generation under the probed exact identity, and healthy typed status; deterministic malformed/stale/no-witness branches stop before model work; live zero cases retain clean-start continuity | Raw summary, receipt, generation adjudicator, keeper session, filter probe identity | Pin bounded candidate/token limits and deterministic generation rejection; live proof owns clean-start continuity only |
| A12 | final | TAP-02, TAP-03 | Run post-dispatch loss cases | Typed infrastructure failure with no repeated dispatch/tool event | Health checks and ledger | Pin “dispatch may have occurred” boundary |
| A13 | final | TAP-02, TAP-03 | At provider and direct-preflight seams, inject Ctrl-C after child creation before publication; deterministically run spawn-lock-first and close-lock-first interleavings with cooperative, TERM-ignoring, and pipe-holding descendants plus untagged sentinel | Unpublished interrupted child is locally drained; committed spawn is in terminal snapshot; close-first spawn is rejected before `Popen`; no publication occurs after CLOSING; no survivor/open pump; untagged command is unsignalled; registry CLOSED precedes one keeper close/release | `cure.py`, `cure_llm.py`, `cure_output.py`, `run.py`, registry lock/condition and cleanup stack | Pin Linux skip, barrier hooks, typed closing error, and monotonic timing tolerance in RED tests |
| A14 | final | TAP-02, TAP-03 | Inject close/release failures | Sensitive cleanup event plus visible teardown failure | Nested cleanup | Lock primary/teardown exception reporting form |
| A15 | final | TAP-01, TAP-02 | Run secret-bearing faults | Sentinel values absent recursively | Metadata, logs, exceptions | Enumerate persisted/rendered fields |
| A16 | final | TAP-04, TAP-06 | Run mapping parity cases | `search` and `research` map to unchanged native tools | Helper adapter | Capture pre-change mapping fixture |
| A17 | final | TAP-04 | Run output fixtures | Existing success/error JSON schemas compare equal | Helper output | Define normalized dynamic fields |
| A18 | final | TAP-04 | Run stage-timeout fixtures | Existing preflight/search/research timeout outcomes | Helper timeouts | Capture exact current budgets |
| A19 | final | TAP-04 | Run long-operation fixture | Existing five-second heartbeat cadence | Helper stderr heartbeat | Define timing tolerance |
| A20 | final | TAP-06 | Compare prompt corpus | Byte-identical built-in prompt templates | `prompts/` | Lock authoritative prompt manifest |
| A21 | final | TAP-04, TAP-06 | Run proof parity fixtures | Existing accepted/rejected helper evidence unchanged | Proof parser and fixtures | Capture canonical positive/negative corpus |
| A22 | final | TAP-02, TAP-03, TAP-05, TAP-06 | Use TAP-02/TAP-03 for seeded/pre-existing/unattested same-root rejection and post-open ownership mismatch; use TAP-06 for static/config/manifest proof; run TAP-05 as four clean-start cases crossing non-empty/zero × absent/existing parent without seeding or manipulating a pre-existing native generation | Deterministic proof rejects every pre-existing/unattested same-root generation and requires the newly opened CURe-owned generation. Live proof observes immediate pre-open/pre-spawn absence, exactly one pre-spawn validation, newly lease-owned `ExpectedGenerationEvidence`, continuity through marker/native-session/readiness/client concurrency/pre-close, release to absence, exact `['**/.chunkhound/**']` once/effective exclusion, and marker/sibling/path absence plus exact source boundary in all four cases | Config materializer/effective-filter generation gate, deterministic generation ledgers, keeper/index/cleanup, live native tools and DB/corpus evidence | Closed — enabled exact four-case proof passed `4 passed in 68.54s`; the default skips and historical two-case run are not the completion evidence |
| A23 | final | TAP-07 | Run isolated wheel smoke | Installed `cure` completes eligible lifecycle | Wheel and smoke harness | Add exact release workflow invocation |
| A24 | final | TAP-07 | Inspect smoke import origins | Every CURe module resolves under wheel venv | Isolated Python import state | Add explicit module-origin assertions |
| A25 | final | TAP-07 | Run installed success, failure, provider/helper Ctrl-C-at-publication, spawn-wins, and close-wins smoke exits | No created or registered provider/helper descendant, keeper, or DB lock remains; ledger proves local unpublished-child cleanup, snapshot inclusion or pre-`Popen` rejection, and bounded TERM/KILL path | Fake process/publication ledger and DB probe | Pin portable `/proc`/signal fallback and deterministic barrier control for Linux CI in RED tests |

### Surface / Branch Proof Matrix

| Surface | Supported Variant | Internal Execution Branch | Proof Class | Owning Proof Seam | Why This Seam Is Sufficient | Out of Scope Notes |
|---|---|---|---|---|---|---|
| Static eligibility | Fresh indexed Linux Codex helper route | Standard, big, or initial multipass | routing | TAP-03 real `_pr_flow_impl` route ledger | Proves every supported callsite selects mandatory keeper flow | Resume/follow-up excluded |
| Static eligibility | Indexed helper-bearing unsupported OS/runtime | Static reject before setup/model | routing | TAP-03 unsupported route nodes | Real orchestration ledger proves zero model invocations | Windows/macOS remain unsupported |
| Provider/bypass | HTTP/non-helper, `--no-index`, or `--no-review` | Existing keeper-ineligible branch | routing | TAP-01, TAP-03, TAP-06 | Route ledger plus static contract proves no keeper and unchanged behavior | Custom non-helper behavior is not redesigned |
| Ordering | Orientation enabled or disabled | Final index/receipt → keeper health/session → helper preflight → first model | behavior | TAP-02 component ledger; TAP-03 real-flow ledger | Component faults and canonical orchestration jointly prove no early model | None |
| Startup | First attempt or transient pre-model failure | Acquire once or one bounded retry | behavior | TAP-02 fake MCP process | Deterministic process ledger distinguishes attempts and dispatch boundary | No retry after model dispatch |
| Capability/health | Missing tool/payload field or initializing/degraded status | Fail closed | behavior | TAP-02 fake native MCP; TAP-05 live status canary | Exact native payload variants and real capability are observed | No warning-only fallback |
| Expected session | Non-empty final receipt | Deterministic path/literal witness succeeds or fails | behavior | TAP-02 fake receipt/search; TAP-05 live tiny corpus | Proves content identity through keeper-held native search | Candidate scan remains bounded |
| Expected session | Authoritative zero-chunk final receipt | Exact receipt launch projection + current attempt's newly opened CURe-owned generation under the probed exact config/runtime identity + healthy typed status | behavior | TAP-01/TAP-02 zero-chunk raw fake and stale/unattested rejection; TAP-05 two clean-start zero-chunk parent-state cases | Deterministic proof rejects stale/unattested reuse; live proof establishes clean-start expected-generation continuity without a fabricated hit | Zero search result cannot prove non-empty receipt |
| Expected session | Normal streaming final top-up with complete, missing/conflicting/malformed/error summary, recognized fields displaced beyond tails, or capture/receipt failure | Visible pumps tee to private spools before tails/live sink; accept only complete consistent authority or fail before receipt/keeper/model | behavior | TAP-01/TAP-02 greater-than-`capture_tail_chars` visible-pump matrix; TAP-03 normal-route ledger | Proves complete-stream authority while preserving current live display | No other `run_cmd` invocation opts into lossless authority capture |
| Expected session | Public `--quiet` final top-up with the same valid/adversarial corpus | `stream=False` suppresses live sink but capture presence forces silent pumps/spools; bounded post-completion replay preserves current log/progress behavior | behavior | TAP-01/TAP-02 silent-pump parity matrix; TAP-03 public `--quiet` route | Proves quiet route cannot bypass strict authority, leak live lines, or create an unbounded memory path | Ordinary non-authority commands unchanged |
| Expected session | Public explicit `--no-stream` final top-up with the same valid/adversarial corpus | `stream=False` suppresses live sink but capture presence forces silent pumps/spools; bounded post-completion replay preserves current log/progress behavior | behavior | TAP-01/TAP-02 silent-pump parity matrix; TAP-03 public `--no-stream` route | Separately proves explicit no-stream selection, authority parity, zero live lines, disposal, and bounded memory | Ordinary non-authority commands unchanged |
| Expected session | Malformed status/search, non-empty no-witness, or identity-projection mismatch | Fail before every model | behavior | TAP-02 and TAP-03 fault nodes | Raw native fault plus orchestration ledger proves fail-closed routing | None |
| Startup identity | Any pre-existing or unattested same-root daemon generation | Reject before opening; never kill | behavior | TAP-02/TAP-03 process and generation-ledger fixtures | Real subprocess ownership ledger proves no PID/root killing and zero helper/model dispatch | Private IPC excluded |
| Startup identity | Generation observed after open is not newly opened and CURe-owned under the probed exact config/runtime identity | Close the opened mismatch and fail before helper/model | behavior | TAP-02/TAP-03 generation/config/runtime identity matrix | Deterministic ownership ledger proves mismatch rejection; TAP-05 separately proves continuity of a clean-start newly lease-owned generation | Cross-command attachment excluded |
| Runtime | Sequential gap or eight concurrent workers | Independent proxies attach to one held generation | behavior | TAP-02, TAP-03, TAP-05 | Deterministic overlap plus real canary proves retention without serialization | Cross-command persistence excluded |
| Loss | Before model dispatch | Optional bounded retry then fail | behavior | TAP-02, TAP-03 | Dispatch ledger defines safe retry boundary | None |
| Loss | After possible model dispatch | Infrastructure failure, no replay | behavior | TAP-02, TAP-03 | Tool/model event ledger exposes duplicate work | None |
| Exit | Success, provider error, sibling error, provider/direct-preflight Ctrl-C at creation/publication, or concurrent spawn/terminate | Synchronized OPEN → CLOSING snapshot → CLOSED; unpublished interrupt gets local drain, committed spawn is snapshot-owned, close-first spawn is rejected; then tagged PGID TERM(5s) → KILL(2s) → drain(2s) → one keeper close → release → sensitive cleanup | behavior | TAP-02, TAP-03, TAP-07 | Deterministic publication/closing barriers plus real cooperative/ignoring descendants, pumps, and untagged sentinel prove no post-snapshot orphan and isolation order | Untagged generic commands and broad scheduler redesign excluded |
| Exit | Close/release timeout | Cleanup continues and teardown remains visible | behavior | TAP-02, TAP-03 | Nested fault injection observes both cleanup and report | None |
| Helper compatibility | Search/research success/failure/timeout/heartbeat | Existing generated-helper adapter | helper | TAP-04, TAP-06 | Public helper/proof fixtures compare behavior directly | Direct Codex MCP excluded |
| Packaging | Installed wheel success/failure/provider-Ctrl-C/helper-preflight-Ctrl-C | Installed lifecycle and tagged descendants outside checkout | behavior | TAP-07 wheel smoke/release test | Exercises packaged executable, import origin, signal inheritance, PGID/process/DB residue | Source-tree-only proof is insufficient |

### Design Sources

| Source Anchor | Authority | Use |
|---|---|---|
| `openspec/initiatives/cure-chunkhound-daemon-keeper/initiative.md#decisions--constraints` | normative | Fail-before-model authority, helper retention, lifecycle and safety bounds |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/story.md#acceptance` | normative | Observable A1–A25 contract |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#added-requirements` | normative | Requirement/scenario contract, including A11 branch semantics |
| `cure_chunkhound.py:JsonRpcSession`, `run_chunkhound_mcp_preflight_payload`, `run_chunkhound_tool_payload` | orientation only | Existing MCP bootstrap and helper contract |
| `cure_llm.py:prepare_review_agent_runtime` | orientation only | Generated helper and curated runtime |
| `cure.py:_pr_flow_impl`, `_run_pr_context_orientation`, `_run_session_chunkhound_index_with_rebuild_fallback` | orientation only | Fresh PR, orientation, top-up, and multipass ordering |
| `cure_llm.py:run_llm_exec`, `cure_llm.py:run_codex_exec`, `cure_output.py:ReviewflowOutput.run_logged_cmd`, and `run.py:run_cmd` | orientation only | Provider subprocess routing plus current streamed/non-streamed transport and presentation seams |
| Installed ChunkHound `chunkhound.mcp_server.tools:daemon_status_impl` and `chunkhound.mcp_server.status:derive_daemon_status` | orientation only | Native generic-health semantics; not expected-session identity |

### Design Element Trace

| Source Anchor | Visible Element / State | Obligation | Bounds / Required Behavior | Scenario | Acceptance ID | Proof Row / Reviewer Action |
|---|---|---|---|---|---|---|
| `openspec/initiatives/cure-chunkhound-daemon-keeper/initiative.md#decisions--constraints` | Fail before model work | required | Supported indexed helper route completes native capability, health, expected-session adjudication, and helper preflight before orientation or any model; bypass routes remain unchanged | S1, S7–S10 | A1, A7–A10 | TAP-02/TAP-03 — run orientation-enabled ordering and all gate-fault route nodes; require zero earlier model events |
| `openspec/initiatives/cure-chunkhound-daemon-keeper/initiative.md#decisions--constraints` | Parent-owned ordinary keeper; independent helpers | required | Exactly one retained parent client per command; no broker, mutex, replay, direct Codex MCP, or cross-command persistence | S2–S4, S12 | A2–A4, A12 | TAP-02/TAP-03/TAP-05 — inspect generation/overlap/no-replay ledgers |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-exact-launch-identity` | Canonical launch identity | required | Keeper/helper complete identity equals the immutable receipt's named launch-identity projection; reviewed HEAD and final chunk count remain receipt-only fields | S5 | A5 | TAP-01/TAP-05/TAP-07 — run schema/projection, alias/symlink identity, and installed smoke nodes |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-curated-environment` | Curated child environment | required | Keeper/helper key sets and equality digest match; unrelated inherited values and raw values are absent | S6, S15 | A6, A15 | TAP-01/TAP-02 — run sentinel and recursive-redaction nodes |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-expected-session-index-is-validated` | Display-independent lossless raw receipt and native health | required | In normal, public quiet, and explicit no-stream routes, tee complete final-attempt stdout/stderr before tail eviction and seal after pump join; capture presence forces pumps but the existing `stream` boolean alone controls live user output. Project only the capture plus exit; reject early/beyond-bound conflicts, malformed/error evidence, integrity/construction failure; dispose every attempt; require typed ready/query-ready non-degraded `daemon_status`, never status alone as identity | S10, S11 | A10, A11 | TAP-01/TAP-02/TAP-03/TAP-05 — run normal/quiet/no-stream greater-than-tail valid/early-conflict/integrity/disposal matrices, zero-live-line and post-completion-display assertions, native matrices, and live canary |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-expected-session-index-is-validated` | Non-empty expected-session witness | required | Bounded deterministic Git-tracked candidate selection under include/exclude; path-constrained native search returns expected path/literal or fails closed | S11 | A11 | TAP-02/TAP-05 — run non-empty success, empty-result, wrong-path, wrong-literal, and exhausted-candidate nodes |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-expected-session-index-is-validated` | Zero-searchable-content state | required | Only authoritative zero-chunk receipt + exact launch identity + the current attempt's newly opened CURe-owned generation under its probed exact config/runtime identity + healthy native status is accepted; no invented witness | S11 | A11 | TAP-02 — run zero-chunk acceptance, stale/unattested rejection, and non-empty-no-witness nodes; TAP-05 — run the two clean-start zero-chunk parent-state continuity cases without pre-existing-generation manipulation |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-cleanup-follows-ownership-order` | Race-closed tagged descendant cleanup and ordered release | required | OPEN/CLOSING/CLOSED synchronization makes each provider/helper child locally cleaned, snapshot-owned, or rejected before creation with no post-snapshot publication; only owned groups receive TERM 5s, KILL survivors 2s, pipe/reap drain 2s; registry CLOSED precedes one keeper close/release and sensitive cleanup; untagged commands unchanged | S13, S14, S25 | A13, A14, A25 | TAP-03/TAP-07 — interrupt both callsites at publication, force both spawn/terminate orderings, and inspect PGID/order/residue ledgers |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-helper-tool-mapping-remains-stable` through `#requirement-tool-proof-semantics-remain-stable` | Generated-helper compatibility | required | Existing mapping, normalized JSON, timeout, five-second heartbeat, prompt, and proof behavior remain unchanged | S16–S21 | A16–A21 | TAP-04/TAP-06 — run parity fixtures and prompt/proof manifests |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-source-boundaries-are-preserved` | Creation-only daemon-log boundary and generation-bound corpus exclusion | required | Permit exact directory-plus-regular-log creation when both absent and exact regular-log-only creation when a real parent exists; preserve parent type/mode/content metadata/siblings, every other reviewed-root path/type/mode/symlink/content, and all operator-checkout entries; preserve pre-existing logs fully and reject symlink/non-directory parents; inject/dedupe exact `**/.chunkhound/**`; require a non-degraded installed-runtime effective-filter probe on every startup/config/runtime identity, reject every pre-existing/unattested same-root generation, and use only the newly opened CURe-owned generation under that exact probed identity; exclude log from corpus/search/research/readiness/witness/receipt/identity | S22 | A22 | TAP-02/TAP-03 — deterministic seeded/pre-existing/unattested rejection and ownership mismatch; TAP-06 — static/config/manifest proof; TAP-05 — four clean-start non-empty/zero × absent/existing-parent continuity, exclusion, release, and source-boundary cases without pre-existing-generation manipulation |
| `openspec/changes/cure-chunkhound-daemon-aware-research-calls/specs/chunkhound-daemon-aware-research/spec.md#requirement-installed-wheel-executes-the-lifecycle` through `#requirement-installed-wheel-cleanup-leaves-no-owned-residue` | Installed lifecycle | required | Wheel runs eligible lifecycle outside checkout, imports only wheel modules, and leaves no owned process/DB lock | S23–S25 | A23–A25 | TAP-07 — run isolated build/smoke and inspect origins/process/lock ledger |

### Input Boundary Shape Risk

| Boundary | Raw Input Source | Strict Assumption | Variant / Case | Evidence | Mitigation / Exclusion |
|---|---|---|---|---|---|
| Final-index summary transport | Final top-up invocation stdout/stderr and exit code before `_TailBuffer(capture_tail_chars)` eviction or `chunkhound_summary.py` normalization | One sealed lossless per-attempt capture constructs a complete receipt independently of display-tail bounds and user-visible stream selection | Normal route (`stream=True`) uses visible pumps; public quiet and explicit no-stream retain `stream=False` but capture presence forces the same pump/spool transport with no live sink; complete nonzero/zero fields before/after greater-than-bound filler; seal only after pumps join and exit | TAP-01/TAP-02 parameterized real emitters plus TAP-03 separate public normal/quiet/no-stream routes | Final-index owner alone passes `lossless_capture`; `run_cmd` chooses pump transport when `stream or lossless_capture is not None`, tees before tail eviction, and writes the live sink only when `stream=True`; separate mode-0600 spools outside reviewed roots; no `subprocess.run` authority and no unbounded in-memory fallback |
| Quiet/no-stream presentation | Sealed final-index stdout/stderr spools after silent pumps finish | Public quiet and explicit no-stream preserve zero live user lines and existing post-completion log/progress observability | Recording user sink remains empty until exit and stays free of command lines; sealed stdout/stderr are replayed to the existing non-stream log/progress path in bounded chunks; summary callback sees complete content; tails remain diagnostic only | TAP-01 recording sinks and TAP-03 public CLI route ledgers | Keep capture transport private from display semantics; replay from disk in bounded chunks, never materialize complete output in memory; ordinary no-capture `stream=False` stays on unchanged `subprocess.run` branch |
| Final-index summary authority | Same sealed complete capture in all three display routes | Dropped, partial, contradictory, or capture-damaged evidence cannot establish authority | Early malformed/conflicting recognized field, greater-than-bound filler, later valid-looking field; missing fields; nonzero errors/exit; capture write/pump/seal/read/replay-integrity/disposal failure | TAP-01/TAP-02 mode-parameterized adversarial matrix proves returned tails omit early evidence while receipt construction still rejects; TAP-03 proves route parity/disposal | Tee every decoded pump chunk to its corresponding spool before tail/live sink; propagate pump/capture integrity faults; strict projector scans all occurrences across complete stdout/stderr and permits repeats only when every occurrence agrees; dispose every attempt |
| Receipt construction | Filesystem/Git/config/runtime identity inputs | All receipt fields are canonical, digestible, and immutable | Missing HEAD; path resolution failure; non-regular config; digest/read race or failure; DB identity failure; unsupported schema version | TAP-01 temp symlink/race/failure fixtures | Construct once as a frozen value; no partial receipt and no fallback identity |
| Native status | Raw MCP `daemon_status` result | Object contains correctly typed ready/query-ready and non-degraded scan/realtime state | Non-object, missing field, wrong type, initializing, degraded, or error envelope | TAP-02 fake frames; TAP-05 live canary | Reject before model; retain bounded redacted diagnostics |
| Native search | Raw MCP `search` result | Documented result collection exposes a matching canonical path and literal | Non-object/error envelope, missing/wrong-type result collection/fields, empty, wrong path/literal, oversized/exhausted candidates | TAP-02 raw frames; TAP-05 deterministic corpus | Strict bounded parser; malformed/empty never proves a non-empty receipt |
| Environment and launch identity | Mutable secret-bearing parent env plus executable/root/config/DB/cwd paths | Keeper/helper share an immutable canonical projection without persisting values | Symlink/alias, unrelated env sentinel, changed key set/value digest | TAP-01 recorder process | Copy allowlist once; store only key set and non-reversible equality digest |
| Process ownership | Linux PID/PGID, pipes, exits, Ctrl-C, and terminal teardown racing tagged spawn creation/publication | Only registry-created provider/helper groups are signal targets; every created child is either locally cleaned or published before the terminal snapshot; no post-snapshot publication | Cooperative TERM, TERM-ignoring/pipe-holding descendants, Ctrl-C after `Popen` before publication, spawn-lock-first, close-lock-first, normal exit/unregister, untagged sentinel | TAP-03/TAP-07 real subprocess ledgers with deterministic lock/publication barriers | One lock/condition guards OPEN/CLOSING/CLOSED, `Popen`+publication, and closing snapshot; pre-publication `BaseException` locally TERM/KILL/drains; closing rejects spawn before `Popen`; first terminator owns cleanup and concurrent terminators await CLOSED; fixed 5s/2s/2s budgets; never infer ownership from root/PID/daemon registry |
| Source manifest and daemon-log filter/generation | Reviewed-root/operator-checkout entries, CURe materialized config, installed-runtime effective-filter result, startup generation ledger, and daemon-log marker bytes | Exact directory-plus-regular-log creation when both absent or regular-log-only creation when a real parent exists; existing parent type/mode/content metadata/siblings and all other pre-existing entries are path/type/mode/symlink/content immutable; exact `['**/.chunkhound/**']` occurs once and is effectively excluded; generation used is newly opened and CURe-owned under the probed exact config/runtime identity | Pre-existing-log mutation; symlink/non-directory parent; parent metadata/sibling or other artifact change; operator-checkout change; duplicate/missing exclusion; changed config/runtime identity; stale/malformed/degraded/non-excluding probe; any pre-existing/unattested same-root generation; post-open ownership/identity mismatch; marker appears in corpus/search/research/readiness/witness/receipt/identity | TAP-02/TAP-03 deterministic rejection and TAP-06 static/config/manifest matrix; TAP-05 four clean-start non-empty/zero × absent/existing-parent cases proving immediate absence, one validation, newly lease-owned evidence, continuity, release, effective exclusion, and exact boundary without pre-existing-generation manipulation | Deterministic seams reject pre-existing/unattested generations and opened mismatch; TAP-05 does not seed them. Permit no operator-checkout exception and never broadly ignore `.chunkhound/**`; log observation cannot authorize readiness or identity |

### Fail-open Checks

- Unsupported static eligibility cannot continue into orientation/model execution.
- Failed keeper capability, native status, expected-session receipt/witness/zero-chunk adjudication, or identity cannot continue into orientation or any other model execution with a zero-client lifecycle.
- Missing required tools cannot degrade to warning-only preflight.
- Post-dispatch keeper loss cannot restart or replay model/helper work.
- Teardown timeout cannot be reported as successful cleanup.
- Sensitive cleanup cannot be skipped because release observation failed.
- `--no-index`, `--no-review`, and keeper-ineligible provider routes are explicit expected bypasses, not silent failures.

### Risk Lens Inventory

| Risk | Control |
|---|---|
| External process lifecycle | Executable fake MCP and real canary |
| Final-index transport/display coupling | Final-top-up-only capture forces bounded-memory pumps in normal/quiet/explicit-no-stream; `stream` alone controls live lines; mode-parity grammar/integrity/disposal and bounded replay proof; ordinary no-capture branches unchanged |
| Worker/child ownership | Explicit `review-provider`/`chunkhound-helper` registry, synchronized OPEN/CLOSING/CLOSED publication protocol, local cleanup for interrupted unpublished children, Linux process-group isolation, fixed TERM/KILL/drain budgets, and untagged sentinel proof |
| Concurrency | Eight-client overlap barrier |
| Duplicate side effects | Pre-dispatch-only retry and post-dispatch no replay |
| Root/config/database ambiguity | Exact CURe identity invariant |
| Secrets | Curated environment and recursive redaction |
| Platform/version/filter/generation drift | Static gates plus a fresh non-degraded installed-runtime effective-filter proof for every startup/config/runtime identity, rejection of every pre-existing/unattested same-root generation, and post-open proof of the newly opened CURe-owned generation under that exact probed identity |
| Cleanup/database lock | Bounded release observation |
| Source mutation / daemon-log corpus contamination | Exact absent-parent directory-plus-log and existing-real-parent log-only deltas; parent metadata/sibling, pre-existing-log immutability, invalid-parent, and operator-checkout gates; injected/deduped `**/.chunkhound/**`; enabled non-empty/zero marker absence across corpus/search/research/readiness/witness/receipt/identity |
| Packaging divergence | Isolated installed-wheel and release-workflow proof |
| Prompt substitution | Not changed; canonical prompt/helper parity test |

## Discovery Notes

- Each helper already invokes native daemon-backed `chunkhound mcp`.
- Final-client disconnect currently schedules immediate daemon shutdown.
- Current preflight closes its proxy and is not a keepalive.
- Daemon discovery is keyed by canonical root, not config/database.
- `JsonRpcSession` currently inherits ambient `os.environ`.
- Fresh PR top-up indexing precedes current helper preflight.
- PR-context orientation currently invokes `run_llm_exec` before top-up indexing; supported indexed helper routes must move that dispatch after final indexing, keeper expected-session adjudication, and helper preflight.
- Multipass runs plan, up to eight concurrent steps, retries, then synthesis.
- `cure_llm.py:run_llm_exec` routes Codex to `run_codex_exec`, which reaches `run.py:run_cmd` directly or through `cure_output.py:ReviewflowOutput.run_logged_cmd`; streamed `run_cmd` waits and drains pumps but has no active-child termination owner.
- `_run_chunkhound_helper_preflight` in `cure.py` separately owns a direct `Popen`; its timeout kills only the immediate process and does not prove descendant/process-group cleanup.
- Final-index display evidence is accumulated through permissive `chunkhound_summary.py:parse_chunkhound_index_summary` parsing in `cure_output.py`; streamed `run.py:run_cmd` retains only `capture_tail_chars` (default 200,000) per pipe, while public fresh-review `--quiet` and explicit `--no-stream` currently select `stream=False` and the `subprocess.run` branch with complete in-memory strings. Receipt authority therefore must make final-top-up capture presence force pump/spool transport independently of visible streaming, suppress live sink writes when `stream=False`, and reject incomplete, contradictory, malformed, error-bearing, or capture-integrity-failed evidence across the complete invocation without an unbounded in-memory authority path.
- Public tests require explicit façade exports.
- Release workflow currently performs only a basic installed `cure --help` smoke.

## Critical Files

### Create

- `cure_chunkhound_lifecycle.py`
- `tests/_reviewflow_unittest_daemon_aware_impl.py`
- `tests/test_daemon_aware_chunkhound_live.py`
- `tests/test_chunkhound_daemon_aware_source.py`
- `tests/daemon_aware_research_calls_smoke.py`

### Modify

- `cure_chunkhound.py`
- `cure.py`
- `cure_llm.py`
- `cure_runtime.py`
- `cure_output.py`
- `run.py`
- `tests/_reviewflow_unittest_core.py`
- `tests/test_reviewflow_unittest.py`
- `tests/test_release_workflow_unittest.py`
- `.github/workflows/publish-package.yml`
- `pyproject.toml`
- `README.md`
- `ARCHITECTURE.md`

### Expected unchanged

- `prompts/*.md`
- `cure_flows.py`
- resume/follow-up implementation surfaces
- doctor behavior

## Implementation Notes

1. Add RED tests and executable fake MCP/process fixtures.
2. Add immutable explicit environment handling to `JsonRpcSession`.
3. Extract canonical bootstrap:
   `spawn → initialize → initialized notification → tools/list → require search/code_research/daemon_status`.
4. Implement a focused lease state machine:
   `NEW → STARTING → HELD → CLOSING → CLOSED`, with typed startup, loss, and teardown failures.
5. Add static eligibility before orientation.
6. For each final top-up attempt, create a private `FinalIndexRawCapture` and pass it through the optional `lossless_capture` interface on `ReviewflowOutput.run_logged_cmd`/`run_cmd`. In `run_cmd`, select pump transport when `stream` is true **or** capture is present; tee each decoded stdout/stderr chunk to its separate spool before bounded-tail append, but forward to the live sink only when the existing `stream` flag is true. Thus normal mode remains live, while public quiet and explicit no-stream retain `stream=False`, emit no live user lines, and after exit/seal replay the private spools in bounded chunks through the same existing non-stream log/progress callback path. Seal only after both pumps join and exit is known; strictly project only the sealed complete capture; dispose every attempt on every path. Build exactly one frozen receipt only after strict all-occurrence grammar, zero-error, integrity, canonicalization, digest, and projection validation. Never materialize complete captured output in memory; ordinary no-capture commands retain their existing branches and display behavior.
7. Before each keeper open, reject every pre-existing or unattested same-root generation. Acquire the keeper only after the exact config/runtime effective-filter probe, then require that the observed generation was newly opened and is CURe-owned under that probed identity, closing/failing before helper/model on mismatch; additionally require a strictly shaped native `daemon_status`, exact equality with the receipt's launch projection, and a strictly shaped non-empty witness or bounded zero-chunk expected-session adjudication.
8. Thread one optional `OwnedProcessRegistry` only through supported fresh-review callsites: `_pr_flow_impl` → `run_llm_exec` → `run_codex_exec` → `ReviewflowOutput.run_logged_cmd`/`run_cmd`, plus `_run_chunkhound_helper_preflight`; do not tag resume/follow-up, HTTP, indexing, Git, Jira, or other generic commands.
9. Registry spawn creates a Linux session/process group atomically for roles `review-provider` and `chunkhound-helper`. One lock/condition serializes OPEN-state validation, `Popen`, publication, and the OPEN → CLOSING terminal snapshot. If `BaseException` interrupts after child creation but before publication, spawn locally applies the same bounded group TERM/KILL/drain/reap before releasing the lock and re-raising; after CLOSING begins, spawn is rejected before `Popen`; no entry can publish after the snapshot. Normal completion waits, drains pumps/pipes, and unregisters under the same synchronization. The first `terminate_and_drain` owns the snapshot/cleanup; concurrent calls await CLOSED and reuse its typed outcome. Cleanup sends TERM and waits 5 seconds, sends KILL to survivors and waits 2 seconds, then spends at most 2 seconds draining/reaping before reporting typed teardown failure.
10. Run existing helper preflight, then optional orientation and all remaining model work while holding one keeper through standard/big or complete multipass execution; check health only at safe phase boundaries.
11. Use nested cleanup so registry termination/drain precedes one keeper close and sensitive cleanup executes even after teardown failure.
12. Observe release only for the current attempt's newly opened CURe-owned generation; reject pre-existing/unattested same-root generations and never kill by root/PID/private metadata.
13. Preserve all helper-facing behavior and prompt/proof semantics.
14. Add deterministic, live, source-boundary, and installed-wheel proof, including separate normal/public-quiet/explicit-no-stream final-top-up routes; all-occurrence valid and adversarial output beyond `capture_tail_chars`; write/pump/seal/read/replay/disposal faults; bounded memory; unchanged live/no-live and post-completion display; provider/direct-preflight Ctrl-C after child creation before publication; both spawn-versus-terminate lock orderings; cooperative/TERM-ignoring descendants; pipe holders; and an untagged generic-command sentinel.

## Locked Decisions

- Retain the generated helper.
- Do not configure direct Codex-native MCP.
- Use one parent-owned retained ordinary MCP proxy.
- Share canonical bootstrap between preflight and keeper and require `search`, `code_research`, and `daemon_status` for supported routes.
- Use explicit immutable curated environment.
- Define `ExpectedSessionReceiptV1` as a frozen value with `schema_version`, canonical root, reviewed HEAD, resolved config path and digest, resolved database path, final `total_chunks`, and `launch_identity_projection`; that projection contains resolved executable, canonical root, resolved config path/digest, resolved database path, cwd, curated environment key set, and non-reversible equality digest. Keeper and helper identities equal the projection exactly; HEAD and chunk count are receipt-only adjudication fields.
- Receipt authority is a sealed `FinalIndexRawCapture` for the final successful top-up attempt, never `CommandResult.stdout`/`stderr` bounded tails or `ChunkhoundLiveProgressReporter`'s partial dictionary. `run_cmd(..., lossless_capture: LosslessCommandCapture | None = None)` and matching `ReviewflowOutput.run_logged_cmd` forwarding form the narrow final-top-up interface. `run_cmd` computes capture-capable transport as `stream or lossless_capture is not None`: ordinary `stream=False` with no capture keeps the current `subprocess.run` branch, while any capture uses stdout/stderr pumps, writes each decoded chunk to its corresponding spool before `_TailBuffer` eviction, and writes the live sink only when `stream=True`. Therefore normal top-up remains live; public quiet and explicit no-stream retain `stream=False` and zero live user lines, then `ReviewflowOutput`/the direct owner replay sealed streams in bounded chunks through the existing post-completion log/progress callback path. Capture seals only after both pumps join and exit is known. The final-index owner creates one mode-0600 private spool pair outside reviewed roots per attempt, scans/replays without loading complete output into memory, and disposes every attempt on success, retry, projector/read failure, interruption, and teardown; no other caller supplies this option, so ordinary tagged/untagged commands and existing display behavior are unchanged. Exit must be zero; `total_chunks` and `error_files` must be present integers and every recognized occurrence across complete stdout/stderr must be well formed and agree; `error_files` must be zero. Missing/conflicting counts, malformed recognized fields even when earlier than or beyond `capture_tail_chars`, nonzero errors/exit, capture write/pump/seal/read failure, or canonicalization/digest/construction failure is typed fail-closed evidence before receipt/keeper/model. Repeated identical recognized fields may normalize only when all occurrences agree.
- Native `daemon_status` and `search` results are strict external shapes: error envelopes, non-objects, missing/wrong-type required fields, degraded state, malformed result collections/hits, or wrong/empty witnesses fail before model and never authorize the zero branch.
- Complete final indexing/receipt, keeper native health, expected-session adjudication, and helper preflight before optional orientation or any other model work.
- Treat native `daemon_status` as required generic health, never sufficient expected-session identity.
- For non-empty receipts require a bounded deterministic path/literal search witness; for authoritative zero-chunk receipts require exact receipt/launch identity, the current attempt's newly opened CURe-owned generation under the probed exact config/runtime identity, and healthy native status; never accept an empty result for a non-empty receipt.
- One keeper spans multipass phases and retries.
- Preserve independent helper concurrency.
- Allow one bounded startup retry only before any model work; each attempt independently probes the exact config/runtime identity, rejects every pre-existing/unattested same-root generation, and accepts only its newly opened CURe-owned generation.
- Never replay after possible dispatch.
- Add `OwnedProcessRegistry` in `run.py` with `spawn(*, role: OwnedProcessRole, cmd: list[str], **popen_options) -> subprocess.Popen[Any]` and `terminate_and_drain(*, term_timeout_seconds=5.0, kill_timeout_seconds=2.0, drain_timeout_seconds=2.0)`. `OwnedProcessRole` is exactly `Literal["review-provider", "chunkhound-helper"]`. One registry lock/condition guards `OPEN`, `CLOSING`, and `CLOSED`, the OPEN check, Linux new-session/process-group `Popen`, publication, normal unregister, and the terminal snapshot. Spawn holds that synchronization from OPEN check through publication: if spawn wins, publication commits before teardown can set CLOSING/snapshot; if teardown wins, spawn raises typed `OwnedProcessRegistryClosingError` before `Popen`; publication after CLOSING is impossible. A `BaseException` after child creation but before successful publication triggers local 5s TERM/2s KILL/2s drain/reap under spawn ownership before re-raise. The first `terminate_and_drain` transitions OPEN → CLOSING, snapshots every committed entry, performs bounded cleanup, records the typed outcome, and transitions CLOSED; concurrent terminators wait for CLOSED and do not duplicate signals. Registered entries remain owned until exit plus pipe/pump drain; only their PGIDs are signalled; survivors/drain timeout remain typed teardown failures.
- Extend only the ownership route with optional parameters: `run_cmd(..., owned_processes: OwnedProcessRegistry | None = None, owned_role: OwnedProcessRole | None = None)` and matching `ReviewflowOutput.run_logged_cmd` forwarding; `run_llm_exec(..., owned_processes: OwnedProcessRegistry | None = None)` and `run_codex_exec(..., owned_processes: OwnedProcessRegistry | None = None)` always forward role `review-provider` when the registry is present; `_run_chunkhound_helper_preflight(..., owned_processes: OwnedProcessRegistry | None = None)` spawns role `chunkhound-helper`. Supplying only one of registry/role is invalid. Every unrelated `run_cmd` caller, HTTP route, indexing/Git/Jira command, resume/follow-up route, and normal untagged behavior remains unchanged.
- On Ctrl-C/fault, registry reaches CLOSED before exactly one keeper close; deterministic proof must cover provider and direct-preflight interrupt after `Popen` but before publication, spawn-lock-first publication-before-snapshot, close-lock-first rejection-before-`Popen`, concurrent `terminate_and_drain`, cooperative and TERM-ignoring descendants, descendant-held pipes, normal exit/unregister races, and an untagged sentinel.
- No user legacy toggle.
- No daemon TTL, private IPC, broker, PID/root killing, or cross-command persistence.
- Resume/follow-up, interactive, Windows/macOS, and doctor remain excluded.
- HTTP/non-helper providers remain keeper-ineligible and unchanged.

## Plan Review Log

- 2026-07-29T09:21:52Z Cycles 1–3 plan review history compressed after feedback absorption
  - Addressed plan review entries: `2026-07-29T08:35:54Z`, `2026-07-29T08:55:29Z`, and `2026-07-29T09:12:27Z` (`request_changes`).
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes.
  - Material closure: Cycle 1 moved final index/receipt, native health/session adjudication, and helper preflight before every model and added witness/zero-chunk/design-trace proof; Cycle 2 froze `ExpectedSessionReceiptV1`, strict native shapes, exact fresh-route registry wiring, fixed process budgets, and untagged invariance; Cycle 3 added final-top-up-only sealed lossless authority beyond bounded tails and race-closed OPEN/CLOSING/CLOSED spawn publication/teardown proof.
  - Material evidence anchors: initiative `initiative.md#decisions--constraints`; `chunkhound_summary.py:20-59`; `cure_output.py:112-139,563-661`; `run.py:63-150`; `cure.py:_run_session_chunkhound_index_with_rebuild_fallback`, `_run_chunkhound_helper_preflight`, `_pr_flow_impl`; `cure_llm.py:run_llm_exec`, `run_codex_exec`.
  - Latest disposition: all three review entries addressed; no unresolved blockers; Plan lane `🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT`; Status remains `⚪ TODO`.

- 2026-07-29T09:04:19Z Debt Friction recorded by `/openspec-story-plan-resume`
  - Debt Friction: provider/helper descendant ownership
  - Current Story Action: make A13/A25 Ctrl-C and installed-wheel cleanup executable while retaining the generated helper and parent-owned keeper.
  - Friction Evidence: `cure_llm.py:391-472,721-758` routes Codex through `cure_output.py:ReviewflowOutput.run_logged_cmd`/`run.py:63-150`, whose streamed child only waits; `cure.py:8672-8731` separately owns helper preflight and kills only its immediate child on timeout.
  - Delivery Impact: without one explicit owner and descendant isolation, Ctrl-C can leave provider/helper descendants or pipe holders alive, invalidating keeper-close ordering and wheel residue proof.
  - Decision: fix-now.
  - Scope Justification: narrowly tagged provider and helper ownership is directly required by A13/A25; broad generic-command cancellation is excluded.
  - Guardrail: only supported fresh-review `review-provider` and `chunkhound-helper` groups use the registry; untagged `run_cmd`, HTTP, indexing, Git, Jira, resume/follow-up, daemon PID/root killing, and scheduler behavior remain unchanged.

- 2026-07-29T09:35:11Z Cycle 4 plan review summary (stale detail compressed after feedback absorption)
  - Verdict: `request_changes`; Plan lane `🟡 PLAN DRAFT -> 🟠 PLAN CHANGES REQUESTED`; Status remained `⚪ TODO`.
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes.
  - P1: public fresh-review `--quiet` and explicit `--no-stream` select final-top-up `stream=False` (`cure.py:_pr_flow_impl`, `_run_session_chunkhound_index_with_rebuild_fallback`; `cure_output.py:ReviewflowOutput.run_logged_cmd`; `run.py:run_cmd`) and reached `subprocess.run`, while A11 authority/proof covered only streamed pumps. Required an implementable lossless silent transport plus separate route, display, all-occurrence, integrity/disposal, and greater-than-bound proof.
  - Preserved closure: stream-mode complete authority; OPEN/CLOSING/CLOSED publication race and cleanup ordering; generated-helper retention; exactly one parent-owned ordinary keeper; independent helpers; exclusions and untagged invariance.
  - Addressed by receipt: `2026-07-29T09:39:21Z`; no unresolved blockers or new Debt Friction.

- 2026-07-29T09:39:21Z Plan feedback addressed by `/openspec-story-plan-resume`
  - Original plan review entry: 2026-07-29T09:35:11Z
  - Sections edited: `story.md` Scope, S11, A11, Test Architecture Plan, Acceptance Proof Matrix, Surface / Branch Proof Matrix, Design Element Trace, Input Boundary Shape Risk, Discovery Notes, Implementation Notes, Locked Decisions, Plan header, and Plan Review Log; `proposal.md` Goal / Context and Decisions & Constraints; `design.md` Architecture Overview, capture/adjudication decision, Implementation Strategy, and Risks & Mitigations; `tasks.md` setup, implementation, and proof tasks; `specs/chunkhound-daemon-aware-research/spec.md` summary and expected-session requirement/scenarios
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Changes: separated final-top-up authority transport from user-visible streaming by locking capture-forced bounded-memory stdout/stderr pumps for normal, public `--quiet`, and explicit `--no-stream`; only normal mode forwards live lines, while silent modes retain `stream=False` and use bounded post-completion spool replay for existing log/progress behavior. Added deterministic route, no-live-line, all-occurrence grammar, integrity/disposal, greater-than-bound valid/early-conflict, and bounded-memory parity proof. Capture remains final-top-up-only; ordinary commands, generated helper, exactly one parent-owned keeper, process-race closure, exclusions, and untagged invariance remain unchanged.

- 2026-07-29T09:53:18Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `openspec/initiatives/cure-chunkhound-daemon-keeper/initiative.md` Goal / Context, Story Candidates, Decisions & Constraints, and External Resources (`None`); no issue, PR, Jira, ticket, dependency workspace, or sibling shared-interface anchor is linked
  - Traceability: forward complete; backward complete
  - Design trace: complete
  - Code surfaces searched: `chunkhound_summary.py:6-61`; `run.py:29-150`; `cure_output.py:57-161,469-653`; `cure_chunkhound.py:1-40,286-321,722-1294`; `cure_llm.py:391-472,716-790,845-1135,1203-1345`; `cure.py:_run_session_chunkhound_index_with_rebuild_fallback`, `_run_chunkhound_helper_preflight`, `_run_chunkhound_access_preflight`, `_pr_flow_impl`, `_execute_multipass_step_stage`; `tests/_reviewflow_unittest_core.py`; `tests/test_reviewflow_unittest.py`; `tests/test_release_workflow_unittest.py`; `pyproject.toml`; `.github/workflows/publish-package.yml`; `scripts/build_standalone_release.py`; `README.md`; `ARCHITECTURE.md`; installed ChunkHound `chunkhound/mcp_server/tools.py:630-704,732-739`, `chunkhound/mcp_server/status.py:21-56`, and `chunkhound/daemon/server.py:30,203-224`
  - Risk lenses reviewed: activated concurrency/thread/process synchronization (eight-client overlap and OPEN/CLOSING/CLOSED both-order barriers); Linux process-group/OS-signal and cancellation behavior (publication interruption, TERM/KILL/drain, unsupported-platform fail-before-model); external subprocess/MCP I/O and raw data-shape boundaries (sealed complete stdout/stderr all-occurrence authority plus strict status/search payloads); presentation/transport coupling (separate normal, public-quiet, and explicit-no-stream route proof, zero live lines for silent modes, bounded replay, ordinary no-capture invariance); filesystem permissions, bounded memory, persistence, and resource lifecycle (mode-0600 private spools, per-attempt disposal, one keeper close, generation/DB-lock release); security/privacy (curated immutable environments, equality digest, recursive redaction, no raw stderr/auth material); retries/timeouts/partial failure (one pre-dispatch startup retry, no post-dispatch replay, fixed process budgets, cleanup despite teardown failure); generated helper and packaging divergence (helper parity, source manifest, isolated wheel/import-origin and release-workflow proof); naming/schema-sensitive invariants (receipt version/projection, exact process roles, native tool names, summary grammar); source-boundary/backward-compatibility risk (manifest proof and excluded-route/untagged controls). Async/event-loop is non-material to CURe's planned implementation because ownership is thread/process based; network/external-service behavior, database/config migration, and UI responsive/layout/copy are not changed; prompt/template substitution is unchanged and bounded by A20/TAP-04/TAP-06 parity rather than a new rendered-template obligation.
  - Evidence quality: confirmed current source routes public quiet/no-stream to `stream=False`, ordinary non-stream commands to `subprocess.run`, streamed commands to bounded tails, final top-up through `ReviewflowOutput.run_logged_cmd`, orientation before current top-up, helper generation/import/tool mapping, direct helper `Popen`, Codex/provider routing and multipass concurrency, packaging/module lists, release smoke, installed ChunkHound immediate zero-client shutdown and native status/search shapes, all material artifact selectors, and structural A1–A25/TAP-01–TAP-07 coverage; inferred none; unknown implementation-time live generation/release behavior on the eventual supported environment, safely bounded by mandatory deterministic TAP-02/TAP-03 and opt-in installed-runtime TAP-05 before implementation approval; provisional executable evidence is expected at plan time and every A1–A25 row names an owner, reviewer action, expected signal, and RED-test detail
  - Finding closure: Cycle 4 capture/display omission is closed by synchronized story/proposal/design/tasks/spec changes: A11 and TAP-01/TAP-02/TAP-03 now separately force pumps for normal/quiet/no-stream, preserve zero-live silent presentation and bounded post-completion replay, scan complete sealed streams, dispose every attempt, and keep ordinary no-capture paths unchanged; current source checks confirm those are the real routing/transport seams. Earlier receipt/session/process-publication findings remain closed, with regression and side-effect controls in the Surface / Branch Proof Matrix, Input Boundary Shape Risk matrix, TAP-03/TAP-04/TAP-06/TAP-07, and explicit excluded-route/untagged invariance. No unresolved finding remains.
  - Key findings:
    - No blocking planning finding: initiative intent maps through S1–S25, A1–A25, TAP-01–TAP-07, proof rows, owning source/test surfaces, and the delta spec without an orphaned branch or surface.
    - Final-top-up-only capture authority is separated from presentation and memory ownership: complete private spools authorize/reject, normal alone emits live, quiet/no-stream replay boundedly only after completion, and ordinary no-capture streamed/non-streamed behavior stays outside the interface.
    - Lifecycle ownership is implementable at the actual provider and direct-preflight spawn seams and has deterministic close-first/spawn-first/prepublication-interrupt/concurrent-terminator proof, one parent-owned ordinary keeper, retained independent helpers, and source/wheel residue checks.
    - No normative visual design artifact exists; user-visible no-live/post-completion behavior is nevertheless observable at recording sinks and public CLI route ledgers, so no additional rendered UI review is required.
  - Hypothesis triage: none
  - Debt Friction: none beyond the existing fix-now provider/helper descendant-ownership decision, which is fully incorporated into A13/A25, TAP-03/TAP-07, implementation tasks, and locked route bounds
  - Next action: choose either `/openspec-story-converge cure-chunkhound-daemon-keeper cure-chunkhound-daemon-aware-research-calls` or `/openspec-story-claim cure-chunkhound-daemon-keeper cure-chunkhound-daemon-aware-research-calls`, not both
