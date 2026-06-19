# CURe Architecture

CURe ("Code Under Review") is a CLI tool that runs GitHub pull request reviews inside isolated sandboxes, backed by ChunkHound code search and a configurable LLM review agent.

This document describes the internal architecture: how modules connect, what happens during a review, and how data flows through the system.

## High-Level Overview

```
┌──────────────────────────────────────────────────────────┐
│                    CLI Entry Point                        │
│                  cure_commands.py                         │
│         (argparse dispatch → command flows)               │
└──────────┬───────────────────────────────────┬────────────┘
           │                                   │
    ┌──────▼──────┐                   ┌────────▼────────┐
    │  Bootstrap   │                   │  Review Flows   │
    │  & Config    │                   │  cure.py /      │
    │  cure_runtime│                   │  cure_flows.py  │
    └──────┬──────┘                   └────────┬────────┘
           │                                   │
           │              ┌────────────────────┼──────────────┐
           │              │                    │              │
    ┌──────▼──────┐  ┌────▼─────┐  ┌──────────▼──┐  ┌───────▼───────┐
    │   Paths &   │  │ Session  │  │  LLM Exec   │  │  ChunkHound   │
    │   Config    │  │ State    │  │  Layer       │  │  Integration  │
    │  paths.py   │  │cure_     │  │ cure_llm.py │  │  cure_flows.py│
    │  cure.toml  │  │sessions  │  │ cure.py     │  │  (indexing,   │
    └─────────────┘  │  .py     │  └──────┬──────┘  │   helper)     │
                     └──────────┘         │         └───────────────┘
                                   ┌──────┴──────┐
                                   │  Subprocess  │
                                   │   Runner     │
                                   │   run.py     │
                                   └─────────────┘
```

## Module Responsibilities

### `cure_commands.py` — CLI Dispatch & Top-Level Flows

The primary entry point for all user-facing commands. Receives parsed `argparse.Namespace` arguments and delegates to the appropriate flow function. Owns the command catalog (`commands --json`), `setup`, `doctor`, `status`, `watch`, `clean`, `set-agent`, and `cache` subcommands. For review-producing commands (`pr`, `resume`, `followup`, `interactive`), it delegates to `cure.py` via thin wrappers.

### `cure.py` — Core Implementation (the "shell")

The largest module (~13k lines). Contains the canonical implementation of all review-producing flows. Key responsibilities:

- **`_pr_flow_impl`** — Full new-review pipeline: resolve PR metadata, create sandbox, clone repo, build ChunkHound index, resolve LLM config, run multipass review, finalize artifacts.
- **`_resume_flow_impl`** — Resume a failed or partially-completed multipass session from a specific phase (plan, steps, synth).
- **`_followup_flow_impl`** — Run a follow-up review on a completed session after the PR HEAD has advanced.
- **`_interactive_flow_impl`** — Interactive review mode with operator-in-the-loop.
- **Multipass orchestration** — Plan decomposition, parallel step execution with worker pools, synthesis, grounding validation.
- **LLM execution dispatch** — `run_llm_exec` routes to Codex CLI, Claude CLI, or HTTP providers.
- **ChunkHound helper** — Generates a standalone Python script (`cure-chunkhound`) that wraps ChunkHound daemon access for CLI-provider review sessions.
- **Session lifecycle** — `SessionProgress` class manages `meta.json` state throughout a review.

### `cure_flows.py` — Sandbox & Index Operations

Handles the lower-level sandbox setup and ChunkHound indexing operations:

- **PR stats computation** (`compute_pr_stats`) — Git-based diff stats to determine review profile.
- **Prompt profile resolution** — Selects "normal" vs "big" prompt templates based on PR size.
- **ChunkHound prompt contracts** — Defines which prompts require `search` and `code_research` tool proofs.
- **Base cache management** — Seed repo operations, base cache build/refresh with file locking.
- **Embedding config discovery** — Auto-detects embedding API keys and persists config.
- **Repo-local ChunkHound config discovery** — Finds `chunkhound.json` / `.chunkhound.json` in the target repo.

