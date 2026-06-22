# Proposal: cure-doctor-chunkhound-health

## Goal / Context

`cure doctor` currently validates ChunkHound config and binary presence, but never verifies
the daemon, MCP transport, or query pipeline actually work — leading to silent failures deep
in review flows. This change extracts reusable ChunkHound MCP/JSON-RPC logic into a new
`cure_chunkhound.py` module, refactors `write_chunkhound_helper()` to generate a thin wrapper
that imports from it, adds a static `chunkhound-config-validate` doctor check that inspects
`.chunkhound.json` for missing sections and recommends CURe's opinionated configuration, and
adds a runtime `chunkhound-health` doctor check that indexes a self-contained fixture and
runs a full end-to-end verification (MCP preflight → search → code_research). When `cure
doctor` passes both checks, operators can be confident ChunkHound will work during reviews.

## Story Candidates

Single story — this change workspace is the full scope of the
`cure-doctor-chunkhound-health` initiative.

## Decisions & Constraints

- New module `cure_chunkhound.py` at project root (flat modules, no `src/` prefix)
- Reusable MCP/JSON-RPC logic extracted into `cure_chunkhound.py`; generated helper script
  imports from it instead of containing inline definitions
- Public preflight function `run_chunkhound_mcp_preflight()` returning
  `ChunkHoundPreflightResult` dataclass; hard errors via `ChunkHoundPreflightError`
- Self-contained fixture `_doctor_chunkhound_fixture/` at project root, indexed on-the-fly
  in temp dir
- Full verification (level C): preflight + search + code_research against the fixture
- Config validation: hard fail on missing `embedding`/`llm`, soft warn on non-recommended
  values per canonical recommendation table
- Timeout ~510s worst case (index 120s + preflight 30s + search 60s + research 300s)
- Shared artifacts mechanism between `_doctor_runtime_checks()` and `_doctor_runtime_payload()`
  to avoid re-executing expensive health checks
- New test file `tests/test_doctor_chunkhound.py`; existing ChunkHound doctor tests moved
- Must not break existing `cure doctor` or `cure pr` behavior

## External Resources

- Notebook: `cure-doctor-chunkhound-health`
- Initiative: `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`
