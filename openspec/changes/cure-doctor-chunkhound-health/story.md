Plan: 🟢 PLAN APPROVED
Status: ✅ DONE

## Purpose

`cure doctor` currently validates ChunkHound config and binary presence, but never verifies
the daemon, MCP transport, or query pipeline actually work — leading to silent failures deep
in review flows. This change extracts reusable ChunkHound MCP/JSON-RPC logic into a new
`cure_chunkhound.py` module, refactors `write_chunkhound_helper()` to generate a thin wrapper
script that imports from it, adds a static `chunkhound-config-validate` doctor check that
inspects `.chunkhound.json` for missing sections and recommends CURe's opinionated
configuration, and adds a runtime `chunkhound-health` doctor check that indexes a
self-contained fixture and runs a full end-to-end verification. When `cure doctor` passes
both checks, operators can be confident ChunkHound will work during reviews.

## Actors

- **Primary:** CURe operator running `cure doctor` — receives complete verification that
  ChunkHound is ready before launching a review
- **Secondary:** ChunkHound daemon — invoked by `cure doctor` for preflight and test queries
- **Affected:** Review agent (LLM) — benefits from ChunkHound tools being pre-verified;
  opaque mid-review failures are avoided
- **Reviewer:** CURe maintainer — verifies `cure_chunkhound.py` extraction does not break
  `cure_llm.py` or existing review flow

## Triggering Need

ChunkHound timeouts have been adjusted repeatedly (initialize 30s→60s→120s, search 15s→60s)
and research was deferred from multipass planning to scoped steps — all signals of recurring
integration friction. Today `cure doctor` cannot detect whether ChunkHound actually works;
operators only discover the problem minutes later, mid-review. This story provides early
visibility: `cure doctor` verifies the full pipeline before the review starts.

## Expected Prerequisites

None. No dependency on existing change workspaces.

External prerequisites for full `chunkhound-health` runtime check:

- `chunkhound` binary on PATH (validated by existing `chunkhound` doctor check)
- Valid embedding API credentials in the loaded ChunkHound config (`embedding.api_key`)
- Valid LLM API credentials in the loaded ChunkHound config (`llm.api_key`)
- Network access to embedding and LLM providers

When config credentials are missing or network is unavailable, `chunkhound-health` degrades
to `warn` rather than failing. The doctor uses the same ChunkHound config reported by
`chunkhound-config`; operators do not need to pass API variables manually.

## Scope

- New module `cure_chunkhound.py` at project root with reusable MCP/JSON-RPC logic:
  `JsonRpcSession`, `run_chunkhound_mcp_preflight()`, `run_chunkhound_tool()`,
  `daemon_metadata_payload()`, `ChunkHoundPreflightResult`, `ChunkHoundPreflightError`
- `cure_llm.py` refactored: `write_chunkhound_helper()` generates thinner wrapper script
  that imports from `cure_chunkhound` instead of containing all logic inline
- `codex_mcp_overrides_for_reviewflow()` and `prepare_review_agent_runtime()` unchanged
  in `cure_llm.py`
- Fixture `_doctor_chunkhound_fixture/` at project root with 3-4 files (Python + .md)
  and helper `index_fixture_for_health_check()` that creates temp dir, merges user config
  with fixture DB, indexes, returns context manager
- Doctor check `chunkhound-config-validate`: static `.chunkhound.json` inspection
  - Hard fail if `embedding` or `llm` sections missing
  - Opinionated warn if values differ from canonical CURe recommendation table
- Doctor check `chunkhound-health`: runtime verification against fixture
  - Merge user's `embedding`/`llm` config with fixture `database`/`indexing` into temp
    health-check config
  - Check `embedding.api_key` and `llm.api_key` in resolved ChunkHound config; if missing → `warn` (skip runtime check)
  - Index fixture → preflight (~30s) → search (~60s) → code_research (~300s)
  - Total worst case: ~510s (~8.5 min) including indexing
  - Search success: result contains at least one fixture file path
  - code_research success: response contains at least one citation to a fixture file
  - Fail on preflight failure, warn on code_research timeout if preflight+search passed
  - Gated on: `chunkhound-config` ok AND `chunkhound` binary ok AND `chunkhound-config-validate` ≠ `fail`
- Shared artifacts dict passed between `_doctor_runtime_checks()` and
  `_doctor_runtime_payload()` to avoid re-executing expensive health checks
- Extension of `_doctor_runtime_payload()` with `chunkhound_health` block
- Doctor check execution order:
  1. `chunkhound-config` (existing, load config from `cure.toml` — already before binary)
  2. `chunkhound-config-validate` (new, static — runs if config loaded, regardless of binary)
  3. `chunkhound` (existing, binary on PATH)
  4. `chunkhound-health` (new, runtime) — only if 1 ok AND 3 ok AND 2 ≠ `fail`
- New test file `tests/test_doctor_chunkhound.py`
- Migration of existing ChunkHound doctor tests from
  `tests/_reviewflow_unittest_runtime_ui_impl.py`
- `pyproject.toml`: register `cure_chunkhound` as py-module, add `_doctor_chunkhound_fixture/`
  as package data

