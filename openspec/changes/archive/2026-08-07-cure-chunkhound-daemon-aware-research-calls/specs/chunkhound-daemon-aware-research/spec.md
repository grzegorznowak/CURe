# Spec: chunkhound-daemon-aware-research

## Summary

Fresh indexed Linux Codex standard, big, and multipass reviews retain one parent-owned native ChunkHound MCP connection from final index/receipt readiness through optional orientation and all review model/helper work. Final-index receipt authority uses bounded-memory pump/spool capture in normal, public quiet, and explicit no-stream display modes without changing each mode's user-visible behavior. Generated helper calls remain independent but attach to that retained daemon generation.

## ADDED Requirements

### Requirement: Ordered keeper startup

For a supported indexed helper route, CURe MUST complete final indexing, expected-session receipt creation, keeper validation, expected-session adjudication, and helper preflight before optional orientation or any other model invocation.

#### Scenario: Eligible review starts
- **Given** an eligible indexed fresh review
- **When** CURe prepares model work
- **Then** the recorded order is final index/receipt readiness, keeper native-health and expected-session readiness, helper preflight, and first model dispatch, including optional orientation

### Requirement: Sequential daemon reuse

CURe MUST retain one native MCP client while sequential helper calls execute.

#### Scenario: Calls separated by an idle gap
- **Given** a held keeper
- **When** separate helper calls execute across an idle gap
- **Then** both observe one daemon generation without backend reinitialization

### Requirement: Phase-gap retention

The keeper MUST remain held across applicable standard, big, and multipass phases and retries.

#### Scenario: Multipass phase transitions
- **Given** an indexed multipass review
- **When** plan, step, retry, and synthesis boundaries occur
- **Then** one keeper remains continuously held

### Requirement: Independent concurrent clients

CURe MUST NOT broker or serialize helper calls.

#### Scenario: Eight overlapping workers
- **Given** eight effective multipass workers
- **When** their helper clients overlap
- **Then** eight independent proxies use one keeper-held daemon generation

### Requirement: Exact launch identity

Keeper and helper launches MUST exactly equal the immutable final-index receipt's launch-identity projection: resolved executable, canonical root, resolved config path and digest, resolved database path, cwd, curated-environment key set, and non-reversible environment equality digest.

#### Scenario: Launch identities are compared
- **Given** one review command
- **When** keeper and helper proxies launch
- **Then** both complete launch-identity tuples equal the receipt projection, while reviewed HEAD and final chunk count remain receipt-only fields

### Requirement: Curated environment

Keeper and helper MCP children MUST receive the same immutable allowlisted environment instead of arbitrary ambient parent state.

#### Scenario: Parent contains unrelated values
- **Given** unrelated parent environment values
- **When** keeper and helper children launch
- **Then** their curated environments are equal and exclude those values

### Requirement: Supported routes require the keeper

Every fresh indexed Linux Codex helper route in standard, big, or multipass mode MUST acquire the keeper.

#### Scenario: Supported route is classified
- **Given** a fresh indexed Linux Codex helper route
- **When** eligibility resolves
- **Then** keeper acquisition is mandatory

### Requirement: Unsupported helper-bearing routes fail early

An indexed helper-bearing route on an unsupported platform or runtime MUST fail before any model invocation.

#### Scenario: Unsupported helper route is classified
- **Given** an indexed helper-bearing unsupported route
- **When** static eligibility resolves
- **Then** CURe fails before its first model invocation

### Requirement: Keeper-ineligible routes bypass unchanged

HTTP/non-helper, `--no-index`, and `--no-review` routes MUST remain keeper-free and preserve their existing behavior.

#### Scenario: Keeper-ineligible route is classified
- **Given** a keeper-ineligible route
- **When** eligibility resolves
- **Then** CURe starts no keeper and preserves the route's existing behavior

### Requirement: Dynamic readiness fails closed

Missing required tools, bootstrap/readiness failure, degraded native daemon status other than exactly one typed waitable condition, launch-receipt mismatch, expected-session adjudication failure, any pre-existing or unattested same-root generation, or failure to prove the generation newly opened and owned by CURe under the current attempt's probed exact config/runtime identity MUST prevent every model dispatch without a cold-start fallback; any opened mismatch MUST be closed.