### `cure_llm.py` — LLM Execution Adapters

Abstracts the differences between LLM providers:

- **`run_llm_exec`** — Provider-agnostic dispatch (mirrors the version in `cure.py` but delegates back to it).
- **Codex CLI adapter** — Builds command-line flags, manages sandbox permissions, captures events from JSONL logs.
- **Claude CLI adapter** — Runs `claude` with prompt piped via stdin, captures streaming events, extracts tool usage and review artifacts.
- **HTTP adapter** — For OpenAI/OpenRouter Responses API calls.
- **ChunkHound helper generation** — Writes a self-contained helper script that manages daemon lifecycle, preflight checks, and tool call timeouts.
- **Auth staging** — Copies `gh`, Jira, and `.netrc` credentials into the sandbox work directory.

### `cure_sessions.py` — Session State & Resolution

Pure-logic module (no subprocess calls) for session state management:

- **`PullRequestRef`** — Immutable PR identity (host/owner/repo/number).
- **Session resolution** — Finds sessions by ID or PR URL, selects the best candidate for `resume`, `status`, `watch`, etc.
- **Review verdicts** — Extracts and normalizes `APPROVE`/`REJECT`/`REQUEST CHANGES` verdicts from markdown review artifacts.
- **LLM meta normalization** — Resolves legacy Codex-only metadata to the unified `llm` schema.
- **`build_status_payload`** — Assembles the full JSON status payload for a session.

### `cure_runtime.py` — Runtime Configuration Resolution

Resolves the full runtime environment from CLI args, env vars, and TOML config:

- **`ReviewflowRuntime`** — Frozen dataclass holding resolved config path, paths, and codex config path with their provenance sources.
- **Config path cascade** — CLI flag → env var → `cure.toml` → XDG defaults.
- **ChunkHound config loading** — Reads `[chunkhound]` from `cure.toml`, resolves `base_config_path`, overlay indexing/research settings.
- **LLM preset resolution** — Resolves which provider (codex-cli, claude-cli, openai-responses, openrouter-responses) to use from saved preferences, env, or autodetection.
- **Local agent selection** — Detects installed `codex`/`claude` executables, applies saved preferences, surfaces readiness status.
- **Doctor checks** — Runs a structured health-check suite (`_doctor_runtime_checks`) and produces a machine-readable payload.
- **Review intelligence config** — Parses the `[review_intelligence]` source registry (GitHub, Jira) and builds prompt guidance.
- **Multipass defaults** — Reads `[multipass]` from config (grounding_mode, step_workers, max_steps).

### `paths.py` — Path Layout

Defines the filesystem layout conventions:

- **XDG-compliant defaults** — Config in `~/.config/cure/`, state in `~/.local/state/cure/sandboxes/`, cache in `~/.cache/cure/`.
- **`ReviewflowPaths`** — Frozen dataclass with `sandbox_root`, `cache_root`, derived `seeds_root`, `bases_root`.
- **Seed/base directory naming** — `<cache_root>/seeds/<host>/<owner>/<repo>` and `<cache_root>/bases/<host>/<owner>/<repo>/<base_ref>`.

### `cure_output.py` — Output, TUI & Logging

Handles all user-facing output:

- **`ReviewflowOutput`** — Manages the TUI dashboard lifecycle (start/stop/redraw).
- **Dashboard rendering** — Reads `meta.json` to produce a live terminal dashboard with phase status, multipass step progress, ChunkHound index stats.
- **Structured logging** — `log()` writes to both stderr and the session log file.
- **Review artifact footer** — Appends provenance watermarks to completed review markdown.
- **Claude/Codex event parsing** — Extracts tool call progress, assistant messages, and usage stats from provider event streams.

### `ui.py` — Terminal UI Primitives