## Out of Scope

- Changes to `chunkhound` binary
- Changes to `cure_flows.py` (review flow)
- Other non-ChunkHound doctor checks
- Persistent caching of the fixture database
- UI/TUI changes

## Scenarios / Behavior Examples

### S1 — Baseline: config matches recommendation
- Given: `.chunkhound.json` with `embedding` and `llm` sections matching canonical CURe
  recommendation
- When: `cure doctor` runs
- Then: `chunkhound-config-validate` → `ok` with detail "configuration matches CURe
  recommendation"
- Covers: A1

### S2 — Baseline: full runtime health check passes
- Given: valid config matching recommendation, valid API credentials, `chunkhound` on PATH
- When: `cure doctor` runs
- Then: `chunkhound-health` merges user config with fixture DB, indexes fixture, MCP
  preflight passes, search finds fixture file reference, code_research returns answer
  with citation to fixture file. `chunkhound-health` → `ok`.
- Covers: A2

### S3 — Config inválida: falta `embedding`
- Given: `.chunkhound.json` without `embedding` section
- When: `cure doctor` runs
- Then: `chunkhound-config-validate` → `fail` with detail "missing required section: embedding".
- Covers: A3

### S4 — Config inválida: falta `llm`
- Given: `.chunkhound.json` without `llm` section
- When: `cure doctor` runs
- Then: `chunkhound-config-validate` → `fail` with detail "missing required section: llm".
- Covers: A3

### S5 — Config warning: values differ from recommendation
- Given: `.chunkhound.json` with `embedding.model = "text-embedding-3-small"` and
  `llm.provider = "openai"`
- When: `cure doctor` runs
- Then: `chunkhound-config-validate` → `warn` with semicolon-joined detail listing each
  deviation.
- Covers: A4

### S6 — MCP preflight falla
- Given: valid `.chunkhound.json` with credentials, but `chunkhound mcp` fails to start
  (e.g. port conflict, corrupted DB)
- When: `cure doctor` runs
- Then: `chunkhound-health` → `fail` with preflight error details.
- Covers: A5

### S7 — code_research timeout pero preflight+search OK
- Given: fixture indexed, preflight and search pass, but code_research does not respond
  within 300s
- When: `cure doctor` runs
- Then: `chunkhound-health` → `warn` with detail "code_research timed out after 300s;
  preflight and search passed"
- Covers: A6

### S8 — Config sin credenciales de API
- Given: valid `.chunkhound.json` structure but empty `embedding.api_key` or `llm.api_key`
- When: `cure doctor` runs
- Then: `chunkhound-config-validate` → `warn` (static recommendation detects missing key).
  `chunkhound-health` → `warn` with detail "skipping runtime check: chunkhound config
  missing embedding/LLM api_key".
- Covers: A7

### S9 — Sin chunkhound en PATH
- Given: `chunkhound` not installed, but `.chunkhound.json` is valid
- When: `cure doctor` runs
- Then: `chunkhound-config-validate` still runs (config is loadable). Existing `chunkhound`
  check → `fail`. `chunkhound-health` is not executed (gated on binary check).
- Covers: A8

### S10 — `cure_llm.py` regression after extraction
- Given: `cure_chunkhound.py` created, `cure_llm.py` refactored to generate thin wrapper
- When: `cure pr` runs with ChunkHound enabled
- Then: `write_chunkhound_helper()` generates valid wrapper script; `codex_mcp_overrides_for_reviewflow()`
  returns identical overrides; `prepare_review_agent_runtime()` injects identical env vars;
  all existing review flow tests pass.
- Covers: A9

### S11 — `--json` output includes `chunkhound_health` block
- Given: `cure doctor --json` with ChunkHound working
- When: executed
- Then: JSON output contains `checks[]` with both new checks, plus `chunkhound_health` block
  with `preflight_stage`, `available_tools`, `daemon_pid`, `time_ms`.
- Covers: A10

### S12 — search returns zero results
- Given: fixture indexed but search regex matches nothing
- When: `cure doctor` runs the health check
- Then: `chunkhound-health` → `fail` with detail "search returned no results for fixture"
- Orientation only

## Acceptance

**A1:** `cure doctor` reports `chunkhound-config-validate: ok` when `.chunkhound.json` has
`embedding` and `llm` sections with values matching the canonical CURe recommendation table.
Covers: S1.

**A2:** `cure doctor` reports `chunkhound-health: ok` when MCP preflight passes, search
returns at least one result referencing a fixture file, and code_research returns an answer
containing at least one citation to a fixture file. Covers: S2.

**A3:** `cure doctor` reports `chunkhound-config-validate: fail` with detail naming the
missing section when `embedding` or `llm` is absent from `.chunkhound.json`. Covers: S3, S4.

**A4:** `cure doctor` reports `chunkhound-config-validate: warn` when config values differ
from the canonical CURe recommendation, with semicolon-joined detail listing each deviation.
Covers: S5.

**A5:** `cure doctor` reports `chunkhound-health: fail` with the preflight error when
`chunkhound mcp` fails to start. Covers: S6.

**A6:** `cure doctor` reports `chunkhound-health: warn` when code_research exceeds 300s but
preflight and search passed. Covers: S7.