The sole waitable degraded condition MUST be proven from the documented status payload as active Watchman fresh-instance reconciliation: top-level `status` is `"degraded"`; `scan_progress.realtime.resync.needs_resync` is exactly `true`; `resync.last_reason` is exactly `"realtime_loss_of_sync"`; `resync.last_details.loss_of_sync_reason` is exactly `"fresh_instance"`; and `resync.last_details.backend` is exactly `"watchman"`. `scan_progress.scan_error` MUST be absent or exactly null; `realtime.last_error` and `resync.last_error` MUST each be present and exactly null; `realtime.service_state` MUST be a present string other than `"degraded"`; and `realtime.live_indexing_state` MUST be a present string other than `"stalled"`. Every other named container and field MUST be present with the stated type. The state fields are intentionally open vocabulary: only exact `realtime.service_state == "degraded"` and exact `realtime.live_indexing_state == "stalled"` are terminal state values, and any other string value is accepted. Unknown values in the exact discriminator/fault fields (`needs_resync`, `last_reason`, `loss_of_sync_reason`, `backend`, and the named error fields), missing or wrong-typed required named fields, malformed containers, contradictory or non-fresh evidence, and every otherwise degraded condition MUST be terminal. Under ordinary exact ready/true or initializing/false status, when a resync object supplies `needs_resync`, only exact boolean `false` is inactive historical evidence; exact `true` or any non-boolean value MUST be an active terminal contradiction. Unrelated unknown sibling fields outside the named paths MUST remain accepted and opaque. The wait MUST retain the same owned lease and generation, recheck liveness and generation on every probe, use the existing 600-second deadline and 0.5-second poll interval, and dispatch no search, helper, or model before exact ready/query-ready status. A22's startup/filter/generation semantics and the separate 60-second witness-search deadline remain unchanged.

#### Scenario: Active fresh-instance reconciliation is waitable
- **Given** one owned lease/generation reports the exact typed fresh-instance degraded condition
- **When** subsequent status probes transition through the same condition or exact initializing status to exact ready/query-ready status
- **Then** CURe retains that lease/generation within the existing readiness deadline and performs no search, helper, or model dispatch before ready

#### Scenario: Degraded evidence is not the sole benign condition
- **Given** degraded status with a scan, realtime, or resync error; degraded service state; stalled live indexing; a non-fresh or unknown named loss reason; a missing, wrong, or malformed backend discriminator; or other missing, wrong-typed, malformed, or contradictory named nested evidence
- **When** CURe adjudicates readiness
- **Then** the condition is terminal, owned cleanup runs once, and no search, helper, or model is dispatched

#### Scenario: Dynamic gate fails
- **Given** an eligible route with a failed dynamic gate
- **When** CURe prepares model work
- **Then** no model, including optional orientation, is dispatched and no zero-client fallback runs

### Requirement: Expected session index is validated

After final indexing, CURe MUST construct exactly one frozen versioned receipt from the final successful top-up attempt's sealed lossless stdout/stderr capture, exit code, and canonical identity inputs. This contract MUST hold for normal streaming, public `--quiet`, and explicit `--no-stream` fresh-review routes. The final-index owner MUST pass the optional capture only for final top-up attempts. Capture presence MUST force bounded-memory stdout/stderr pump transport independently of the existing user-visible `stream` boolean. Every decoded chunk MUST be teed into its corresponding private capture stream before bounded-tail eviction. When `stream=True`, normal mode MUST retain current live output; when quiet/no-stream sets `stream=False`, pumps MUST emit no live user lines and the sealed streams MUST be replayed in bounded chunks only through the existing post-completion log/progress path. Ordinary no-capture streamed and non-streamed commands MUST remain unchanged. The capture MUST seal only after both pumps join and exit is known, complete streams MUST NOT be materialized in memory, and every attempt MUST be disposed on success, retry, interruption, read/projector failure, and teardown. CURe MUST NOT authorize a receipt from bounded `CommandResult` tails or progress summaries. Capture write, pump, seal, read, replay-integrity, or disposal failure MUST fail before receipt, keeper, or model work. Exit MUST be zero; `total_chunks` and `error_files` MUST be present integers; every recognized occurrence across both complete streams, including occurrences displaced beyond `capture_tail_chars`, MUST be well formed and non-conflicting; `error_files` MUST be zero. Canonicalization/digest failure or unsupported/partial receipt construction MUST fail before keeper or model work. Repeated identical fields MAY normalize only when all occurrences agree. The receipt MUST contain schema version, canonical root, reviewed HEAD, resolved config path/digest, resolved database path, final chunk count, and the complete launch-identity projection. CURe MUST require strictly shaped native `daemon_status`, apply only the narrowly typed fresh-instance reconciliation wait defined by Dynamic readiness, eventually obtain exact healthy ready/query-ready status, and require exact equality between keeper identity and that projection. For a non-empty receipt it MUST additionally obtain the expected path and literal through a bounded deterministic path-constrained strictly shaped native `search`; malformed payload or missing witness MUST fail closed. Git-tracked witness selection MUST apply the materialized include/exclude policy with the same effective recursive-subtree semantics as the installed index filter: a `**/<component>/**` exclusion MUST exclude files at every depth beneath a matching root-level or nested directory, including deep descendants, and wildcard component matching MUST remain component-bounded. Excluded paths MUST NOT become witness candidates or expected-session evidence. For an authoritative zero-chunk receipt, it MUST accept only exact projection equality, the expected generation newly opened and owned by CURe for the current startup attempt under its probed exact config/runtime identity, and healthy native status, and MUST NOT treat an empty search result as proof of a non-empty index.

