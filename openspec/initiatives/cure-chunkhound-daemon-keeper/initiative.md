# CURe ChunkHound Daemon Keeper

source_of_truth: internal

## Goal / Context

CURe review commands currently route each ChunkHound research request through a generated helper that creates and destroys a short-lived native MCP proxy. Those proxies already use ChunkHound's shared native daemon, but zero-client gaps allow the daemon and its initialized backend to shut down between indexing and later agent tool calls. This initiative will retain the helper as a thin access and policy layer while CURe holds one ordinary keeper connection open for each supported indexed Linux review command. Users should receive reliable standard and multipass research without repeated backend cold starts while CURe preserves every pre-existing entry in the source tree being reviewed and permits only the narrowly proven creation of the native daemon log described below. The initiative is complete when those routes have proven daemon reuse, startup, readiness, failure, concurrency, and cleanup behavior.

### Risks / unknowns

- ChunkHound lifecycle and effective filtering behavior may change between versions.
- A daemon may still be running while no longer healthy or serving the expected index.
- Shutdown may occur while agents are still working, leaving background processes or locked database files.
- Installed-package behavior may differ from development tests because of environment, executable-path, or packaging differences.
- The keeper approach may need reconsideration if ChunkHound cannot provide reliable readiness and shutdown behavior.

## Story Candidates

**Make standard and multipass research calls daemon-aware.** Retain the generated helper as a thin per-call access and policy adapter, and hold one ordinary native MCP keeper connection per top-level indexed Linux review command from final index readiness until all agent work ends. Existing helper calls continue to use independent native MCP proxies, which attach to the keeper-held daemon instead of cold-starting the backend. Add privacy-safe lifecycle reporting, native capability and expected-index checks, concurrent-client proof, and proof that successful reviews, failures, cancellation with Ctrl-C, and cleanup do not leave background processes or locked database files. Preserve CURe's source-boundary guarantee, narrowed only to creation of an initially absent canonical indexed-root `.chunkhound/` directory when needed and creation of its initially absent regular `daemon.log`, including when the parent already exists as a real directory, after proving the log is excluded from every research authority.

- **Archived**: `cure-chunkhound-daemon-aware-research-calls` was archived on 2026-08-07.

## Decisions & Constraints

Supported review agents will continue to invoke CURe's generated helper, and each helper call will continue to use its own native ChunkHound MCP proxy. CURe will keep the shared daemon alive by holding one additional ordinary keeper client connection open for the duration of a supported review command. The keeper will not broker, proxy, serialize, or replay agent research calls, and CURe will not implement ChunkHound's private IPC protocol or replace native connections with a shared query service.

CURe's review machinery must preserve every pre-existing reviewed-source entry byte-for-byte and metadata-for-metadata. The sole reviewed-root exception is creation by the native daemon lifecycle of exactly the initially absent regular `<canonical-indexed-root>/.chunkhound/daemon.log`, with its `.chunkhound/` parent created as a directory only when that parent is absent. If the parent already exists as a real directory and the log is absent, lifecycle may create only the regular log while preserving the parent's type, mode, content metadata, and every sibling. A pre-existing log is fully immutable; a parent that is a symlink or is not a directory fails closed. Every other pre-existing entry is immutable in path, type, mode, symlink target, and content; append, truncate, rewrite, chmod, replacement, and deletion are forbidden. No exception applies beneath an operator source checkout.

CURe's materialized ChunkHound indexing config must inject and deduplicate the exact exclusion `**/.chunkhound/**`. On every daemon startup attempt, and without reusing evidence across a changed materialized config or installed runtime identity, CURe must fail closed unless an installed-runtime effective-filter probe is non-degraded and demonstrates that exclusion. Probe authority is generation-bound: the attempt must reject any pre-existing or unattested same-root generation, and after opening must require the CURe-owned generation newly opened by that attempt under the exact probed materialized-config and installed-runtime identity; any mismatch must be closed and fail before helper/model work. The daemon log must contribute to neither corpus/index state nor search, research, readiness, witness, receipt, launch/generation identity, or any other expected-session identity evidence. CURe may write its own sandbox artifacts and may build or restore ChunkHound index and database state during priming.

Concurrent ChunkHound queries must remain supported. This initiative will not add cross-command locking for hypothetical index-rebuild conflicts unless evidence demonstrates a concrete need.

If ChunkHound fails after review work may have started, CURe must report the failure rather than automatically repeat work whose outcome is uncertain.

The keeper lifecycle will be the default for supported indexed standard and multipass reviews; CURe will not expose a user-selectable legacy zero-client lifecycle. Logs and diagnostics must not expose credentials, raw environments, daemon authentication data, or sensitive daemon output.

A supported indexed route that cannot establish the required native daemon behavior must fail before model work rather than silently run with repeated backend cold starts. `--no-index` and `--no-review` paths remain keeper-free. Normal CURe testing, type-checking, linting, packaging, and review gates remain required.

The following are outside this initiative:

- Keeping ChunkHound alive between unrelated CURe commands
- Building a CURe-owned ChunkHound broker or query service
- Modifying any pre-existing reviewed-source entry, creating any reviewed-root entry other than the exact creation-only native daemon-log exception, or modifying any operator-checkout entry
- Broad redesign of agent scheduling or cancellation
- Direct Codex-native MCP migration or removal of the generated helper
- Resume and follow-up routes, which are being deprecated separately
- Windows and interactive-review support
- Changes to `cure doctor`

## External Resources

None.
