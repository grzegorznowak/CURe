> [!WARNING]
> **Read this first: [ChunkHound](https://github.com/chunkhound/chunkhound) and disk requirements.** CURe cannot run reviews until ChunkHound is fully installed, configured, and confirmed working end-to-end. When possible, use the latest ChunkHound `main` branch so CURe gets current indexing and research behavior.
>
> CURe creates ChunkHound-backed indexes and ad-hoc DuckDB databases inside review sandboxes. On large repositories, these artifacts can consume vast disk space; CURe is best suited to small and medium projects where the ChunkHound index is measured in a few GB, not hundreds.
>
> Use a fast, spacious SSD, and run `cure clean` regularly to remove old sandboxes and cached state you no longer need.

# CURe

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

It is for human operators who want a repeatable way to run or delegate PR review work without letting the source checkout be mutated. LLM agents can assist by following documented commands, but installation, persistent configuration, secrets, network access, local agent selection, and sandbox permissions remain operator-controlled.

If you are using CURe from an agent session, treat [SKILL.md](SKILL.md) as an assisted checklist: run only the steps your environment and operator allow, and stop when setup or permissions are ambiguous.

## Quick Links

- [Why CURe](#why-cure)
- [Install And First Review](#install-and-first-review)
- [Example Flows](#example-flows)
- [Agent And Setup Notes](#agent-and-setup-notes)
- [Core Commands](#core-commands)
- [Secondary Standalone Install](#secondary-standalone-install)
- [Minimal Config](#minimal-config)
- [Changing The Review Model](#changing-the-review-model)
- [Jira CLI](#jira-cli)
- [Tests](#tests)

## Why CURe

Use CURe when you want to:
- review a GitHub PR from a disposable sandbox instead of the working repo
- standardize how operators start, observe, resume, and clean review runs, including agent-assisted runs
- document an assisted path from an operator-approved install or disposable setup to "review in progress" without promising unattended bootstrap

CURe is different from an ad-hoc manual agent review because the project checkout stays untouched, the review state stays on disk, and the workflow is resumable instead of prompt-by-prompt improvisation.

CURe is not for:
- ad-hoc in-place repo review where the agent should work directly in the project checkout
- environments that cannot install tools or authenticate the required external systems

## Install And First Review

Persistent install:

```bash
uv tool install cureview
cure setup
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
```

`cure setup` reuses an existing `chunkhound` already on `PATH` by default. Pass `--chunkhound-source release` or `--chunkhound-source git-main` only when the operator has approved CURe installing or replacing that binary explicitly, or `--skip-install` when `chunkhound` is already available and should be left untouched.

Disposable assisted run path:

```bash
uvx --from cureview cure setup
uvx --from cureview cure doctor --pr-url <PR_URL> --json
uvx --from cureview cure pr <PR_URL> --if-reviewed new
```

This disposable path assumes package execution, network access, config writes under the selected XDG roots, and any ChunkHound install are permitted by the operator and sandbox. If one of those prerequisites is blocked or ambiguous, stop and ask the operator instead of improvising.

## Example Flows

### Clean install to explained review

Full lifecycle — persistent install, configure, review a PR, then explain the review's findings:

```bash
uv tool install cureview
cure setup
cure doctor --pr-url https://github.com/chunkhound/chunkhound/pull/220 --json
cure pr https://github.com/chunkhound/chunkhound/pull/220 --if-reviewed new
cure explain https://github.com/chunkhound/chunkhound/pull/220
```

`cure explain <PR_URL>` loads the most recent completed review for that PR and produces a natural-language explanation of its findings — what the reviewer judged, what evidence it used, and what alternatives it considered. Use `--explain-prompt 'Why did you flag X?'` to narrow the focus, or `--open-in-codex` to continue in an interactive Codex session with full review context preloaded.

During a review, use `cure status <session_id|PR_URL> --json` to inspect progress and `cure resume <session_id|PR_URL>` after an interruption. Use `cure clean <session_id>` when its sandbox and cached state are no longer needed. `cure commands --json` provides the machine-readable command catalog.

For disposable or agent-sandbox runs, replace `uv tool install cureview` + `cure setup` with `uvx --from cureview cure setup` and keep the rest unchanged.

## Agent And Setup Notes

Ensure `git`, `curl`, and `ca-certificates` are present before bootstrap. Install `uv` only in an environment where package installation is operator-approved; otherwise stop with the missing prerequisite and the exact command the operator can run.

Use `cure doctor --pr-url <PR_URL> --json` as the source of truth for inspect-first setup. Its `repo_local_chunkhound` payload plus the `repo-local-chunkhound` check and `executor-network` advisory check surface the same setup hints in machine-readable and text forms.

If a repo-local `chunkhound.json` or `.chunkhound.json` exists, summarize what it contains and ask the operator whether it should be reused. Do not silently adopt it in this public contract.

Commands that actually require bootstrap now fail or repair approved non-secret defaults earlier instead of surfacing late config or agent-selection errors. On a TTY, `cure pr`, `cure resume`, `cure cache prime`, and `cure interactive` can enter the same setup wizard before review side effects. On non-TTY runs, those commands fail fast and point back to `cure setup` plus `cure doctor` so a human operator or approved automation can complete setup.

On an interactive `cure pr` cold start with no existing CURe-managed base cache for the selected baseline, CURe may also ask whether you already have a matching ChunkHound workspace/config for that exact repo. If validation passes, CURe hot-starts the managed base cache from that workspace before running the normal top-up index. Non-TTY runs skip this prompt and build the baseline cache normally.

`cure pr --no-index` remains available only as an advanced opt-out for custom prompt flows that intentionally skip the built-in ChunkHound-backed prompts. It is not the normal or recommended path.

Review output toggles:
- Verbose final finding cards are now the default for `cure pr`. They include severity/impact, likelihood, assumptions, downgrade factors, code trail, and reproduction detail. Use `--wtf off` when you need the older concise finding format.
- Chain-of-Draft hypothesis ledger triage is enabled by default for multipass `cure pr` runs. It asks step reviewers to record compact candidate issue threads before promoting only grounded survivors into findings. Use `--cod-ledger off` to disable it; it remains intentionally outside single-pass prompt families.

CURe uses a staged ChunkHound helper (exported as `$CURE_CHUNKHOUND_HELPER`) instead of native MCP wiring for built-in Codex review runs. It exports `PYTHONSAFEPATH=1` so a daemon started while reviewing the `chunkhound` repo does not import the checked-out code. For fresh indexed Codex reviews, CURe retains a private keeper from final-index readiness through teardown so helper calls reuse the daemon; routes that skip indexing or review generation retain their existing behavior. Codex executor paths need network access for review context — look for the `executor-network` check in `cure doctor` output.

If helper preflight times out, inspect the persisted helper path plus daemon lock/log/runtime metadata in session status or `meta.json` before retrying.

Codex explicit override example:

```bash
cure doctor --llm-preset codex-cli --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new --llm-preset codex-cli
```

To persist the choice for future runs, use `cure setup --agent codex` after the operator has approved Codex as the local CLI provider. `cure setup` can repair missing non-secret bootstrap files and the saved local-agent choice only when the selected config target is approved and the choice is unambiguous.

Need the full operator-controlled setup checklist for agent sessions or existing local setups? Use [SKILL.md](SKILL.md).

## Core Commands

Initialize or repair non-secret bootstrap files:

```bash
cure setup
```

Verify prerequisites and PR-specific readiness:

```bash
cure doctor --pr-url <PR_URL> --json
```

Start a fresh review:

```bash
cure pr <PR_URL> --if-reviewed new
```

Selected-PR discussion orientation is enabled by default for the built-in `auto`, `normal`, and `big` prompt profiles. Use `--no-pr-context` to opt out for a run; `--pr-context` remains explicit enable. Custom prompts, prompt files, and `--prompt-profile default` bypass this.

Check status / resume / explain:

```bash
cure status <session_id|PR_URL> --json
cure resume <session_id|PR_URL>
cure explain <PR_URL> [--explain-prompt 'Why?']
```

Clean up:

```bash
cure clean <session_id>
```

Show the machine-readable command catalog:

```bash
cure commands --json
```

## Secondary Standalone Install

The public package remains the default and recommended path:

```bash
uv tool install cureview
```

Use the standalone GitHub Release assets only when the package path is unavailable or inconvenient, and only when the operator has approved running the installer in the current environment. The current secondary targets are:
- Linux x86_64 with glibc 2.31 or newer
- macOS x86_64
- macOS arm64

Install the latest standalone release:

```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh
```

Pin a specific standalone release:

```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.8
```

The installer downloads the matching release asset into `~/.local/bin/cure`. Agent sessions should not run this installer just because package installation failed; they should stop unless the operator approves this persistent install path. After that, follow the standard setup flow.

If your platform is not covered by the standalone assets, fall back to the package path instead of inventing a separate bootstrap recipe.



## Minimal Config

Default config path:

```text
~/.config/cure/cure.toml
```

By default `cure setup` also writes:

```text
~/.config/cure/chunkhound-base.json
```

If you need a disposable or non-default layout, set `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and `XDG_CACHE_HOME` before `cure setup`, or pass `--config`, `--sandbox-root`, and `--cache-root` directly to `cure setup`.

Minimal config written by `cure setup`:

```toml
[paths]
sandbox_root = "/absolute/path/to/sandboxes"
cache_root = "/absolute/path/to/cache"

[review_intelligence]
[[review_intelligence.sources]]
name = "github"
mode = "auto"

[[review_intelligence.sources]]
name = "jira"
mode = "when-referenced"

[chunkhound]
base_config_path = "/absolute/path/to/chunkhound-base.json"

[multipass]
# strict = fail closed on invalid grounding
# warn   = record findings and continue
# off    = skip grounding validation
grounding_mode = "strict"
step_workers = 4

[code_debt]
# Always-on dedicated, isolated code-debt stage/subagent settings.
model_preset = "codex-cli"
model = "gpt-5.6-terra"
max_token_budget = 4000 # validated range: 1..100000
timeout = 300 # seconds; validated range: 1..3600
grounding_mode = "strict" # required; debt findings never relax grounding
# Optional Tier 1 subset; Tier 2 assessment remains prompt-driven.
metrics = ["debt_ratio", "severity_counts", "cyclomatic_complexity", "duplication_density", "comment_todo_density", "test_gap", "dependency_debt"]
hotspot_threshold = 0.0
report_output = "file"
```

Code-debt analysis runs for every review using isolated Codex CLI executions and reports only strictly grounded findings against recognized source/configuration file types (prose-only files such as `README.md` are excluded). Multipass reviews run metric clusters concurrently using the configured multipass worker bound and feed `code-debt.md` into synthesis. Single-stage reviews run a separate subagent and append its report after the main review, so the main model context is not polluted. Plan-aborted, failed-step, and resumed multipass reviews run or reuse the persisted debt artifact. `CURE_CODE_DEBT_PRESET`, `CURE_CODE_DEBT_MODEL`, `CURE_CODE_DEBT_MAX_TOKEN_BUDGET`, `CURE_CODE_DEBT_TIMEOUT`, and `CURE_CODE_DEBT_REPORT_OUTPUT` override the corresponding fields. Debt grounding is intentionally fixed to `strict`.

Debt workers use the same proven Codex runtime policy as ordinary multipass step workers, including the review session's writable scratch/add-directories and approval/sandbox semantics. Each worker remains isolated in the pre-staged per-session checkout and a dedicated process registry. Safety is enforced by the dedicated prompt: workers must inspect statically, must not execute repository-controlled tests/builds/hooks, and must not modify the repository; writable paths are for CURe session artifacts and scratch. CURe additionally starts debt executions with `--skip-git-repo-check`, avoiding the adapter's trust-directory whole-command retry, and passes `rollout_budget.limit_tokens` on every bounded attempt so generation and retry allocations cannot exceed the configured budget. This alignment intentionally replaces the former process-level `read-only`/`never` policy, which prevented Terra workers from performing tool-based analysis in live reviews.

On interactive `cure pr` runs, CURe can open a `/dev/tty` picker for the resolved CLI provider when `model` or execution `reasoning_effort` was not explicitly configured. Press Enter keeps the displayed defaults. Built-in Codex defaults are explicit: `codex-cli` defaults to effort `high`.

When strict multipass grounding fails, CURe keeps the invalid artifact on disk and writes the validation details to `work/grounding_report.json` inside the session. Inspect the persisted state with `cure status <session_id|PR_URL> --json`, then rerun the same session with `cure resume <session_id>` or the narrower `cure resume <session_id> --from steps` / `cure resume <session_id> --from synth`. If you want fail-open behavior for future runs, set `[multipass].grounding_mode = "warn"`.

If an embedding key is already present in the environment, `cure setup` adds the matching non-secret embedding provider/model block and continues. If `VOYAGE_API_KEY` already exists, `cure setup` writes the Voyage embedding model into the active ChunkHound base config and continues. Otherwise, if `OPENAI_API_KEY` already exists, `cure setup` writes the OpenAI embedding model into the active ChunkHound base config and continues. CURe does not write the secret value into that config.

If no supported key is present, an assisting agent should stop with the exact local config path, the minimal snippet to add, the required env var name, and the rerun command instead of improvising a manual review. Agents must not ask the operator to paste secret values into chat, infer secret values, or persist secrets outside operator-approved local mechanisms.

The structured `review_intelligence` source registry now feeds prompt guidance, session metadata, and `cure doctor --json` capability summaries. Only `mode = "required"` sources are preflighted before review generation; optional sources stay lazy and surface as `available`, `unavailable`, or `unknown` based on the runtime facts CURe already has.

## Changing The Review Model

CURe only supports the Codex CLI LLM backend; the `openai-responses` and `openrouter-responses` built-in presets have been removed (to avoid the maintenance burden on the developer). Persistent model settings live in `cure.toml` (normally `~/.config/cure/cure.toml`). Define a named preset and select it as the default:

```toml
[llm]
default_preset = "review_codex"

[llm_presets.review_codex]
preset = "codex-cli"
model = "gpt-5.4"
reasoning_effort = "high"
```

Named presets use `[llm_presets.<name>]`, not `[llm.presets.<name>]`. The example above configures the supported Codex CLI path. `cure setup` may persist `default_preset = "codex-cli"` after an approved Codex choice, but it does not choose a model or create a complete named preset.

For one review, override the selected preset, model, and effort on the command line:

```bash
cure pr <PR_URL> --llm-preset codex-cli --llm-model gpt-5.4 --llm-effort high
```

CLI model and effort overrides take precedence over the selected preset. CURe uses the resolved main model for the review stages and selected-PR orientation; the current `cure pr` workflow does not apply separate coordinator, reviewer, synthesis, or utility model settings.

## Jira CLI

Use this only when the workflow actually needs Jira context. Normal public GitHub PR review flows do not require Jira.

For tenant setup, auth, `jira init`, `JIRA_CONFIG_FILE`, common queries, and troubleshooting, use the dedicated [Jira reference](https://github.com/grzegorznowak/CURe/blob/main/JIRA.md).

If Jira context is required in a CURe session, keep auth local, prefer `~/.netrc` for `api.atlassian.com` or a short-lived `JIRA_API_TOKEN`, and point CURe at a non-default Jira CLI config with `JIRA_CONFIG_FILE` when needed.

## Tests

Fast local check:

```bash
./selftest.sh
```