#### Scenario: Normal stream uses lossless authority and live display
- **Given** a normal final top-up emits valid recognized fields and more than `capture_tail_chars` of later output
- **When** visible pumps tee, join, and seal the per-attempt capture
- **Then** current live lines remain visible, complete capture remains authoritative when bounded tails omit fields, and only complete internally consistent zero-error evidence creates one `ExpectedSessionReceiptV1`

#### Scenario: Quiet route uses silent lossless authority
- **Given** a public `--quiet` final top-up emits the same valid or adversarial corpus
- **When** `stream=False` suppresses live presentation and capture presence forces silent pumps
- **Then** no command line is emitted live, complete sealed streams reach existing post-completion log/progress handling through bounded replay, and receipt/rejection results exactly match normal streaming without unbounded memory

#### Scenario: Explicit no-stream route uses silent lossless authority
- **Given** a public explicit `--no-stream` final top-up emits the same valid or adversarial corpus
- **When** `stream=False` suppresses live presentation and capture presence forces silent pumps
- **Then** no command line is emitted live, complete sealed streams reach existing post-completion log/progress handling through bounded replay, and receipt/rejection results exactly match normal streaming without unbounded memory

#### Scenario: Dropped early recognized data cannot authorize a receipt
- **Given** any supported display mode emits an early malformed or conflicting recognized field, more than `capture_tail_chars` of filler, and later valid-looking recognized fields
- **When** strict receipt projection scans every occurrence in the sealed complete stdout and stderr streams
- **Then** no receipt, keeper, or model is authorized even though the bounded command tails omit the early invalid evidence

#### Scenario: Lossless capture integrity fails
- **Given** any supported display mode has a final-index capture write, pump, seal, read, replay-integrity, or disposal failure
- **When** receipt construction runs
- **Then** CURe fails closed before receipt, keeper, or model work and disposes every available capture resource

#### Scenario: Native payload is malformed
- **Given** a native status or search error envelope, non-object, missing field, wrong-type field, or malformed result hit
- **When** expected-session adjudication runs
- **Then** CURe fails before any model work and does not authorize the zero branch

#### Scenario: Non-empty expected-index witness is queried
- **Given** a prepared session index whose final receipt reports searchable chunks
- **When** readiness validation runs
- **Then** native status is healthy and the keeper-held daemon returns the deterministic expected path and literal before any model work

#### Scenario: Prepared index has zero searchable chunks
- **Given** a successful authoritative final-index receipt reporting zero chunks
- **When** readiness validation runs
- **Then** exact receipt launch-projection equality, adjudication of the current attempt's newly opened CURe-owned generation under its probed exact config/runtime identity, and healthy strictly shaped native status establish the bounded empty-index result without inventing a search witness

#### Scenario: Searchable receipt has no valid witness
- **Given** a final-index receipt reporting one or more chunks
- **When** every bounded deterministic witness candidate fails
- **Then** CURe fails before any model work

