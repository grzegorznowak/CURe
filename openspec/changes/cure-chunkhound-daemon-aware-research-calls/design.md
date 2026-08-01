# Design: cure-chunkhound-daemon-aware-research-calls

## Architecture Overview

```text
final index/receipt readiness
        │
        ▼
CURe parent keeper ─────────────┐
                               │
review agent                    ├── shared native ChunkHound daemon
  └─ cure-chunkhound helper     │
       └─ short-lived MCP proxy ┘
```

The keeper is only a daemon-liveness lease. Helper requests remain independent
and continue using their current access, timeout, heartbeat, output, prompt, and
proof contracts.

Responsibilities:

- `cure_chunkhound.py`: MCP transport and canonical bootstrap.
- `cure_chunkhound_lifecycle.py`: lease state, identity, health, and release.
- `cure_llm.py`: authoritative helper/runtime environment construction.
- `cure.py`: eligibility, keeper ownership, multipass lifetime, and cleanup.
- `run.py`: final-top-up-only display-independent complete-output pump/spool tee plus narrowly scoped provider/helper spawn-publication and termination/drain ownership.

## Technical Decisions

### Parent-owned retained proxy

`ChunkHoundDaemonLease` owns one initialized `JsonRpcSession`. It exposes
identity metadata, `assert_alive()`, idempotent `close()`, and context-manager
semantics. It never receives helper queries.

### Canonical bootstrap and expected-session adjudication

Ordinary preflight and keeper acquisition share:

```text
spawn chunkhound mcp
→ initialize
→ notifications/initialized
→ tools/list
→ require search, code_research, and daemon_status
```

Preflight closes immediately. Keeper acquisition retains the session. The
keeper calls native `daemon_status` and requires `status == "ready"`,
`query_ready == true`, the documented payload shape, and no scan/realtime
degradation. This is generic health evidence only; it does not by itself prove
which session index is attached.

The final successful top-up invocation's sealed `FinalIndexRawCapture` plus exit
code is the only index-summary authority for receipt construction. The final-index
owner creates one capture per attempt using separate mode-0600 private stdout and
stderr spools outside reviewed roots and disposes each capture on every path. It
passes that owner through the narrow optional
`lossless_capture: LosslessCommandCapture | None` parameter on
`ReviewflowOutput.run_logged_cmd` and `run_cmd`.