Low-level TUI building blocks:

- **`Dashboard`** — Full-screen terminal dashboard with keyboard input handling (verbosity cycling, help toggle, quit).
- **`UiState`** — Thread-safe state for the TUI (verbosity level, help visibility, stop/redraw signals).
- **`TailBuffer`** — Circular buffer for capturing the tail of streaming output.

### `run.py` — Subprocess Execution

Thin wrapper around `subprocess.Popen`/`subprocess.run`:

- **`run_cmd`** — Runs a command with optional streaming to stderr, tail capture, and structured error reporting.
- **`CommandResult`** — Frozen dataclass with cmd, cwd, exit_code, duration, stdout, stderr.

### `cure_errors.py` — Error Types

- **`ReviewflowError`** — Base exception for all CURe user-facing errors.
- **`StepGroundingValidationError`** — Raised when multipass grounding validation fails in strict mode.

### `meta.py` — JSON Persistence

- **Secret redaction** — Recursively redacts keys like `api_key`, `token`, `password` before writing to disk.
- **`write_json` / `write_redacted_json`** — Atomic JSON writes (write to `.tmp`, then `os.replace`).

### `cure_branding.py` — Product Identity

Constants: `PRODUCT_NAME = "CURe"`, `PRIMARY_CLI_COMMAND = "cure"`, `RUNTIME_SLUG = "cure"`.

### `chunkhound_summary.py` — Index Summary Parser

Parses ChunkHound index output (files processed, chunks, embeddings, duration) from log text for display in the TUI.

### `prompts/` — Review Prompt Templates

Markdown templates with `{{VARIABLE}}` placeholders, selected by prompt profile and multipass stage:

| Template | Purpose |
|----------|---------|
| `default.md` | Fallback single-pass prompt |
| `mrereview_gh_local.md` | Normal-size PR single-pass |
| `mrereview_gh_local_big.md` | Large PR entry (triggers multipass) |
| `mrereview_gh_local_big_plan.md` | Multipass: plan decomposition |
| `mrereview_gh_local_big_step.md` | Multipass: individual step execution |
| `mrereview_gh_local_big_synth.md` | Multipass: final synthesis |
| `mrereview_gh_local_big_followup.md` | Follow-up after HEAD advance |
| `mrereview_gh_local_followup.md` | Normal-size follow-up |
| `mrereview_gh_local_big_resume_*.md` | Resume variants (plan/step/synth) |

## Flow of a `cure pr` Review

This is the primary operation. Here is what happens step by step:

### 1. Bootstrap & Validation

```
CLI args → cure_commands.pr_flow() → cure._pr_flow_impl()
```

- Resolve runtime config (`cure_runtime.resolve_runtime`)
- Check bootstrap readiness (ChunkHound binary, embedding config, agent selection)
- If TTY and not ready, enter the setup wizard
- Parse the PR URL into `PullRequestRef`

### 2. PR Metadata Resolution

- Fetch PR metadata via `gh api` (base ref, head SHA, title)
- Resolve baseline selection (which base branch to diff against)
- Check for existing completed sessions; handle `--if-reviewed` policy

### 3. Session Creation

- Generate a unique session ID: `{owner}-{repo}-pr{number}-{timestamp}-{hex}`
- Create session directory structure:
  ```
  <sandbox_root>/<session_id>/
    meta.json          # Session state (written throughout)
    review.md          # Final review artifact
    agent_desc.txt     # Optional operator description
    repo/              # Cloned repository
    work/
      tmp/
      chunkhound/      # ChunkHound workspace
        chunkhound.json
        .chunkhound.db
      logs/
        cure.log
        chunkhound.log
        codex.log       # or claude.events.jsonl
      review_plan.json  # Multipass plan
      review.step-01.md # Step artifacts
      review.step-02.md
      ...
  ```
- Initialize `meta.json` with PR identity, paths, options
- Start TUI dashboard if interactive