#### Scenario: Recursive-root exclusions govern witness selection
- **Given** effective indexing config excludes `**/.claude/**` or another `**/<component>/**` subtree
- **When** Git-tracked files exist as deep descendants beneath a matching root-level or nested directory
- **Then** every such file is excluded from bounded witness candidacy and expected-session evidence
- **And** an eligible included file outside the excluded subtree may be selected instead

### Requirement: Mid-review loss is not replayed

Keeper or daemon loss after dispatch may have occurred MUST produce an infrastructure failure without automatic restart or replay.

#### Scenario: Keeper is lost after dispatch
- **Given** review work may already have started
- **When** continuity is lost
- **Then** CURe records infrastructure failure and repeats no uncertain work

### Requirement: Cleanup follows ownership order

Every terminal path, including Ctrl-C during child creation/publication, MUST synchronize owned spawn against teardown with one `OwnedProcessRegistry` OPEN/CLOSING/CLOSED protocol. The OPEN check, Linux process-group creation, publication, and OPEN-to-CLOSING terminal snapshot MUST be serialized so a spawn that wins is published before the snapshot and a teardown that wins causes spawn rejection before `Popen`; publication after CLOSING MUST be impossible. A `BaseException` after child creation but before publication MUST locally terminate/drain/reap that group before re-raise. The first terminator MUST own the snapshot and cleanup while concurrent terminators await CLOSED without duplicate signals. CURe MUST terminate and drain only owned `review-provider` and `chunkhound-helper` groups and descendants with 5-second TERM, 2-second KILL, and 2-second pipe/reap-drain budgets before closing the keeper exactly once and then attempting bounded daemon/database release observation. Untagged generic commands MUST retain existing behavior.

#### Scenario: Review reaches a terminal path
- **Given** tracked work and a held keeper
- **When** review execution unwinds
- **Then** registered groups receive bounded TERM/KILL/drain before one keeper close and release observation follows that close, while untagged commands receive no registry signal

#### Scenario: Ctrl-C interrupts creation before publication
- **Given** a Codex provider or direct helper-preflight `Popen` has created a group but publication has not committed
- **When** Ctrl-C interrupts spawn
- **Then** spawn locally applies bounded TERM/KILL/drain/reap, re-raises, and leaves no unpublished descendant before keeper close

#### Scenario: Spawn wins the publication race
- **Given** spawn holds the registry lock while terminal teardown is requested
- **When** spawn publishes and releases the lock
- **Then** teardown transitions to CLOSING, includes that group in its snapshot, drains it, and reaches CLOSED before keeper close

#### Scenario: Teardown wins the publication race
- **Given** teardown transitions the registry to CLOSING before a concurrent provider or helper spawn acquires the lock
- **When** the spawn checks registry state
- **Then** it receives the typed closing error before `Popen`, creates no child, and cannot publish after the terminal snapshot

### Requirement: Teardown failure cannot skip sensitive cleanup

Sensitive staged-state cleanup MUST execute despite close or release-observation failure, and the teardown failure MUST remain reportable.

#### Scenario: Release observation times out
- **Given** keeper release cannot be confirmed
- **When** nested cleanup continues
- **Then** sensitive state is removed and teardown failure remains visible

### Requirement: Lifecycle diagnostics are privacy-safe

Lifecycle diagnostics MUST exclude credentials, raw environments, daemon authentication material, unredacted sensitive stderr, raw exception text, native payload text, and repository paths. Fresh-route startup/readiness failures MUST expose and persist only an allowlisted stage and category sufficient to distinguish launch validation, lease open, generation attestation, witness selection, expected-session status, status timeout, and witness-search failure. The persisted `chunkhound_readiness_failure` value MUST contain only `stage` and `category`, and the public error MUST render only those values; exception class names and raw cause text MUST NOT be used as the diagnostic contract.

#### Scenario: Failure data contains secrets
- **Given** secret-bearing environment, subprocess output, exception text, native payload, or repository path
- **When** CURe reports or persists a lifecycle failure
- **Then** those sensitive values are absent
- **And** only the allowlisted privacy-safe `stage` and `category` are emitted and stored

#### Scenario: Witness no-hit remains attributable
- **Given** a valid native search returns no exact expected witness and its raw response contains sensitive path data
- **When** expected-session adjudication fails
- **Then** public and persisted diagnostics identify stage `expected_session` and category `witness_search`
- **And** the raw response, path, exception text, and credentials are absent