**A7:** `cure doctor` reports `chunkhound-health: warn` with detail about missing config
credentials when `embedding.api_key` or `llm.api_key` is absent in the resolved ChunkHound
config, without attempting MCP connection. Covers: S8.

**A8:** `cure doctor` does not execute `chunkhound-health` when: (a) the `chunkhound`
binary is not on PATH, or (b) `chunkhound-config-validate` status is `fail`.
`chunkhound-config-validate` still runs in case (a) if config was loaded (static check).
Covers: S9, S3, S4.

**A9:** After `cure_chunkhound.py` extraction: `write_chunkhound_helper()` generates valid
wrapper script; `codex_mcp_overrides_for_reviewflow()` returns identical overrides; all
existing `cure pr` review flow tests pass unchanged. Covers: S10.

**A10:** `cure doctor --json` includes a `chunkhound_health` block in its output with
`preflight_stage`, `available_tools`, `daemon_pid`, `daemon_socket`, `time_ms`. Block is
absent when health check was skipped. Covers: S11.

## Verification

### Verification Commands

```bash
# Existing doctor tests (must keep passing)
pytest tests/_reviewflow_unittest_runtime_ui_impl.py -k "doctor" -v

# New chunkhound tests
pytest tests/test_doctor_chunkhound.py -v

# Regression: cure_llm.py still works after extraction
pytest tests/ -k "reviewflow" -v --timeout=120

# Lint & type check
ruff check cure_chunkhound.py cure_llm.py cure_runtime.py
mypy cure_chunkhound.py

# Smoke: doctor output includes new checks
cure doctor --json 2>&1 | python -c "import sys,json; d=json.load(sys.stdin); assert any(c['name']=='chunkhound-health' for c in d['checks'])"
```

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|---|---|---|---|---|---|---|---|---|---|
| TAP-1 | Unit | `cure_chunkhound.py` dataclasses and public functions | `tests/test_doctor_chunkhound.py` (new) | Module boundary: `cure_chunkhound` | Construction, serialization, error propagation | In-memory dataclass instances | `pytest tests/test_doctor_chunkhound.py` | N/A (pure unit) | New dataclasses, isolated from IO |
| TAP-2 | Unit | `chunkhound-config-validate`: fail on missing sections, warn on non-recommended, ok on match (A1, A3, A4) | `tests/test_doctor_chunkhound.py` (new) | Doctor check logic boundary | `DoctorCheck.status` and `detail` for each config variant | Mocked config dicts (missing embedding, missing llm, non-recommended values, matching, multiple warnings) | `pytest tests/test_doctor_chunkhound.py` | N/A (pure unit) | Config validation is stateless logic |
| TAP-3 | Unit | `chunkhound-health`: status mapping for preflight fail, search fail, research timeout/citation, all ok (A2, A5, A6) | `tests/test_doctor_chunkhound.py` (new) | Doctor check logic boundary | `DoctorCheck.status` for mocked stage outcomes | Mocked `ChunkHoundPreflightResult` + search/research results with staged outcomes | `pytest tests/test_doctor_chunkhound.py` | N/A (pure unit) | Status mapping is pure function |
| TAP-4 | Unit | `chunkhound-health`: config credential check → warn (A7) | `tests/test_doctor_chunkhound.py` (new) | Doctor check logic boundary | `DoctorCheck.status == "warn"` when resolved config lacks api keys | Mocked ChunkHound config with empty `embedding.api_key`/`llm.api_key` | `pytest tests/test_doctor_chunkhound.py` | N/A (pure unit) | Credential check is stateless |
| TAP-5 | Unit | Doctor skip: health absent when binary fails OR config-validate fails (A8) | `tests/test_doctor_chunkhound.py` (new) | Doctor orchestration boundary | Health absent when binary check fails OR when config-validate status is `fail`; config-validate still present when binary fails | Mocked binary/config-validate check results | `pytest tests/test_doctor_chunkhound.py` | N/A (pure unit) | Orchestration logic, isolated |
| TAP-6 | Unit | JSON payload block `chunkhound_health` (A10) | `tests/test_doctor_chunkhound.py` (new) | `_doctor_runtime_payload()` boundary | JSON dict has `chunkhound_health` key with required fields; absent when health skipped | Mocked preflight result injected into payload builder | `pytest tests/test_doctor_chunkhound.py` | N/A | Payload extension is additive |
| TAP-7 | Unit | Fixture helper: temp dir lifecycle + config merge | `tests/test_doctor_chunkhound.py` (new) | Temp dir + subprocess boundary | Temp config merges user embedding/llm with fixture DB; `chunkhound index` called with correct args | Mocked subprocess; real `tempfile` | `pytest tests/test_doctor_chunkhound.py` | Skip if `chunkhound` binary missing (CI constraint) | Fixture helper is pure orchestration |
| TAP-8 | Integration | `cure_llm.py` regression: helper script, overrides, env vars identical (A9) | `tests/` (existing review flow tests) | `cure_llm` → `cure_chunkhound` import boundary | `write_chunkhound_helper()` output is valid; `codex_mcp_overrides_for_reviewflow()` identical; all existing review flow tests pass | Existing test fixtures, no changes | `pytest tests/ -k reviewflow` | Revert extraction if import chain breaks | Regression gate for the refactor |
| TAP-9 | Migration | Existing ChunkHound doctor tests moved | `tests/test_doctor_chunkhound.py` (new) ← `tests/_reviewflow_unittest_runtime_ui_impl.py` | Test ownership boundary | Moved tests pass in new file; old file has no orphaned references | Extract from old file | `pytest tests/test_doctor_chunkhound.py` | Keep old tests if move breaks | Consolidate ChunkHound tests |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|---|---|---|---|---|---|---|
| A1 | final | Unit test (TAP-2) | `pytest tests/test_doctor_chunkhound.py -k config-validate` | Config with matching values → `ok` | `cure_runtime._doctor_runtime_checks()` | — |
| A2 | final | Unit/integration test (TAP-3, TAP-7) | `pytest tests/test_doctor_chunkhound.py -k health` | Mocked preflight+search+research stages ok → `chunkhound-health: ok`; fixture helper merges user config into temp config | `cure_runtime._doctor_runtime_checks()`, `cure_chunkhound.run_chunkhound_mcp_preflight()`, `_doctor_chunkhound_fixture.index_fixture_for_health_check()` | — |
| A3 | final | Unit test (TAP-2) | `pytest tests/test_doctor_chunkhound.py -k config-validate` | Config missing `embedding` → `fail`; missing `llm` → `fail` | `cure_runtime._doctor_runtime_checks()` | — |
| A4 | final | Unit test (TAP-2) | `pytest tests/test_doctor_chunkhound.py -k config-validate` | Non-recommended values → `warn` with semicolon-joined detail | `cure_runtime._doctor_runtime_checks()` | — |
| A5 | final | Unit test (TAP-3) | `pytest tests/test_doctor_chunkhound.py -k health` | Mocked preflight error → `fail` | `cure_runtime._doctor_runtime_checks()` | — |
| A6 | final | Unit test (TAP-3) | `pytest tests/test_doctor_chunkhound.py -k health` | Mocked research timeout → `warn` | `cure_runtime._doctor_runtime_checks()` | — |
| A7 | final | Unit test (TAP-4) | `pytest tests/test_doctor_chunkhound.py -k health` | Config missing api keys → `warn` "skipping runtime check" | `cure_runtime._doctor_runtime_checks()` | — |
| A8 | final | Unit test (TAP-5) | `pytest tests/test_doctor_chunkhound.py` | No binary OR config-validate fail → health absent | `cure_runtime._doctor_runtime_checks()` | — |
| A9 | final | Integration test (TAP-8) + unit assertion | `pytest tests/ -k reviewflow`; assert helper/overrides identity | All existing review flow tests pass; overrides dict identity | `cure_llm.py`, `cure_chunkhound.py` | — |
| A10 | final | Unit test (TAP-6) | `pytest tests/test_doctor_chunkhound.py` | JSON has `chunkhound_health` block; absent when health skipped | `cure_runtime._doctor_runtime_payload()` | — |