### 4. LLM Config Resolution

- Resolve which provider to use (codex-cli, claude-cli, openai-responses, openrouter-responses)
- Cascade: CLI flag → env var → `cure.toml` `[llm].default_preset` → autodetect from PATH
- On TTY with unset model/effort, show an interactive picker
- Resolve per-stage LLM configs for multipass (plan, step, synth can have different effort levels)

### 5. Base Cache Build

- Ensure a seed clone exists at `<cache_root>/seeds/<host>/<owner>/<repo>`
- Build or refresh the base cache at `<cache_root>/bases/.../<base_ref>/`
- This is a ChunkHound index of the base branch, reusable across reviews
- File-locked to prevent concurrent builds
- TTL-based refresh (default 24 hours)

### 6. Sandbox Clone & Checkout

- Clone from the seed (local hardlinks for speed)
- Reset remote URL to the real origin
- Fetch + checkout the base branch
- `rsync` file timestamps from seed (preserves ChunkHound cache validity)
- `gh pr checkout` the PR branch
- Create `cure_base__<base_ref>` branch for the diff baseline

### 7. ChunkHound Indexing (Top-Up)

- Copy the base cache DuckDB into the session's ChunkHound workspace
- Run `chunkhound index` as a top-up (only indexes files changed in the PR)
- Materialize the runtime ChunkHound config (embedding settings, include/exclude patterns)
- Verify the index with a compatibility canary

### 8. Multipass Review Execution

For "big" PRs (auto-detected by file/line thresholds), the review runs in three stages:

#### 8a. Plan Stage

- Render the plan prompt template with PR context, diff stats, review intelligence guidance
- Run through the LLM (Codex/Claude/HTTP)
- Parse the returned JSON plan: an ordered list of review steps, each with a focus area and title
- Persist plan to `work/review_plan.json`

#### 8b. Step Stage (Parallel)

- For each step in the plan, render a step prompt with the step's focus area
- Execute steps in parallel using a `ThreadPoolExecutor` (default 4 workers, max 8)
- Each step produces a `review.step-{NN}.md` artifact
- After each step completes, run **grounding validation**: verify that file:line citations in the step output actually exist in the repo
- In strict mode, invalid grounding fails the step (with retry); in warn mode, it records findings and continues
- Track step states: queued → running → awaiting_validation → completed/failed/grounding_skipped

#### 8c. Synthesis Stage

- Render the synthesis prompt with all completed step artifacts as input
- Run through the LLM to produce the final unified `review.md`
- The review has stable headings: Summary, Business/Product Assessment, Technical Assessment
- Each assessment section contains an In Scope Issues list and a Verdict (APPROVE/REJECT/REQUEST CHANGES)

### 9. Finalization

- Extract and persist verdicts from the review markdown
- Append a provenance footer to the review artifact
- Record LLM usage, resume info, ChunkHound tool proof evidence
- Update `meta.json` with `status: "done"`, `completed_at`, final paths
- Stop the TUI dashboard
- Print the review markdown path to stdout

## Data Flow Diagram

```
                    ┌─────────────┐
                    │   GitHub    │
                    │   API /    │
                    │   gh CLI   │
                    └──────┬──────┘
                           │ PR metadata, checkout
                           ▼
┌──────────┐     ┌─────────────────┐     ┌──────────────┐
│cure.toml │────▶│   CURe Core     │────▶│  Sandbox     │
│chunkhound│     │  (cure.py)      │     │  <session>/  │
│-base.json│     └────────┬────────┘     │  repo/       │
└──────────┘              │              │  work/       │
                          │              │  meta.json   │
               ┌──────────┼──────────┐   │  review.md   │
               │          │          │   └──────────────┘
               ▼          ▼          ▼
        ┌──────────┐ ┌─────────┐ ┌──────────┐
        │ChunkHound│ │  LLM    │ │  Review  │
        │ index &  │ │Provider │ │ Intelli- │
        │ search   │ │(Codex/  │ │ gence    │
        │ research │ │ Claude/ │ │(GitHub/  │
        └──────────┘ │ HTTP)   │ │ Jira)    │
                     └─────────┘ └──────────┘
```

