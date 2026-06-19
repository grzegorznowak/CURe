> [!WARNING]
> **Read this first: [ChunkHound](https://github.com/chunkhound/chunkhound) and disk requirements.** CURe cannot run reviews until ChunkHound is fully installed, configured, and confirmed working end-to-end. When possible, use the latest ChunkHound `main` branch so CURe gets current indexing and research behavior.
>
> CURe creates ChunkHound-backed indexes and ad-hoc DuckDB databases inside review sandboxes. On large repositories, these artifacts can consume vast disk space; CURe is best suited to small and medium projects where the ChunkHound index is measured in a few GB, not hundreds.
>
> Use a fast, spacious SSD, and run `cure clean` regularly to remove old sandboxes and cached state you no longer need.

# CURe

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

It is for two audiences:
- human operators who want a repeatable way to hand PR review work to agents without letting them mutate the source checkout
- agentic sessions that need a clear, reusable bootstrap contract for fresh or partially configured environments

If you are an agent, or you want to install CURe as a reusable skill, start with [SKILL.md](SKILL.md).

## Quick Links

- [Why CURe](#why-cure)
- [Install And First Review](#install-and-first-review)
- [Example Flows](#example-flows)
- [Agent And Setup Notes](#agent-and-setup-notes)
- [Core Commands](#core-commands)
- [Secondary Standalone Install](#secondary-standalone-install)
- [Advanced / Pre-Provisioned Environments](#advanced--pre-provisioned-environments)
- [Minimal Config](#minimal-config)
- [Jira CLI](#jira-cli)
- [Tests](#tests)

## Why CURe

Use CURe when you want to:
- review a GitHub PR from a disposable sandbox instead of the working repo
- standardize how humans and agents start, observe, resume, and clean review runs
- give an agent a single documented path from fresh install or existing local setup to "review in progress"

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

`cure setup` reuses an existing `chunkhound` already on `PATH` by default. Pass `--chunkhound-source release` or `--chunkhound-source git-main` when you want CURe to install or replace that binary explicitly, or `--skip-install` when `chunkhound` is already available and should be left untouched.

Ephemeral agent run path:

```bash
uvx --from cureview cure setup
uvx --from cureview cure doctor --pr-url <PR_URL> --json
uvx --from cureview cure pr <PR_URL> --if-reviewed new
```

Keep the README focused on the landing page and first success. For the full agent bootstrap contract, including local setup inspection rules and operator handoff wording, use [SKILL.md](SKILL.md).

## Example Flows

### Example 1: clean public package install to first review

This is the primary public path and matches the package prove-out used for the first successful public release:

```bash
uv tool install cureview
cure setup
cure doctor --pr-url https://github.com/chunkhound/chunkhound/pull/220 --json
cure pr https://github.com/chunkhound/chunkhound/pull/220 --if-reviewed new
```

The `v0.1.2` public release prove-out verified the package-first bootstrap flow in a clean temp-home install. `cure setup` is the single public bootstrap command.

### Example 2: ephemeral agent bootstrap from the one-sentence kickoff

Use the canonical agent run surface when the review happens inside a disposable sandbox or agent session:

```bash
tmp_root="$(mktemp -d)"
export XDG_CONFIG_HOME="$tmp_root/config"
export XDG_STATE_HOME="$tmp_root/state"
export XDG_CACHE_HOME="$tmp_root/cache"

uvx --from cureview cure setup
uvx --from cureview cure doctor --pr-url <PR_URL> --json
uvx --from cureview cure pr <PR_URL> --if-reviewed new
```

If CURe is already partially configured, inspect the active local setup before creating a fresh one:

```text
- the active `cure.toml`
- the JSON file resolved from `[chunkhound].base_config_path`
- repo-root `chunkhound.json` and `.chunkhound.json` as ask-first ChunkHound setup hints
```

On a TTY, `cure setup` acts as the setup wizard. The wizard can keep the current configured base config, adopt a repo-root `chunkhound.json` / `.chunkhound.json`, accept an absolute custom base-config path, or generate the default CURe-managed base config. It also detects installed `codex` and `claude` executables, persists the sticky choice through `default_preset`, and can install ChunkHound before returning to the original command when `chunkhound` is still missing on `PATH`.

### Example 3: what a finished review produces

A normal review run leaves behind resumable session state plus a review artifact with stable headings:

```text
<session_dir>/
  meta.json
  review.md
```

```markdown
**Summary**: ...
## Business / Product Assessment
### In Scope Issues
## Technical Assessment
### In Scope Issues
```

Review output uses two independent lenses:
- Business / Product Assessment uses product/ticket scope.
- Technical Assessment uses implementation scope.

## Agent And Setup Notes

Ensure `git`, `curl`, and `ca-certificates` are present before bootstrap. Install `uv` if it is missing.

Use `cure doctor --pr-url <PR_URL> --json` as the source of truth for inspect-first setup. Its `repo_local_chunkhound` payload plus the `repo-local-chunkhound` check and `executor-network` advisory check surface the same setup hints in machine-readable and text forms.

If repo-local ChunkHound config exists, summarize what it contains and ask the operator whether it should be reused. Do not silently adopt it in this public contract.

Commands that actually require bootstrap now fail or repair earlier instead of surfacing late config or agent-selection errors. On a TTY, `cure pr`, `cure resume`, `cure followup`, `cure cache prime`, and `cure interactive` can enter the same setup wizard before side effects. On non-TTY runs, those commands fail fast and point back to `cure setup` plus `cure doctor`.

On an interactive `cure pr` cold start with no existing CURe-managed base cache for the selected baseline, CURe may also ask whether you already have a matching ChunkHound workspace/config for that exact repo. If validation passes, CURe hot-starts the managed base cache from that workspace before running the normal top-up index. Non-TTY runs skip this prompt and build the baseline cache normally.

That indexed ChunkHound-backed path is the default and recommended public review workflow.

```bash
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
cure resume <session_id|PR_URL>
```

Once the first run is active, continue the same indexed session with `cure resume <session_id|PR_URL>`.

`cure pr --no-index` remains available only as an advanced opt-out for custom prompt flows that intentionally skip the built-in ChunkHound-backed prompts. It is not the normal or recommended path.

Review output toggles:
- Verbose final finding cards are now the default for `cure pr`. They include severity/impact, likelihood, assumptions, downgrade factors, code trail, and reproduction detail. Use `--wtf off` when you need the older concise finding format.
- Chain-of-Draft hypothesis ledger triage is enabled by default for multipass `cure pr` runs. It asks step reviewers to record compact candidate issue threads before promoting only grounded survivors into findings. Use `--cod-ledger off` to disable it; it remains intentionally outside single-pass prompt families.

Built-in CLI-provider review runs use a staged CURe-managed ChunkHound helper rather than native agent MCP wiring. CURe exports that helper through `CURE_CHUNKHOUND_HELPER`; the built-in prompt/proof contract is per-template successful helper execution whose captured output contains the final structured output for that call, even if preflight/progress lines appear before it. A successful `"$CURE_CHUNKHOUND_HELPER" search ...` call proves the `search` requirement. A successful `"$CURE_CHUNKHOUND_HELPER" research ...` call proves `code_research` only for templates where that requirement is required or conditional; it remains optional guidance for initial plan and resume-plan. For `search`, that output may be a JSON object with a `results` list or a markdown/text block. Per-template contracts decide whether helper `research` is required, guidance-only, or conditional. Initial plan and resume-plan prompts require helper `search` but do not require helper `research`/`code_research`. Other built-in prompts may still require or conditionally request helper `research`. Plain `chunkhound search`, `chunkhound research`, and `chunkhound mcp` shell usage are not the built-in CLI-provider contract. Historical sessions may still report legacy `mcp_tool_call` evidence.

Helper-backed Codex runs also export `PYTHONSAFEPATH=1` so a ChunkHound daemon started while reviewing the `chunkhound` repo does not import the checked-out repo package by accident. If helper preflight times out, inspect the persisted helper path plus daemon lock/log/runtime metadata in session status or `meta.json` before retrying.

Codex and Claude executor paths need internet / network access to obtain code-under-review context. In constrained agent sandboxes, treat that as an operator-visible prerequisite and ask for help instead of pretending CURe can always self-bootstrap from zero state. When `cure doctor` resolves Codex or Claude, look for the `executor-network` advisory check instead of claiming the sandbox already proved that prerequisite.

Claude-first explicit override example:

```bash
cure doctor --llm-preset claude-cli --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new --llm-preset claude-cli
```

If autodetect picks the wrong CLI provider, override it explicitly with `--llm-preset claude-cli` or `--llm-preset codex-cli`.

To persist the choice for future runs, use `cure set-agent claude` or `cure set-agent codex`. `cure setup` also repairs missing bootstrap files plus the saved local-agent choice when it can do so deterministically.

Need the full bootstrap contract for agent sessions or existing local setups? Use [SKILL.md](SKILL.md).

## Core Commands

Recommended indexed review loop:

```bash
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
cure resume <session_id|PR_URL>
```

Initialize or repair non-secret bootstrap files:

```bash
cure setup
```

Start a fresh review:

```bash
cure pr <PR_URL> --if-reviewed new
```

Check status:

```bash
cure status <session_id|PR_URL> --json
```

Watch a run:

```bash
cure watch <session_id|PR_URL>
```

Resume a session:

```bash
cure resume <session_id|PR_URL>
```

Clean up old sessions:

```bash
cure clean closed --json
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

Use the standalone GitHub Release assets only when the package path is unavailable or inconvenient. The current secondary targets are:
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

The installer downloads the matching release asset into `~/.local/bin/cure`. After that, the bootstrap/readiness flow is unchanged:

```bash
cure setup
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
```

If your platform is not covered by the standalone assets, fall back to the package path instead of inventing a separate bootstrap recipe.

## Advanced / Pre-Provisioned Environments

Persistent human install should use the public package:

```bash
uv tool install cureview
cure setup
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
```

Teams that already manage a local CURe checkout can keep using that as a secondary local-development flow:
- keep CURe in a stable local path
- refresh it with `git -C <CURE_SOURCE> pull --ff-only`
- install it with `uv tool install /path/to/cure`
- keep any project-specific wrappers or config beside that checkout

If local CURe config already exists, inspect it before overwriting it:
- check the active `cure.toml`
- inspect the JSON resolved from `[chunkhound].base_config_path`
- treat repo-root `chunkhound.json` or `.chunkhound.json` as setup hints to discuss with the operator, not inputs to silently adopt

Prefer `cure doctor --pr-url <PR_URL> --json` as the readiness summary after that inspection. It now reports `repo_local_chunkhound` plus the `repo-local-chunkhound` and `executor-network` checks so the operator does not need to infer those details from raw files alone.

When no explicit preset or config default is selected, CURe only autodetects between `claude-cli` and `codex-cli` from the high-confidence session markers it already understands. If autodetect picks the wrong CLI provider, override it explicitly with `--llm-preset claude-cli` or `--llm-preset codex-cli`.

Those details are secondary. The primary operator contract stays `use <CURE_REPO_URL> to review <PR_URL>`.

Example: use https://github.com/grzegorznowak/CURe to review https://github.com/chunkhound/chunkhound/pull/220.
That sentence is the kickoff contract, not a promise that every sandbox can finish setup unattended.
The operator should not need to provide a local checkout path.
It should not do a manual review outside CURe.

For the full bootstrap contract around fresh installs, existing local setup, and operator handoff, use [SKILL.md](SKILL.md).

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

[llm]
# One execution effort now applies to plan, step, and synth.
reasoning_effort = "high"
```

On interactive `cure pr` runs, CURe can open a `/dev/tty` picker for the resolved CLI provider when `model` or execution `reasoning_effort` was not explicitly configured. Press Enter keeps the displayed defaults. Built-in defaults are now explicit: `claude-cli` uses `claude-sonnet-4-6` with effort `high`, and `codex-cli` defaults to effort `high`.

When strict multipass grounding fails, CURe keeps the invalid artifact on disk and writes the validation details to `work/grounding_report.json` inside the session. Inspect the persisted state with `cure status <session_id|PR_URL> --json` or `cure watch <session_id|PR_URL>`, then rerun the same session with `cure resume <session_id>` or the narrower `cure resume <session_id> --from steps` / `cure resume <session_id> --from synth`. If you want fail-open behavior for future runs, set `[multipass].grounding_mode = "warn"`.

If an embedding key is already present in the environment, `cure setup` adds the matching embedding block and continues. If `VOYAGE_API_KEY` already exists, `cure setup` writes the Voyage embedding model into the active ChunkHound base config and continues. Otherwise, if `OPENAI_API_KEY` already exists, `cure setup` writes the OpenAI embedding model into the active ChunkHound base config and continues.

If no supported key is present, the agent should stop with the exact local config path, the minimal snippet to add, the required env var name, and the rerun command instead of improvising a manual review.

The structured `review_intelligence` source registry now feeds prompt guidance, session metadata, and `cure doctor --json` capability summaries. Only `mode = "required"` sources are preflighted before review generation; optional sources stay lazy and surface as `available`, `unavailable`, or `unknown` based on the runtime facts CURe already has.

## Jira CLI

Use this only when the workflow actually needs Jira context. Normal public GitHub PR review flows do not require Jira.

For tenant setup, auth, `jira init`, `JIRA_CONFIG_FILE`, common queries, and troubleshooting, use the dedicated [Jira reference](https://github.com/grzegorznowak/CURe/blob/main/JIRA.md).

If Jira context is required in a CURe session, keep auth local, prefer `~/.netrc` for `api.atlassian.com` or a short-lived `JIRA_API_TOKEN`, and point CURe at a non-default Jira CLI config with `JIRA_CONFIG_FILE` when needed.

## Tests

Fast local check:

```bash
./selftest.sh
```