### Requirement: Helper tool mapping remains stable

The generated helper MUST preserve `search` and `research` mapping to the existing native tools.

#### Scenario: Helper tools are invoked
- **Given** keeper-enabled execution
- **When** helper search and research run
- **Then** they map to native `search` and `code_research` as before

### Requirement: Helper output remains stable

The generated helper MUST preserve its structured JSON success and failure contract.

#### Scenario: Helper emits a result
- **Given** any helper outcome
- **When** output is emitted
- **Then** it matches the normalized pre-change JSON contract

### Requirement: Helper timeouts remain stable

Helper preflight, search, and research MUST preserve their existing timeout behavior.

#### Scenario: Helper stage exceeds its budget
- **Given** a helper stage that exceeds its current budget
- **When** timeout handling runs
- **Then** the existing timeout outcome is preserved

### Requirement: Helper heartbeat remains stable

Long helper operations MUST preserve the existing five-second heartbeat behavior.

#### Scenario: Long operation remains active
- **Given** a helper operation longer than five seconds
- **When** it remains incomplete
- **Then** the existing heartbeat is emitted at the established cadence

### Requirement: Prompt instructions remain stable

Built-in helper-capable prompt instructions MUST remain unchanged.

#### Scenario: Prompt corpus is rendered
- **Given** the canonical built-in prompt corpus
- **When** keeper integration is present
- **Then** helper-use instructions are unchanged

### Requirement: Tool-proof semantics remain stable

Existing helper evidence acceptance and rejection semantics MUST remain unchanged.

#### Scenario: Proof fixtures are validated
- **Given** canonical positive and negative helper evidence
- **When** tool-proof validation runs
- **Then** the same fixtures remain accepted or rejected

### Requirement: Source boundaries are preserved

Keeper/index/lifecycle machinery MUST preserve every pre-existing reviewed-root entry in path, type, mode, symlink target, and content and MUST preserve every operator-source-checkout entry without exception. Ordinarily, the sole reviewed-root mutation permitted is native daemon lifecycle creation of the initially absent regular `<canonical-indexed-root>/.chunkhound/daemon.log`, creating its `.chunkhound/` parent as a directory only when the parent is absent. If that parent already exists as a real directory and the log is absent, lifecycle MAY create only the regular log and MUST preserve the parent's type, mode, content metadata, and every sibling. In the dedicated clean-start Watchman case, the installed native lifecycle MAY additionally materialize only regular files and directories beneath the initially absent `<canonical-indexed-root>/.chunkhound/watchman/` subtree. Every such path MUST remain confined beneath that subtree and the effective `**/.chunkhound/**` exclusion. A pre-existing log MUST be fully immutable; a parent that is a symlink or is not a directory MUST fail closed. Append, truncation, rewrite, chmod, replacement, deletion, and every config, database, lock, rotated log, sibling, or other `.chunkhound` artifact outside that narrow Watchman exception are forbidden.

CURe's materialized indexing config MUST inject and deduplicate the exact exclusion `**/.chunkhound/**`. On every daemon startup attempt, CURe MUST fail closed unless a non-degraded installed-runtime effective-filter probe for the exact materialized-config and installed-runtime identity demonstrates that exclusion; evidence MUST NOT be reused after either identity changes. The attempt MUST reject every pre-existing or unattested same-root generation. After opening, CURe MUST require the CURe-owned generation newly opened by that attempt under the exact probed materialized-config and installed-runtime identity; otherwise it MUST close and fail before helper/model work. The daemon log and dedicated Watchman runtime subtree MUST contribute to neither corpus/index state nor search, research, readiness, witness selection, receipt, launch/generation identity, or any expected-session identity/adjudication evidence.

#### Scenario: Initially absent native daemon log is created
- **Given** canonical manifests in which both the canonical indexed-root `.chunkhound/` path and its `daemon.log` are absent
- **When** native daemon lifecycle paths execute
- **Then** the only permitted reviewed-root manifest additions are that exact directory and that exact regular file
- **And** every pre-existing reviewed-root entry and every operator-checkout entry is unchanged in path, type, mode, symlink target, and content

