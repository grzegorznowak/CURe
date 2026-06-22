# Tasks: cure-doctor-chunkhound-health

## Setup & Prerequisites

- [x] Verify worktree at `~/cure-doctor-chunkhound-health` on branch
  `feature/cure-doctor-chunkhound-health`
- [x] Verify `chunkhound` binary is on PATH in dev environment
- [x] Read `cure_llm.py:1733-2990` — understand `write_chunkhound_helper()` and the
  generated script string containing `JsonRpcSession`, `_base_cmd()`, `_run_preflight()`,
  `_run_tool_once()`, `_daemon_metadata_payload()`
- [x] Read `cure_runtime.py:3078-3311` — understand `_doctor_runtime_checks()` ordering
  (chunkhound-config at line 3122, chunkhound binary at line 3198)
- [x] Read `cure_commands.py:1289-1310` — understand `doctor_flow()` and how it calls
  checks and payload separately
- [x] Read existing ChunkHound doctor tests in `tests/_reviewflow_unittest_runtime_ui_impl.py`
  — identify tests to migrate (~line 4880+ for doctor flow, ~line 88+ for helper/preflight)

## Core Implementation

### Extract `cure_chunkhound.py`

- [x] Create `cure_chunkhound.py` at project root with `ChunkHoundPreflightResult` dataclass
  and `ChunkHoundPreflightError` exception
- [x] Extract `JsonRpcSession` class from generated script string into `cure_chunkhound.py`
  as top-level class (adapt script-global refs to parameters: config_path, repo_path, cwd)
- [x] Extract `_base_cmd()` from generated script string into `cure_chunkhound.py` as
  `_base_cmd(config_path, repo_path)` — remove script-global refs
- [x] Refactor `_run_preflight()` logic from generated script string into public
  `run_chunkhound_mcp_preflight(config_path, repo_path, timeout)` returning
  `ChunkHoundPreflightResult`
- [x] Extract `_run_tool_once()` logic into `run_chunkhound_tool(config_path, repo_path,
  tool_name, arguments, timeout)` returning dict
- [x] Extract `_daemon_metadata_payload()` logic into `daemon_metadata_payload()` —
  adapt to use passed paths instead of script globals
- [x] Refactor `write_chunkhound_helper()` in `cure_llm.py`: generate thin wrapper script
  that imports from `cure_chunkhound` instead of containing all logic inline
- [x] Verify wrapper script is valid: can be executed, argparse works, dispatch routes
  to `cure_chunkhound` functions
- [x] Keep `codex_mcp_overrides_for_reviewflow()` and `prepare_review_agent_runtime()`
  unchanged in `cure_llm.py`
- [x] Update `pyproject.toml`: register `cure_chunkhound` in `py-modules` list

### Create fixture

- [x] Create `_doctor_chunkhound_fixture/__init__.py` with
  `index_fixture_for_health_check(chunkhound_binary, user_config, timeout)`:
  - Create temp dir
  - Copy fixture files (`main.py`, `utils.py`, `README.md`) into temp dir
  - Merge user's `embedding`/`llm` with fixture `database`/`indexing` into temp
    `chunkhound.json`
  - Run `chunkhound index <temp_dir> --config <temp>/chunkhound.json`
  - Return `(merged_config_path, repo_path, temp_dir_handle)` as context manager
- [x] Create `_doctor_chunkhound_fixture/main.py`:
  `def saludar() -> str: return "hola"`
- [x] Create `_doctor_chunkhound_fixture/utils.py`:
  `def sumar(a: int, b: int) -> int: return a + b`
- [x] Create `_doctor_chunkhound_fixture/README.md`:
  "Este es un proyecto fixture para verificar que ChunkHound funciona correctamente."
- [x] Update `pyproject.toml` to include `_doctor_chunkhound_fixture/` as package data
  so fixture files are available in installed packages/wheels
- [x] Verify fixture files are importable via `importlib.resources` or equivalent at
  runtime (not just source-tree tests)

### Add `chunkhound-config-validate` doctor check

- [x] Implement `_validate_chunkhound_config(config: dict) -> tuple[str, str]` in
  `cure_runtime.py` using the canonical recommendation table:
  - Hard fail if `embedding` or `llm` section missing
  - Warn if values differ from recommendation (semicolon-joined for multiple deviations)
  - Ok if all recommended values match
  - Recommendation table (single source of truth):
    - embedding: provider=voyageai, model=voyage-3.5-lite, rerank_model=rerank-2.5,
      api_key non-empty
    - llm: provider=deepseek, base_url=https://api.deepseek.com,
      synthesis_model=deepseek-v4-flash, utility_model=deepseek-v4-flash,
      api_key non-empty and starts with sk-,
      codex_reasoning_effort_synthesis=high, codex_reasoning_effort_utility=high
- [x] Add `chunkhound-config-validate` to `_doctor_runtime_checks()` after
  `chunkhound-config` passes (no binary gate — static check of loaded config)

### Add `chunkhound-health` doctor check