## Session Lifecycle States

```
created → running → done
                  → error
```

Multipass sub-states (tracked in `meta.json` → `multipass.status`):

```
planning → stepping → synthesizing → done
                                   → step_failed
                                   → synth_failed
                                   → grounding_failed
```

Each step tracks its own state:

```
queued → running → awaiting_validation → completed
                                       → retrying_grounding → completed / grounding_skipped
                 → failed
       → reused (from a prior run on resume)
```

## Review Intelligence: Jira Integration

CURe has a pluggable **Review Intelligence** framework that injects external context (GitHub, Jira) into the review process. Jira integration is the most involved external source. Here is how it works end-to-end.

### Configuration

Jira is registered as a review intelligence source in `cure.toml`:

```toml
[review_intelligence]
[[review_intelligence.sources]]
name = "jira"
mode = "when-referenced"   # or "auto", "required", "off"
```

The `mode` controls behavior:

| Mode | Behavior |
|------|----------|
| `off` | Jira is completely disabled |
| `auto` | Use Jira when ticket context is readily available and materially clarifies the change |
| `when-referenced` | Use Jira when the PR, commits, or code reference a ticket key (e.g. `PROJ-123`) |
| `required` | Jira context is mandatory; the review will not start without a successful Jira preflight |

### Auth & CLI Prerequisites

Jira integration relies on the `jira` CLI (`ankitpokhrel/jira-cli`). Auth is configured via:

- `~/.config/.jira/.config.yml` (default jira-cli config path)
- `JIRA_CONFIG_FILE` env var to override
- `~/.netrc` with `machine api.atlassian.com` for token-based auth

CURe checks for the `jira` binary on PATH and the config file during `cure doctor` health checks.

### Credential Staging into the Sandbox

Because LLM sandbox environments (Codex/Claude) restrict filesystem access, CURe stages credentials into the session work directory:

1. **`prepare_jira_config_for_codex()`** — Copies the entire Jira config directory (`~/.config/.jira/`) into `<session>/work/jira_config/` and sets `JIRA_CONFIG_FILE` in the subprocess environment.

2. **`prepare_netrc_for_reviewflow()`** — Copies `~/.netrc` into `<session>/work/netrc/.netrc` and sets `NETRC` in the environment (Jira CLI uses netrc for API gateway auth).

3. **`write_rf_jira()`** — Generates a self-contained helper script at `<session>/repo/rf-jira`. This script:
   - Validates that `JIRA_CONFIG_FILE` is set and the config file exists
   - Sets `HOME` to the real user home (for netrc lookup)
   - Wraps all `jira` CLI calls with `--config` pointing to the staged config
   - Implements retry logic with backoff for intermittent 401 errors
   - Acts as a stable interface the LLM agent can call: `rf-jira issue view PROJ-123`

```
Credential flow:
~/.config/.jira/.config.yml  ──copy──▶  work/jira_config/.config.yml
~/.netrc                     ──copy──▶  work/netrc/.netrc
                                        ↓
                             JIRA_CONFIG_FILE + NETRC env vars
                                        ↓
                             repo/rf-jira (helper script)
                                        ↓
                             LLM agent calls: rf-jira issue view PROJ-123
```

### Runtime Capability Detection

During review setup, CURe builds a **capability summary** for each review intelligence source. For Jira, this checks three signals:

- **`config`** — Is the staged Jira config file present?
- **`helper`** — Is the `rf-jira` helper script staged?
- **`jira_cli`** — Is the `jira` binary available on PATH?

All three must be "available" for Jira to be usable. The capability summary is persisted in `meta.json` under `review_intelligence` and reported by `cure doctor --json`.