#### Scenario: Clean-start Watchman runtime remains confined
- **Given** the dedicated installed-Watchman proof starts with no canonical `.chunkhound/watchman/` subtree
- **When** the native Watchman lifecycle materializes its packaged runtime
- **Then** aside from the ordinary `.chunkhound/` parent and regular `daemon.log` allowance, every additional Watchman-runtime path is a regular file or directory confined beneath `.chunkhound/watchman/`
- **And** at least one actual added path beneath `.chunkhound/watchman/` is a materialized regular file
- **And** every pre-existing reviewed-root entry, every path outside `.chunkhound/`, and every operator-checkout entry remains unchanged
- **And** the effective `**/.chunkhound/**` exclusion keeps those runtime artifacts outside corpus and expected-session evidence

#### Scenario: Existing real parent receives only an absent regular log
- **Given** the canonical indexed-root `.chunkhound/` parent already exists as a real directory with siblings and `daemon.log` is absent
- **When** native daemon lifecycle paths execute
- **Then** the only permitted reviewed-root addition is that exact regular `daemon.log`
- **And** the parent's type, mode, content metadata, and every sibling remain identical

#### Scenario: A daemon log pre-exists
- **Given** the canonical `daemon.log` pre-exists
- **When** keeper lifecycle startup is attempted
- **Then** the log and every other pre-existing entry remain byte- and metadata-identical
- **And** no append, truncation, rewrite, chmod, replacement, deletion, or other child creation is accepted

#### Scenario: Daemon-log parent is invalid
- **Given** the canonical `.chunkhound/` parent is a symlink or is not a directory
- **When** keeper lifecycle startup is attempted
- **Then** startup fails closed before lifecycle creation or helper/model work
- **And** every pre-existing entry remains byte- and metadata-identical

#### Scenario: Effective exclusion is proven for the generation used
- **Given** CURe has materialized the indexing config for a daemon startup attempt
- **When** CURe injects and deduplicates `**/.chunkhound/**`
- **Then** a non-degraded installed-runtime effective-filter probe for that exact config and runtime identity demonstrates the exclusion before daemon/model startup
- **And** missing, stale, malformed, degraded, or non-excluding evidence fails closed
- **And** every pre-existing or unattested same-root generation is rejected
- **And** only a CURe-owned generation newly opened by this attempt under that exact probed config/runtime identity may proceed; otherwise CURe closes and fails before helper/model work

#### Scenario: Daemon-log bytes are reporting-only
- **Given** a unique marker in the native daemon log and both non-empty and authoritative zero-chunk indexes
- **When** corpus, native search, native research, readiness, witness, receipt, and identity evidence are inspected
- **Then** the marker and daemon-log path contribute to none of them
- **And** log observation never substitutes for structured native readiness, search, or research proof

### Requirement: Installed wheel executes the production lifecycle API

Outside the source checkout, the isolated installed CURe wheel's production lifecycle API MUST complete fresh-resync readiness and terminal cleanup. Installed `cure --help` MUST separately verify the entrypoint. This requirement MUST NOT be interpreted as proof that the installed CLI executes `_pr_flow_impl`.

#### Scenario: Isolated wheel lifecycle API runs
- **Given** an isolated installed wheel outside the checkout and fake external executables
- **When** the installed production lifecycle API runs fresh-resync and terminal-failure cases
- **Then** that API completes readiness or terminal cleanup as appropriate
- **And** installed `cure --help` separately verifies the entrypoint without claiming installed CLI `_pr_flow_impl` execution

### Requirement: Installed-wheel proof is checkout-isolated

Installed-wheel smoke MUST load no CURe module from the source checkout.

#### Scenario: Module origins are inspected
- **Given** smoke execution outside the checkout with `PYTHONPATH` unset
- **When** CURe modules load
- **Then** every module origin belongs to the isolated wheel environment

### Requirement: Installed-wheel cleanup leaves no owned residue

Installed-wheel success, failure, and Ctrl-C lifecycle exit MUST leave no registered provider/helper descendant, keeper process, or database lock.

#### Scenario: Wheel lifecycle exits
- **Given** successful, failing, provider-Ctrl-C, or direct-helper-preflight-Ctrl-C installed-wheel lifecycle execution
- **When** the smoke exits
- **Then** no registered provider/helper descendant, keeper process, or database lock remains

## MODIFIED Requirements

None.

## REMOVED Requirements

None.
