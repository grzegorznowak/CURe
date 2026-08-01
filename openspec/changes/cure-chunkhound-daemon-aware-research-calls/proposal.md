# Proposal: cure-chunkhound-daemon-aware-research-calls

## Goal / Context

Indexed Linux CURe reviews currently start a short-lived native
`chunkhound mcp` proxy for each generated-helper preflight, search, or research
call. These proxies already attach to ChunkHound's shared daemon, but zero-client
gaps allow the initialized backend to stop between calls.

This change retains the generated `cure-chunkhound` helper as the agent-facing
access and policy adapter while CURe holds one parent-owned ordinary MCP
connection open from final index readiness until all review agents and helper
calls finish. Final-index receipt capture uses the same bounded-memory pump/spool
transport in normal, public quiet, and explicit no-stream display modes while
preserving each mode's visible behavior. Standard, big, and multipass reviews
thereby reuse one daemon generation without adding a broker, changing helper
semantics, or persisting ChunkHound between unrelated commands.

## Story Candidates

This change implements the initiative's standard and multipass daemon-aware
research-call story.

## Decisions & Constraints

- Require the keeper for fresh indexed Linux Codex CLI standard, big, and initial
  multipass reviews that stage the generated ChunkHound helper.
- Fail indexed helper-bearing unsupported platforms/runtimes before model work;
  leave HTTP/non-helper, `--no-index`, and `--no-review` routes unchanged.
- Retain `cure-chunkhound`; helper calls remain independent native MCP proxies.
- Add one parent-owned retained ordinary MCP proxy per supported top-level review.
- The keeper holds the daemon alive but never brokers, serializes, interprets, or
  replays helper calls.
- Use one canonical MCP bootstrap for ordinary preflight and keeper acquisition.
- Require native `daemon_status` for generic health, then prove the expected
  prepared session through one frozen versioned final-index receipt with an exact
  launch-identity projection plus a deterministic path-constrained search witness;
  for an authoritative zero-chunk receipt, use the explicitly bounded
  projection/owned-generation health branch.
- Construct the receipt only from a sealed lossless capture of the final successful
  indexing invocation's complete stdout/stderr plus exit code. Final-top-up capture
  presence forces bounded-memory stdout/stderr pumps independently of the existing
  user-visible `stream` boolean: normal mode tees before tail eviction and displays
  live, while public `--quiet` and explicit `--no-stream` retain `stream=False`, tee
  without live lines, and replay sealed spools in bounded chunks only through the
  existing post-completion log/progress path. Reject missing/conflicting/malformed/
  error evidence anywhere in either stream, write/pump/seal/read integrity failure,
  receipt-construction failure, and malformed native status/search payloads before
  keeper or model work. Dispose every attempt, never load complete authority into
  memory, keep bounded command tails/progress summaries display-only, and leave all
  no-capture commands on their unchanged transport/display branches.
- Keeper and helpers exactly equal the receipt's resolved executable, canonical
  root, config path/digest, database path, cwd, and curated-environment projection.
- Complete final indexing, keeper acquisition, native health, expected-session
  adjudication, and helper preflight before optional orientation or any other
  model invocation on a supported indexed helper route.
- Retain it across plan, concurrent steps, retries, phase gaps, and synthesis.
- Permit one bounded startup retry only before any model work.
- Never replay uncertain work after dispatch may have occurred.
- For supported fresh routes only, own explicitly tagged Linux Codex-provider and
  direct-helper-preflight process groups and descendants. Serialize OPEN-state
  spawn creation/publication with the OPEN → CLOSING terminal snapshot so a
  spawn is either published before the snapshot, rejected before `Popen`, or
  locally drained if interrupted after creation but before publication; permit no
  post-snapshot publication. Apply 5-second TERM, 2-second KILL, and 2-second
  pipe/reap-drain budgets before closing the keeper. Leave every untagged generic
  command and excluded route unchanged.
- Drain tagged model/helper work before closing the keeper; then boundedly observe
  daemon/database release before sensitive cleanup.
- Sensitive cleanup still executes if teardown observation fails, while the
  teardown failure remains reportable.
- Fail closed on unsupported lifecycle behavior, failed readiness, identity
  mismatch, any pre-existing/unattested same-root generation, or failure to prove
  the newly opened CURe-owned generation under the probed exact config/runtime
  identity; close any opened mismatch before helper/model work.
- Leave `CHUNKHOUND_DAEMON_SHUTDOWN_DELAY` unset.
- Do not expose a legacy-lifecycle toggle.
- Preserve privacy-safe diagnostics and every pre-existing reviewed-source entry. The only reviewed-root mutation permitted is native lifecycle creation of the initially absent regular `<canonical-indexed-root>/.chunkhound/daemon.log`, creating its `.chunkhound/` parent as a directory only when the parent is absent. When the parent already exists as a real directory and the log is absent, create only the log and preserve the parent's type, mode, content metadata, and all siblings. A pre-existing log is fully immutable; a symlink or non-directory parent fails closed. Permit no operator-checkout exception and no other `.chunkhound` artifact.
- Inject and deduplicate the exact `**/.chunkhound/**` exclusion in CURe's materialized indexing config. On every startup attempt, with fresh evidence for each materialized-config or installed-runtime identity, fail closed unless the installed runtime's effective-filter probe is non-degraded and demonstrates the exclusion. Reject every pre-existing or unattested same-root generation, then require the generation newly opened and owned by CURe for that attempt to match the exact probed config/runtime identity; otherwise close and fail before helper/model work. The daemon log cannot contribute to corpus/index state, search, research, readiness, witness, receipt, launch/generation identity, or other expected-session identity evidence.

## External Resources

None.