### Input Boundary Shape Risk

- **Fixture files**: 3-4 static files under `_doctor_chunkhound_fixture/`. Low risk —
  versioned with the repo; included via `pyproject.toml` package data.
- **Config JSON parsing**: input is a dict already parsed by
  `load_reviewflow_chunkhound_config()`. No injection risk.
- **Config merge (user + fixture)**: user's `embedding`/`llm` dict is merged with fixture
  `database`/`indexing` into a temp file. No injection risk.
- **Subprocess (chunkhound binary)**: path comes from `shutil.which`, already validated.
  No path traversal risk.
- **Temp dir**: uses `tempfile.TemporaryDirectory`, automatic cleanup via context manager.
- **Timeout**: `subprocess.run` with `timeout=` prevents indefinite doctor hangs.
- **API credentials**: read from the resolved ChunkHound config before MCP connection; no
  credentials are logged or included in doctor output.
- **Doctor runtime**: full health check may add ~8.5 min worst case. Operator visible
  via progress output per stage.

### Shared Artifacts Data Flow

`doctor_flow()` currently calls `_doctor_runtime_checks()` and `_doctor_runtime_payload()`
separately, and payload re-derives its own state. To share the expensive health check result:

```python
# cure_commands.py:doctor_flow()
artifacts: dict = {}
checks = _doctor_runtime_checks(runtime, ..., artifacts=artifacts)
...
payload = _doctor_runtime_payload(runtime, ..., artifacts=artifacts)
```

`_doctor_runtime_checks()` populates `artifacts["chunkhound_health"]` with the
`ChunkHoundPreflightResult` (or error/trace). `_doctor_runtime_payload()` reads it.
No re-execution.

## Critical Files

### Files to create

