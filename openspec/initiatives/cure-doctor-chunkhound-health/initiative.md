# CURe Doctor: ChunkHound Health Verification

source_of_truth: internal

## Goal / Context

`cure doctor` currently validates that ChunkHound is configured and its binary is on PATH, but
never verifies that the daemon, MCP transport, or query pipeline actually work. This creates a
silent failure mode: users launch a review, the agent spends minutes trying to use ChunkHound
tools, and only then hits an opaque error deep in the flow. This initiative adds two new checks
to `cure doctor`: a static `chunkhound-config-validate` that inspects `.chunkhound.json` for
missing required sections and suggests CURe's opinionated recommended configuration, and a
runtime `chunkhound-health` that runs a full end-to-end verification — MCP preflight, search,
and code_research — against a small self-contained fixture. When `cure doctor` passes, operators
can be confident ChunkHound will work during reviews. As a dependency, ChunkHound MCP/JSON-RPC
logic is extracted from the bloated `cure_llm.py` into a new `cure_chunkhound.py` module.

### Risks / unknowns

- ChunkHound research can be slow; timeout set at ~120s to avoid false warnings while still
  catching real failures
- The internal fixture must stay aligned with ChunkHound's expected input format
- The `cure_llm.py` → `cure_chunkhound.py` extraction may surface hidden import dependencies
- Fixture indexing may fail in CI if the `chunkhound` binary is not available

## Story Candidates

1. **Extract `cure_chunkhound.py`** — move `JsonRpcSession`, `_base_cmd()`, `_run_preflight()`,
   `_run_tool_once()`, `_daemon_metadata_payload()`, and `write_chunkhound_helper()` logic
   from `cure_llm.py` into a new `cure_chunkhound.py` module at project root. Refactor
   `_run_preflight()` as a public `run_chunkhound_mcp_preflight()` returning a
   `ChunkHoundPreflightResult` dataclass. `cure_llm.py`'s `write_chunkhound_helper()`
   reworked to import from `cure_chunkhound`; keeps `codex_mcp_overrides_for_reviewflow()`
   and `prepare_review_agent_runtime()`.

2. **Create health-check fixture** — add `_doctor_chunkhound_fixture/` at project root with 3–4 small
   files (Python + .md) containing searchable symbols. Provide a helper that creates a temp dir,
   indexes the fixture with `chunkhound index`, and tears down.

3. **Add `chunkhound-config-validate` doctor check** — static inspection of `.chunkhound.json`.
   Hard fail if `embedding` or `llm` sections are missing. Opinionated warn if values differ
   from CURe's recommended baseline (voyage-3.5-lite / deepseek-v4-flash).

4. **Add `chunkhound-health` doctor check** — runtime verification using the fixture: MCP
   preflight → search → code_research. Conditional on `chunkhound-config` and `chunkhound`
   binary passing first. Timeout ~510s worst case (index 120s + preflight 30s + search 60s + research 300s); warn on timeout if preflight succeeded, fail on
   preflight failure. Extend `_doctor_runtime_payload()` with structured `chunkhound_health`
   block.

5. **Tests** — unit tests for both new checks in `tests/_reviewflow_unittest_runtime_ui_impl.py`,
   integration test for the full fixture-based flow.

## Decisions & Constraints

- **New module `cure_chunkhound.py`** — all ChunkHound MCP/JSON-RPC logic extracted from
  the generated helper script in `cure_llm.py` into a reusable module; `write_chunkhound_helper()`
  refactored to generate a thin wrapper that imports from it. `cure_llm.py` keeps only
  codex-specific wiring.
- **Public preflight function** — `run_chunkhound_mcp_preflight(config_path, repo_path, timeout)`
  returns a `ChunkHoundPreflightResult` dataclass; hard errors via `ChunkHoundPreflightError`.
- **Self-contained fixture** — `_doctor_chunkhound_fixture/` at project root, indexed on-the-fly in a
  temp directory; no dependency on external databases or repos.
- **Full verification (level C)** — preflight + search + code_research against the fixture.
- **Timeout ~510s worst case** — indexing 120s + preflight 30s + search 60s + research 300s; warn if total time exceeded but preflight was OK; fail only if preflight fails.
- **Config validation baseline** — hard requirements: `embedding` and `llm` sections must exist.
  CURe opinionated recommendation (warn, not block):
  - embedding: provider=voyageai, model=voyage-3.5-lite, rerank_model=rerank-2.5, api_key set
  - llm: provider=deepseek, base_url=https://api.deepseek.com, synthesis_model=deepseek-v4-flash,
    utility_model=deepseek-v4-flash, api_key starts with sk-,
    codex_reasoning_effort_synthesis=high, codex_reasoning_effort_utility=high
- **Constraints**: must not break existing `cure doctor` or `cure pr` behavior; flat module
  structure at project root preserved (no `src/` subdirectory).
- **Out of scope**: changes to `chunkhound` binary, review flow (`cure_flows.py`), or other
  non-ChunkHound doctor checks.

## External Resources

(None)