### Preflight Check

When Jira mode is `required`, CURe runs a preflight before starting the review:

1. Verify `JIRA_CONFIG_FILE` is set in the subprocess environment
2. Verify the `rf-jira` helper script exists on disk
3. Execute `rf-jira me` to confirm auth works end-to-end
4. If any check fails, the review aborts with a diagnostic error

### Prompt Injection

Review intelligence guidance is injected into every prompt template via the `{{REVIEW_INTELLIGENCE_GUIDANCE}}` variable. For Jira, this generates mode-specific instructions:

- **`when-referenced`**: "Use Jira when the change, PR, or commits reference a ticket and that context would clarify the review."
- **`required`**: "Jira context is required for this review; confirm the relevant ticket context before finalizing."
- **`auto`**: "Use Jira when ticket context is readily available and materially clarifies the change."

The LLM agent receives this guidance and can call `rf-jira` to look up ticket details when appropriate.

### Multipass Plan: Jira Key Extraction

During the multipass plan stage, the LLM's plan JSON can include a `jira_keys` (or `ticket_keys`) array:

```json
{
  "abort": false,
  "jira_keys": ["PROJ-123", "PROJ-456"],
  "steps": [...]
}
```

CURe validates and normalizes these keys. They flow into the step prompts so each step worker knows which tickets are relevant to the review.

### Doctor Checks

`cure doctor --json` reports Jira readiness under the `review_intelligence` section:

```json
{
  "review_intelligence": {
    "sources": [{
      "name": "jira",
      "mode": "when-referenced",
      "family": "jira",
      "status": "available",
      "signals": {
        "config": { "status": "available", "path": "..." },
        "helper": { "status": "available" },
        "jira_cli": { "status": "available" }
      }
    }]
  }
}
```

## Key Design Decisions

1. **Sandbox isolation** — The source repo is never mutated. Reviews happen in cloned sandboxes under `<sandbox_root>`. This makes runs safe, repeatable, and cleanable.

2. **Seed + base cache** — A bare seed clone is maintained per repo. Base-branch ChunkHound indexes are cached and shared across reviews, avoiding redundant full-repo indexing.

3. **Multipass decomposition** — Large PRs are reviewed in parallel steps, each focusing on a specific area. This improves coverage and allows grounding validation per step. The final synthesis merges findings.

4. **Grounding validation** — In strict mode, every `file:line` citation in a step artifact is verified against the actual repo. This catches LLM hallucinations about code locations.

5. **Provider abstraction** — The LLM execution layer supports multiple providers (Codex CLI, Claude CLI, OpenAI/OpenRouter HTTP). The review pipeline is provider-agnostic; only the execution adapter changes.

6. **ChunkHound helper** — Instead of native MCP wiring, CLI-provider reviews use a generated helper script (`cure-chunkhound`) that manages the ChunkHound daemon lifecycle, preflight checks, and tool call timeouts. This gives CURe control over the search/research contract.

7. **Resumability** — Sessions persist their full state in `meta.json`. Failed multipass runs can be resumed from the exact phase (plan, steps, synth) where they stopped, reusing completed step artifacts.

8. **Config cascade** — Every setting follows CLI flag → env var → `cure.toml` → built-in default. This makes CURe work both for interactive human use and headless agent runs.

## Filesystem Layout

```
~/.config/cure/
  cure.toml                    # Main config
  chunkhound-base.json         # ChunkHound embedding/provider config

~/.local/state/cure/sandboxes/
  <session_id>/                # One per review run
    meta.json
    review.md
    repo/                      # Cloned PR repo
    work/
      logs/
      chunkhound/
      review_plan.json
      review.step-*.md

~/.cache/cure/
  seeds/<host>/<owner>/<repo>/ # Bare seed clones
  bases/<host>/<owner>/<repo>/<base_ref>/
    .chunkhound.db             # Cached base-branch index
```