| File | Role |
|---|---|
| `cure_chunkhound.py` (new) | Reusable MCP/JSON-RPC logic: `JsonRpcSession`, `_base_cmd()`, `run_chunkhound_mcp_preflight()`, `run_chunkhound_tool()`, `daemon_metadata_payload()`, `ChunkHoundPreflightResult`, `ChunkHoundPreflightError` |
| `_doctor_chunkhound_fixture/__init__.py` (new) | Package + helper `index_fixture_for_health_check()` |
| `_doctor_chunkhound_fixture/main.py` (new) | Fixture: `def saludar()` |
| `_doctor_chunkhound_fixture/utils.py` (new) | Fixture: `def sumar(a, b)` |
| `_doctor_chunkhound_fixture/README.md` (new) | Fixture: searchable text |
| `tests/test_doctor_chunkhound.py` (new) | Unit tests for both checks + fixture helper + dataclasses |

### Files to modify

| File | Role |
|---|---|
| `cure_llm.py` | Refactor `write_chunkhound_helper()` to generate thinner wrapper that imports from `cure_chunkhound`. Keep `codex_mcp_overrides_for_reviewflow()` and `prepare_review_agent_runtime()` unchanged |
| `cure_runtime.py` | Add `chunkhound-config-validate` and `chunkhound-health` in `_doctor_runtime_checks()`. Extend `_doctor_runtime_payload()` with `chunkhound_health` block. Add `artifacts` dict parameter to both functions |
| `cure_commands.py` | Pass `artifacts` dict between `_doctor_runtime_checks()` and `_doctor_runtime_payload()` in `doctor_flow()` |
| `tests/_reviewflow_unittest_runtime_ui_impl.py` | Move existing ChunkHound doctor tests to `test_doctor_chunkhound.py` |
| `pyproject.toml` | Register `cure_chunkhound` as py-module; add `_doctor_chunkhound_fixture/` as package data |

## Implementation Notes

### Phases

**Phase 1: Extract `cure_chunkhound.py`** (smallest red-first seam)
- Create `cure_chunkhound.py` with dataclasses + tests (TAP-1) → RED
- Extract `JsonRpcSession`, `_base_cmd()`, `_run_preflight()` logic from generated script
  into reusable functions; `_run_preflight()` → public `run_chunkhound_mcp_preflight()` → GREEN
- Extract `_run_tool_once()` → `run_chunkhound_tool()`, `_daemon_metadata_payload()` →
  `daemon_metadata_payload()`
- Refactor `write_chunkhound_helper()` to generate thin wrapper that imports from
  `cure_chunkhound`
- Regression gate: `pytest tests/ -k reviewflow` (TAP-8), verify wrapper script is valid

**Phase 2: Fixture + helper**
- Create `_doctor_chunkhound_fixture/` with fixture files
- Implement `index_fixture_for_health_check(chunkhound_binary, user_config, timeout)`
  — temp dir, copy fixture, merge config, `chunkhound index`, return context manager
- Tests for helper (TAP-7) — mock subprocess, verify temp dir lifecycle + config merge

**Phase 3: Doctor checks**
- `chunkhound-config-validate`: static validation against canonical recommendation table → TAP-2
- `chunkhound-health`: orchestrate config credential check → fixture → preflight → search →
  research, map to status → TAP-3, TAP-4
- Integrate both in `_doctor_runtime_checks()` with gates → TAP-5
- Add `artifacts` parameter to `_doctor_runtime_checks()` and `_doctor_runtime_payload()`
- Update `doctor_flow()` in `cure_commands.py` to pass shared `artifacts` dict
- Extend `_doctor_runtime_payload()` → TAP-6

**Phase 4: Test migration + cleanup**
- Move existing ChunkHound doctor tests from `_reviewflow_unittest_runtime_ui_impl.py` →
  `test_doctor_chunkhound.py` → TAP-9
- Verify old file has no orphaned references
- `ruff check` + `mypy` on all modified files

### Notes
- The current generated helper script contains inline definitions of `JsonRpcSession`,
  `_base_cmd()`, `_run_preflight()`, etc. The extraction refactors these into
  `cure_chunkhound.py` and the helper script imports from it. Since the helper runs in
  the same venv where CURe is installed, `import cure_chunkhound` works.
- Red-first viable in each phase: dataclasses and status-mapping don't require real
  ChunkHound.
- Full health check adds ~8.5 min worst case to `cure doctor`; operator should be aware.
- API keys are never logged or included in doctor detail strings.

## Locked Decisions

| Decision | Rejected Alternative |
|---|---|
| New module `cure_chunkhound.py` for reusable MCP logic; helper script imports from it | Keep all logic inside generated script string (no reuse for doctor) |
| Extract all MCP/JSON-RPC logic at once | Extract only preflight (leaves inconsistent module) |
| Generated wrapper script imports `cure_chunkhound` at runtime | Duplicate logic in both module and script (divergence risk) |
| Self-contained fixture `_doctor_chunkhound_fixture/` | Depend on repo-local or session cache (non-deterministic) |
| Health config = user `embedding`/`llm` + fixture `database`/`indexing` merged | Use user config (wrong DB) or fixture config (no credentials) |
| Level C full check (preflight + search + code_research) | Preflight-only (misses corrupt/empty index) |
| Search success = fixture file reference; research success = fixture citation | Only check non-empty response (weak signal) |
| Timeout ~300s code_research, ~510s total worst case | Shorter timeout (false warnings) |
| Static validation: hard fail + soft warn; canonical recommendation table | Hard fail only (loses CURe opinionated guidance) |
| `warn` when ChunkHound config lacks API credentials | `fail` (would block doctor in CI/offline) |
| Shared `artifacts` dict between checks and payload | Re-execute health check for payload (wasteful, fragile) |
| Check ordering: config-validate independent of binary; health gated on both | Gating config-validate on binary (unnecessary; config already loaded) |
| New test file `tests/test_doctor_chunkhound.py` | Reuse old file (large, mixed concerns) |
| Fixture included via `pyproject.toml` package data | Assume files always available (fails on wheel installs) |