Transport and presentation are separate. `run_cmd` uses pump transport when
`stream` is true **or** `lossless_capture` is present. With capture, both stdout
and stderr pumps tee each decoded chunk to its corresponding spool before
`_TailBuffer` eviction. The existing `stream` argument remains the sole live
presentation switch: normal top-up (`stream=True`) forwards chunks to the current
sink, whereas public fresh-review `--quiet` and explicit `--no-stream` retain
`stream=False`, forward no live user lines, and avoid the current unbounded
`subprocess.run` authority branch. After both pumps join and exit is known, the
capture seals; the silent path replays each sealed stream in bounded chunks only
through `ReviewflowOutput`'s existing post-completion log/progress callback path
(or the direct owner's equivalent), preserving complete post-completion
observability without materializing either stream in memory. Pump/write/seal/read
or replay-integrity failure is typed fail-closed. Every attempt is disposed on
success, retry, interruption, projection/read fault, and teardown. No other caller
supplies the option: ordinary no-capture `stream=False` remains on `subprocess.run`,
ordinary streamed commands retain their current pump/display behavior, and bounded
`CommandResult` tails remain display/diagnostic only.

A dedicated strict projector incrementally consumes only the sealed complete
streams, never bounded tails, replay output, or the permissive display parser. It requires exit zero, present integer
and internally consistent `total_chunks` and `error_files`, and
`error_files == 0`. Missing or conflicting counts, malformed recognized fields
anywhere in either complete stream (including data displaced beyond
`capture_tail_chars`), nonzero errors/exit, capture-integrity failure, or
canonicalization/digest/construction failure produces a typed pre-receipt,
pre-keeper, pre-model failure. Repeated identical recognized fields may normalize
only if every occurrence agrees.

Final indexing constructs exactly one frozen `ExpectedSessionReceiptV1` with a
schema version, canonical root, reviewed HEAD, resolved config path and digest,
resolved database path, final chunk count, and an embedded
`launch_identity_projection`. The projection is the exact `LaunchIdentity` tuple:
resolved executable, canonical root, resolved config path and digest, resolved
database path, cwd, curated environment key set, and non-reversible equality
digest. Keeper and helper identities equal this projection; reviewed HEAD and
chunk count remain receipt-only adjudication fields. CURe rejects every pre-existing or unattested same-root generation and unsupported
receipt versions. Each startup attempt may proceed only with the CURe-owned
generation newly opened under that attempt's probed exact config/runtime identity.

Native `daemon_status` and `search` payloads are strict external shapes. Error
envelopes, non-objects, missing or wrong-type required fields, degraded state,
malformed result collections/hits, or wrong/empty witness data fail before model
work. When the receipt reports one or more chunks, CURe deterministically selects
bounded Git-tracked regular-file/token candidates under the configured
include/exclude policy and requires native `search`, constrained to the candidate
path, to return the expected literal and path. If no candidate proves identity,
startup fails closed. When the authoritative final receipt reports zero chunks,
search has no valid witness: the only accepted empty-index proof is the zero-chunk
receipt plus exact launch-projection equality, the expected generation newly
opened and owned by CURe for the current startup attempt under its probed exact
config/runtime identity, and healthy `daemon_status`. A zero-result search never
proves an expected non-empty index.

### Creation-only daemon-log boundary and generation-bound effective-filter gate

Before each native daemon startup attempt, CURe records a canonical manifest of
the indexed root and a strict manifest of the operator source checkout. The only
permitted reviewed-root delta is creation by the native daemon lifecycle of the
initially absent regular `<canonical-indexed-root>/.chunkhound/daemon.log`, with
the `.chunkhound/` parent created as a directory only when that parent is absent.
If the parent already exists as a real directory and the log is absent, only the
regular log may be created; the parent's type, mode, content metadata, and every
sibling remain identical. A pre-existing log is fully immutable, and a symlink
or non-directory parent fails closed. Every other pre-existing entry remains
identical in path, type, mode, symlink target, and content. No append, truncation,
rewrite, chmod, replacement, deletion, or other child creation is permitted. The
operator source checkout has no exception. No database, lock, config, rotated
log, sibling, or other `.chunkhound` artifact is allowed by this creation-only
rule.

CURe's materialized indexing config injects the exact glob
`**/.chunkhound/**` once, deduplicating any identical occurrence. Every daemon
startup attempt performs an installed-runtime effective-filter probe against
that materialized config. Probe evidence is scoped to the exact config digest
and installed runtime identity and is never reused after either changes. A
missing, malformed, stale, or degraded probe, or one that cannot demonstrate
the effective exclusion, fails before daemon/model startup. The probe authorizes
only the generation used by that attempt: CURe rejects every pre-existing or
unattested same-root generation, and after open requires the CURe-owned generation
newly opened under the exact probed config/runtime identity. A mismatch is closed
and fails before helper/model work.

The daemon log is reporting-only. A seeded unique log marker must be absent
from indexed corpus/chunk state, native `search`, native `code_research`,
readiness and witness selection, the final-index receipt, launch/generation
identity, and every expected-session identity/adjudication input. Reading or
observing the log can never establish readiness or substitute for structured
native status/search/research evidence.

### Explicit environment and identity

`JsonRpcSession` accepts an immutable copied environment. One launch identity contains the exact fields named in
`ExpectedSessionReceiptV1.launch_identity_projection`: resolved executable,
canonical root, resolved config path and digest, resolved database path, cwd,
curated environment key set, and non-reversible equality digest. Keeper and
helpers derive from and compare to that same immutable projection.

### Eligibility and ordering

A static Linux/Codex/helper-route gate runs before orientation or any other
model invocation. For a supported indexed helper route, final top-up indexing,
keeper bootstrap, expected-session adjudication, and existing helper preflight
also complete before optional orientation or any other model invocation.

```text
static eligibility
→ final index/top-up and expected-session receipt
→ keeper bootstrap and native daemon_status
→ expected-session witness (or bounded zero-chunk adjudication)
→ existing helper preflight
→ optional orientation
→ review model work
```

Fresh indexed Linux Codex helper routes require the keeper. Indexed helper-bearing routes on unsupported platforms/runtimes fail before any model. A supported route whose dynamic native behavior cannot be established likewise fails before any model, including orientation. HTTP/non-helper, `--no-index`, and `--no-review` routes remain keeper-ineligible and unchanged.

### Lifetime and concurrency

One keeper spans standard/big execution or multipass plan, concurrent steps,
retries, gaps, and synthesis. Eight helper proxies may overlap. CURe introduces
no query mutex or broker.

### Failure policy

One bounded retry is allowed only before any model dispatch. Missing
capabilities, unhealthy/degraded `daemon_status`, receipt/projection mismatch,
non-empty witness failure, and invalid empty-index adjudication are deterministic
failures. Loss after dispatch may have occurred is an infrastructure failure
with no replay.

### Tagged provider/helper process ownership and cleanup

One `OwnedProcessRegistry` in `run.py` is created only for a supported fresh
keeper route. `OwnedProcessRole` is exactly
`Literal["review-provider", "chunkhound-helper"]`; registry
`spawn(*, role, cmd, **popen_options)` creates a new Linux session/process group
and publishes it before returning. `run_cmd` and
`ReviewflowOutput.run_logged_cmd` gain optional paired `owned_processes` and
`owned_role` parameters; `run_llm_exec`/`run_codex_exec` gain optional
`owned_processes` and forward `review-provider`; direct
`_run_chunkhound_helper_preflight` gains the same optional registry and spawns
`chunkhound-helper`. Supplying only registry or role is invalid. Resume/follow-up,
HTTP, indexing, Git, Jira, and all other generic commands remain untagged and
unchanged.

The registry has synchronized `OPEN`, `CLOSING`, and `CLOSED` states. One
lock/condition covers the OPEN check, `Popen`, publication commit, normal
unregister, and OPEN → CLOSING terminal snapshot. Therefore exactly one of these
outcomes holds:

1. Spawn owns the lock first: its child is published before a terminator can mark
   CLOSING and is included in the terminal snapshot.
2. Teardown owns the lock first: a later spawn receives typed
   `OwnedProcessRegistryClosingError` before `Popen` and creates no child.
3. `BaseException` (including Ctrl-C) arrives after `Popen` returns but before
   publication commits: spawn retains local ownership and completes the same
   bounded process-group TERM/KILL/drain/reap before releasing the lock and
   re-raising; the child cannot become an unpublished orphan.

Publication after the CLOSING snapshot is impossible. The first
`terminate_and_drain(term_timeout_seconds=5.0, kill_timeout_seconds=2.0,
drain_timeout_seconds=2.0)` caller owns the snapshot and sends TERM, waits five
seconds, sends KILL only to registered survivors and waits two seconds, then
spends at most two seconds draining/reaping. It records the typed result and
moves to CLOSED; concurrent terminators wait on the condition for CLOSED and do
not signal twice. Normal completion retains registration until process exit plus
pipe/pump drain, then unregisters under the same synchronization. Survivors or
drain timeout are typed teardown failures. Ownership is never inferred from
repository root, daemon registry, or an arbitrary PID.

Nested cleanup enforces:

```text
registry OPEN → CLOSING, drain snapshot, reach CLOSED
→ close keeper exactly once
→ attempt bounded exact-generation/socket/DB-release observation
→ always remove sensitive staged state
→ return or report primary plus teardown outcome
```

A teardown failure cannot suppress sensitive cleanup or be reported as success.

### Privacy

Persist only lifecycle state, durations, tool-name availability, identity
equality, sanitized generation identity, retry count, release result, and typed
failure category. Never persist environment values, credentials, auth tokens,
raw registry data, full config, or unredacted stderr.

## Implementation Strategy

1. Add façade-owned RED tests and executable fake processes.
2. Add explicit environment and canonical bootstrap.
3. Implement the focused lease module.
4. Add static eligibility and fresh-review keeper ownership.
5. Add standard/big then multipass fault and concurrency coverage.
6. Add narrowly tagged provider/helper process-group ownership across `cure.py`, `cure_llm.py`, `cure_output.py`, and `run.py`, with untagged-call controls.
7. Add sealed lossless-capture/native-payload RED matrices parameterized over normal visible pumps, public `--quiet` silent pumps, and explicit `--no-stream` silent pumps. For each, cover valid and early malformed/conflicting recognized fields separated from later output by more than `capture_tail_chars`, write/pump/seal/read integrity and disposal, bounded memory, unchanged live/no-live and post-completion display behavior, then add deterministic Ctrl-C-at-publication and both spawn-versus-terminate lock-order RED matrices.
8. Allocate seeded/pre-existing/unattested same-root rejection and post-open ownership mismatch to deterministic TAP-02/TAP-03, with TAP-06 retaining static/config/manifest proof. Add enabled installed-ChunkHound TAP-05 proof as four clean-start cases crossing non-empty/zero-chunk with absent/existing-real-parent-log-absent state. TAP-05 must not seed or manipulate a pre-existing native generation and does not prove A13. It records immediate pre-open and pre-spawn absence, exactly one pre-spawn validation, newly lease-owned `ExpectedGenerationEvidence`, continuity through marker/native session/readiness/ordinary-client concurrency/pre-close, and release to absence. In every case it proves exact `['**/.chunkhound/**']` once and effectively excluded, marker/sibling/path absence, and the exact creation-only source boundary. A22 is final because all four enabled cases passed `4 passed in 68.54s`.
9. Add installed-wheel/release proof and documentation.

## Risks & Mitigations

- **Version-specific lifecycle/filtering:** perform a non-degraded installed-runtime effective-filter probe on every startup attempt, keyed to the exact materialized-config and runtime identity. Deterministic TAP-02/TAP-03 rejects every pre-existing/unattested same-root generation and requires the newly opened CURe-owned generation to match that probed identity. The enabled four-case TAP-05 canary separately proves clean-start continuity, exclusion, source boundary, and release without manipulating a pre-existing native generation.
- **Root-only daemon identity:** CURe validates the full launch tuple, rejects every pre-existing or unattested same-root generation, and closes any newly opened generation that is not CURe-owned under the probed exact identity.
- **Raw-tail truncation/display coupling:** final-index-only private lossless capture forces pump/spool transport independently of live display; normal, quiet, and explicit no-stream greater-than-bound valid/early-conflict tests prove tails cannot authorize receipts, silent modes emit no live lines, and no unbounded in-memory authority is introduced.
- **Worker cleanup races:** one OPEN/CLOSING/CLOSED lock-and-condition protocol orders creation/publication against the terminal snapshot; pre-publication interrupts locally drain and close-first spawns fail before `Popen`; deterministic both-ordering tests plus real cooperative/ignoring descendants precede keeper close.
- **Daemon-log source mutation/corpus contamination:** permit the exact directory-plus-log delta when both are absent or only the regular log when its parent already exists as a real directory; preserve the existing parent's type/mode/content metadata/siblings, every pre-existing reviewed-root entry, and every operator-checkout entry; reject invalid parents and preserve pre-existing logs fully; inject/dedupe exact `**/.chunkhound/**`. Across all four clean-start live cases, prove the unique marker, sibling, and daemon-log path are absent from corpus, search, research, readiness, witness, receipt, and identity evidence.
- **DB release ambiguity:** bounded observation with typed teardown failure.
- **Secret leakage:** allowlisted environment and recursive redaction tests.
- **Packaging drift:** isolated-wheel smoke and release-workflow ownership.
- **Scope creep:** helper, prompts, direct Codex MCP, resume/follow-up, and doctor remain unchanged.