- [x] Implement `_doctor_chunkhound_health_check(runtime) -> tuple[DoctorCheck, object | None]`
  in `cure_runtime.py`:
  - Load user's validated ChunkHound config (embedding + llm)
  - Check API credentials (`embedding.api_key` + `llm.api_key`) in resolved config
  - If missing → `(DoctorCheck(status="warn", "skipping runtime check: ..."), None)`
  - Call `index_fixture_for_health_check(chunkhound_binary, user_config, timeout=120)`
  - Index fail → `(DoctorCheck(status="fail", ...), None)`
  - Index timeout → `(DoctorCheck(status="warn", ...), None)`
  - Call `run_chunkhound_mcp_preflight(merged_config_path, repo_path, timeout=30)`
  - Preflight fail → `(DoctorCheck(status="fail", ...), preflight_error)`
  - Call `run_chunkhound_tool("search", {"type": "regex", "query": "def saludar"}, timeout=60)`
  - Search no fixture ref → `(DoctorCheck(status="fail", ...), preflight_result)`
  - Call `run_chunkhound_tool("code_research", {"query": "como funciona la funcion saludar"}, timeout=300)`
  - Research timeout → `(DoctorCheck(status="warn", ...), preflight_result)`
  - Research no citation → `(DoctorCheck(status="warn", ...), preflight_result)`
  - Return `(DoctorCheck(status="ok", ...), preflight_result)`
- [x] Add `chunkhound-health` to `_doctor_runtime_checks()` gated on:
  - `chunkhound-config` check status is `ok`
  - `chunkhound` binary check status is `ok`
  - `chunkhound-config-validate` status is NOT `fail` (warn is ok)
- [x] Add optional `artifacts: dict | None` parameter to `_doctor_runtime_checks()`;
  when health check runs, store preflight result in `artifacts["chunkhound_health"]`
- [x] Add optional `artifacts: dict | None` parameter to `_doctor_runtime_payload()`;
  read `artifacts["chunkhound_health"]` and build structured block:
  - `preflight_stage`, `available_tools`, `missing_tools`, `mcp_transport`
  - `daemon_pid`, `daemon_socket`, `daemon_log`, `daemon_runtime_dir`
  - `time_ms`
  - Block absent when health was skipped
- [x] Update `doctor_flow()` in `cure_commands.py`:
  - Create `artifacts = {}`
  - Pass `artifacts=artifacts` to both `_doctor_runtime_checks()` and
    `_doctor_runtime_payload()`

## Verification & Proof

- [x] Create `tests/test_doctor_chunkhound.py`
- [x] **TAP-1**: Test `ChunkHoundPreflightResult` dataclass construction, defaults,
  and `ChunkHoundPreflightError` exception propagation
- [x] **TAP-2**: Parametrized tests for `_validate_chunkhound_config()` covering all
  fields in canonical recommendation table:
  - Config matching all recommendations → `("ok", ...)`
  - Config missing `embedding` → `("fail", ...)`
  - Config missing `llm` → `("fail", ...)`
  - Non-recommended provider/model/rerank_model/base_url/synthesis_model/utility_model
    → `("warn", ...)`
  - Empty api_key → `("warn", ...)`
  - LLM api_key not starting with `sk-` → `("warn", ...)`
  - Non-recommended reasoning effort → `("warn", ...)`
  - Multiple warnings → semicolon-joined detail
- [x] **TAP-3**: Tests for `chunkhound-health` status mapping:
  - Preflight OK, search OK with fixture ref, research OK with citation → `ok`
  - Preflight error → `fail`
  - Preflight OK, search returns no fixture results → `fail`
  - Preflight OK, search OK, research timeout → `warn`
  - Preflight OK, search OK, research returns no citation → `warn`
- [x] **TAP-4**: Test credential check → `warn` when resolved config has empty api keys
- [x] **TAP-5**: Test gating:
  - `chunkhound` binary check fails → health absent, config-validate present
  - `chunkhound-config-validate` status is `fail` → health absent
  - `chunkhound-config` check fails → both absent
- [x] **TAP-6**: Test `_doctor_runtime_payload()`:
  - `chunkhound_health` block present with all keys when health ran
  - Block absent when health skipped
- [x] **TAP-7**: Test `index_fixture_for_health_check()`:
  - Temp dir created with correct files
  - Temp config merges user embedding/llm with fixture database/indexing
  - `chunkhound index` called with correct args (mocked subprocess)
  - Temp dir cleaned up on context exit
- [x] **TAP-9**: Migrate existing ChunkHound doctor tests from
  `tests/_reviewflow_unittest_runtime_ui_impl.py` (both doctor-flow ~line 4880+
  and helper/preflight ~line 88+) to `tests/test_doctor_chunkhound.py`
- [x] Verify `tests/_reviewflow_unittest_runtime_ui_impl.py` has no orphaned imports
  after migration
- [x] **TAP-8**: Run full regression:
  `pytest tests/ -k "reviewflow" -v --timeout=120`
  — all existing review flow tests must pass
- [x] Additional regression: verify `write_chunkhound_helper()` output is valid
  Python; `codex_mcp_overrides_for_reviewflow()` returns identical dict
- [x] Run `ruff check cure_chunkhound.py cure_llm.py cure_runtime.py cure_commands.py`
- [x] Run `mypy cure_chunkhound.py`

## Integration & Cleanup

- [x] Smoke test: `cure doctor` output includes `chunkhound-health` and
  `chunkhound-config-validate` checks (if ChunkHound is configured)
- [ ] Smoke test: `cure doctor --json` includes `chunkhound_health` block
- [ ] Smoke test: `cure pr` with ChunkHound enabled completes a review (requires API keys)
- [ ] Verify `cure doctor` exit code: 0 if all checks pass, 1 if any fail
- [x] Update notebook page `cure-doctor-chunkhound-health` with implementation notes
- [ ] Commit with descriptive message referencing the initiative