## Canonical CURe ChunkHound Recommendation Table

Hard requirements (fail if missing):
- `embedding` section must exist
- `llm` section must exist

Recommended values (warn if different):

| Section | Field | Recommended Value |
|---|---|---|
| embedding | provider | `voyageai` |
| embedding | model | `voyage-3.5-lite` |
| embedding | rerank_model | `rerank-2.5` |
| embedding | api_key | non-empty |
| llm | provider | `deepseek` |
| llm | base_url | `https://api.deepseek.com` |
| llm | synthesis_model | `deepseek-v4-flash` |
| llm | utility_model | `deepseek-v4-flash` |
| llm | api_key | non-empty, starts with `sk-` |
| llm | codex_reasoning_effort_synthesis | `high` |
| llm | codex_reasoning_effort_utility | `high` |

## Discovery Notes

- CURe uses flat root Python modules (no `src/` prefix): `cure_llm.py`, `cure_runtime.py`,
  `cure_commands.py`, etc. Registered in `pyproject.toml:17-19` as `py-modules`
- `write_chunkhound_helper()` at `cure_llm.py:1733` generates a standalone script string
  containing `JsonRpcSession` (line 2052), `_base_cmd()` (line 1951), `_run_preflight()`
  (line 2499), `_run_tool_once()` (line 2790), `_daemon_metadata_payload()` (line 1975)
  as inline definitions
- `doctor_flow()` at `cure_commands.py:1289` calls `_doctor_runtime_checks()` at line
  1291, then separately calls `_doctor_runtime_payload()` at line 1301 — payload re-derives
  state independently
- `_doctor_runtime_checks()` at `cure_runtime.py:3078` checks `chunkhound-config` at line
  3122 (check #4) BEFORE `chunkhound` binary at line 3198 (check #10)
- `load_reviewflow_chunkhound_config()` at `cure_runtime.py:2534` validates
  `base_config_path`, indexing overrides, and research algorithm in `cure.toml`; the
  actual `.chunkhound.json` content is read by `resolve_chunkhound_reviewflow_config()`
  at `cure_runtime.py:2622`

## Plan Review Log

- 2026-06-21T13:41:47Z Plan review run by fresh maintainer session
  - Verdict: request_changes
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; change artifacts `proposal.md`, `design.md`, `tasks.md`; no external issue/PR/Jira anchor found
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable
  - Code surfaces searched: `pyproject.toml`, `cure_llm.py`, `cure_runtime.py`, `cure_commands.py`, `tests/_reviewflow_unittest_runtime_ui_impl.py`, recent `git log --oneline -5`
  - Risk lenses reviewed: external I/O/subprocess/timeouts, generated helper artifact, JSON/config data shape, resource lifecycle/temp dirs, packaging/module layout, doctor JSON output schema
  - Evidence quality: confirmed repo layout and current doctor/helper surfaces; inferred no hidden external ticket intent beyond initiative/story; unknown exact ChunkHound env-var contract; provisional live MCP behavior remains manual by plan design
  - Finding closure: previous blockers partially closed, but config/health gating proof and extracted metadata API remain unresolved; repo-layout fix is present in change artifacts but initiative text is stale
  - Key findings:
    - [Blocker] `chunkhound-health` gating contradicts S2/S3/A3: story expects health not to execute when `chunkhound-config-validate` fails, but design/tasks gate only on existing `chunkhound-config` + binary and current `chunkhound-config` only checks a readable JSON object (`cure_runtime.py:2534-2556`, `story.md:111-119`, `design.md:289-296`, `tasks.md:97-99`). Add an explicit non-failing `chunkhound-config-validate` gate and TAP/acceptance proof, or change scenarios/acceptance to match execution.
    - [Blocker] TAP drift remains for the same path: TAP-5 proves only binary-failure skip (A8), while no TAP/proof row covers the S2/S3 promise that health is absent when required sections are missing (`story.md:246-249`, `story.md:259-266`).
    - [Blocker] Extracted metadata API is still under-specified: plan exposes `daemon_metadata_payload()` with no path parameters, while current generated helper passes `REPO_DIR` and `CHUNKHOUND_CWD` into the probe (`design.md:82`, `tasks.md:33-34`, `cure_llm.py:1975-1997`). The extraction contract needs an explicit signature/data flow for repo/cwd/binary/timeout.
    - [Warning] Repo-layout blocker is resolved in story/proposal/design/tasks using project-root flat modules, and live `pyproject.toml` confirms flat `py-modules`; however initiative text still references `src/cure/...` and should be updated or explicitly superseded (`proposal.md:22-27`, `design.md:30`, `pyproject.toml:17-18`, `initiative.md:30-35`, `initiative.md:58-69`).
  - Hypothesis triage: config validation fail path -> health-gate contradiction -> inspect current `load_reviewflow_chunkhound_config` and TAP rows; metadata extraction -> missing repo/cwd parameters -> inspect current generated probe callsites
  - Debt Friction: none
  - Next action: edit `story.md`, `design.md`, and `tasks.md` to align the config-validation gate/proofs and metadata extraction signature, then re-run `/openspec-story-plan-review cure-doctor-chunkhound-health cure-doctor-chunkhound-health` from a fresh session

- 2026-06-21T13:49:23Z Plan review run by fresh maintainer session
  - Verdict: request_changes
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; change artifacts `proposal.md`, `design.md`, `tasks.md`; no external issue/PR/Jira anchor found
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable
  - Code surfaces searched: `pyproject.toml`, `cure_llm.py`, `cure_runtime.py`, `cure_commands.py`, `cure_flows.py`, `tests/_reviewflow_unittest_runtime_ui_impl.py`, recent `git log --oneline -8`
  - Risk lenses reviewed: generated helper artifact, external I/O/subprocess/timeouts, JSON/config data shape, resource lifecycle/temp dirs, packaging/module layout, doctor JSON output schema; no UI/design-source lens applicable
  - Evidence quality: confirmed previous metadata signature and explicit config-validate health gate are now present in design/tasks/scope; confirmed live flat module packaging shape; inferred no hidden external ticket intent beyond initiative/story; unknown live ChunkHound behavior remains bounded by provisional/manual proof
  - Finding closure: previous metadata API blocker is closed; previous health-gate blocker is materially improved but still leaves a scenario/acceptance/proof traceability mismatch
  - Key findings:
    - [Blocker] `S1` is still one normative scenario covering two independently failing acceptance ids (`story.md:99-106`). The scenario funnel requires each normative scenario to carry exactly one `Covers: A<n>` link; split baseline config-validation success (A1) from runtime health success (A2), or reshape the acceptance/scenario contract.
    - [Blocker] The config-validation-fail health-skip path is still orphaned/misassigned: `S2`/`S3` state that `chunkhound-health` is not executed when required sections are missing (`story.md:108-120`), but they cover A3, whose wording only requires the `chunkhound-config-validate: fail` detail (`story.md:191-193`). TAP-5 and the A8 proof row now mention `config-validate` failure (`story.md:249`, `story.md:266`), but A8's acceptance text only covers a missing `chunkhound` binary (`story.md:207-209`). Add an explicit acceptance id or update A3/A8 so the scenario, acceptance, TAP row, and proof matrix all name the same health-skip obligation.
    - [Warning] Packaging proof is thin for the fixture: live `pyproject.toml` currently lists only `packages = ["prompts"]` and `prompts` package data (`pyproject.toml:18-22`), while the plan says to add `_doctor_chunkhound_fixture/` as package data (`story.md:86-87`, `story.md:325`). Make the pyproject task/proof explicit enough to include the new package and its README in installed artifacts, not just source-tree tests.
  - Hypothesis triage: scenario funnel -> S1 multi-cover and S2/S3 health-skip path -> proof target story Acceptance/TAP/APM; package data -> fixture availability in installed wheel -> proof target `pyproject.toml` packaging rules
  - Debt Friction: none
  - Next action: run `/openspec-story-plan-resume cure-doctor-chunkhound-health cure-doctor-chunkhound-health` to fix the scenario/acceptance/TAP/APM traceability gaps, then re-run `/openspec-story-plan-review cure-doctor-chunkhound-health cure-doctor-chunkhound-health` from a fresh session

- 2026-06-21T13:55:33Z Plan review run by fresh maintainer session
  - Verdict: request_changes
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; change artifacts `proposal.md`, `design.md`, `tasks.md`; no external issue/PR/Jira anchor found; no delta spec files present
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable
  - Code surfaces searched: `pyproject.toml`, `cure_llm.py`, `cure_runtime.py`, `cure_commands.py`, `tests/_reviewflow_unittest_runtime_ui_impl.py`, recent `git log --oneline -8`
  - Risk lenses reviewed: generated helper artifact, external I/O/subprocess/timeouts, JSON/config data shape, resource lifecycle/temp dirs, packaging/module layout, doctor JSON output schema; no UI/design-source lens applicable
  - Evidence quality: confirmed current generated helper/doctor/package surfaces and current story/design/tasks fixes; inferred no hidden external ticket intent beyond initiative/story; unknown live ChunkHound behavior remains bounded by provisional/manual proof
  - Finding closure: previous metadata API, health gate, TAP-5/A8, and packaging-proof concerns are materially closed by the current design/tasks/proof rows; one scenario/acceptance funnel blocker remains
  - Key findings:
    - [Blocker] Scenario/acceptance traceability is still internally inconsistent. `S1` links only `Covers: A1` but still includes runtime health/code_research success that belongs to A2 (`story.md:99-106`, `story.md:191-197`). `S3` and `S4` link only `Covers: A3` while their Then clauses also assert `chunkhound-health` is not executed, which is the A8 obligation (`story.md:116-128`, `story.md:199-218`, `story.md:258`, `story.md:275`). Either remove the extra health assertions from those scenarios or split/retarget them so each normative scenario's `Covers:` link maps to the full behavior it states.
  - Hypothesis triage: scenario funnel -> S1/S3/S4 still bundle independently failing behaviors under a single Covers link -> proof target story Scenarios, Acceptance, TAP-5, and APM rows
  - Debt Friction: none
  - Next action: run `/openspec-story-plan-resume cure-doctor-chunkhound-health cure-doctor-chunkhound-health` to fix the remaining scenario/acceptance traceability text, then re-run `/openspec-story-plan-review cure-doctor-chunkhound-health cure-doctor-chunkhound-health` from a fresh session

- 2026-06-21T14:02:34Z Plan review run by fresh maintainer session
  - Verdict: request_changes
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟠 PLAN CHANGES REQUESTED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; change artifacts `proposal.md`, `design.md`, `tasks.md`; no external issue/PR/Jira anchor found; no delta spec files present
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable
  - Code surfaces searched: `AGENTS.md`, `pyproject.toml`, `cure_llm.py`, `cure_runtime.py`, `cure_commands.py`, `tests/_reviewflow_unittest_runtime_ui_impl.py`, recent `git log --oneline -8`
  - Risk lenses reviewed: generated helper artifact, external I/O/subprocess/timeouts, JSON/config data shape, resource lifecycle/temp dirs, packaging/module layout, doctor JSON output schema; no UI/design-source lens applicable
  - Evidence quality: confirmed prior S1/S3/S4 blockers are closed in the current story; confirmed live helper/doctor/package surfaces; inferred no hidden external ticket intent beyond initiative/story; unknown live ChunkHound behavior remains bounded by provisional/manual proof
  - Finding closure: previous blockers not re-flagged; new gate/proof traceability issue found for the config-warning branch
  - Key findings:
    - [Blocker] `S5` still states two independently failing behaviors under `Covers: A4`: `chunkhound-config-validate` warns for non-recommended values and `chunkhound-health` still runs when the validate result is `warn` (`story.md:127-133`). A4 only requires the warning detail (`story.md:199-201`), and the current proof rows for A4/TAP-2 only exercise static validation (`story.md:252`, `story.md:268`). The runtime gate contract says validate `warn` must not block health (`story.md:74`, `story.md:82`, `design.md:294-298`), but no acceptance/proof row proves the `warn -> health runs` orchestration branch. Add that behavior to A4/A8 (or a new acceptance id) and TAP/APM, or remove it from S5 if it is not required.
  - Hypothesis triage: config-warning branch -> possible implementation could gate health on `status == ok` and still satisfy A4's static proof -> proof target S5/A4/A8/TAP-5/APM gate coverage
  - Debt Friction: none
  - Next action: run `/openspec-story-plan-resume cure-doctor-chunkhound-health cure-doctor-chunkhound-health` to align the S5/A4 config-warning gate behavior with an acceptance id and proof row, then re-run `/openspec-story-plan-review cure-doctor-chunkhound-health cure-doctor-chunkhound-health` from a fresh session

- 2026-06-21T14:09:46Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟢 PLAN APPROVED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: `AGENTS.md`; initiative `openspec/initiatives/cure-doctor-chunkhound-health/initiative.md`; change artifacts `proposal.md`, `design.md`, `tasks.md`; no external issue/PR/Jira anchor found; no delta spec files present; no dependency/sibling story required
  - Traceability: forward complete; backward complete
  - Design trace: not applicable
  - Code surfaces searched: `pyproject.toml`; `cure_llm.py` generated helper surface (`write_chunkhound_helper`, `_base_cmd`, `_daemon_metadata_payload`, `_run_preflight`, `_run_tool_once`); `cure_runtime.py` ChunkHound config resolution, `_doctor_runtime_checks()`, `_doctor_runtime_payload()`; `cure_commands.py:doctor_flow()`; existing ChunkHound helper/doctor tests in `tests/_reviewflow_unittest_runtime_ui_impl.py`; recent `git log --oneline -8`
  - Risk lenses reviewed: generated helper artifact, external I/O/subprocess/timeouts, JSON/config data shape, credentials/no-log handling, resource lifecycle/temp dirs, packaging/module layout, doctor JSON output schema; no UI/design-source lens applicable
  - Evidence quality: confirmed story/proposal/design/tasks are aligned; confirmed live flat module packaging, current helper extraction source, doctor check/payload separation, and existing ChunkHound test ownership; inferred no hidden external ticket intent beyond initiative/story; unknown live ChunkHound behavior remains bounded by provisional/manual proof for A2
  - Finding closure: previous blockers, including the S5 config-warning scenario/proof drift, are closed by the current contract; no new blockers found
  - Key findings:
    - None — no new blocking findings.
  - Hypothesis triage: none
  - Debt Friction: none
  - Next action: `/openspec-story-claim cure-doctor-chunkhound-health cure-doctor-chunkhound-health` from a fresh session
