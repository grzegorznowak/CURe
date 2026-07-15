---
name: cure
description: Run GitHub pull request reviews in isolated sandboxes with CURe. Use when you need a safe, repeatable PR review workflow with `cure setup`, `cure pr`, `cure status`, `cure watch`, and `resume`.
metadata:
  short-description: Review GitHub PRs in isolated sandboxes with CURe
---

# CURe Skill

Use this file as an assisted checklist for CURe agent sessions under operator control.

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

## Hard Rule

If the operator asked to use CURe, do not perform a manual review outside CURe. Use CURe when the environment is approved and ready; stop and ask before installing tools, writing persistent config, selecting a local agent, handling secrets, or assuming blocked sandbox/network permissions can be bypassed.

## When To Use CURe

Use CURe when:
- you need to review a GitHub PR from a sandbox
- you need a stable start command and observable session state
- you need an operator-approved setup checklist for a fresh or partially configured environment with explicit readiness checks

## Primary Inputs

The default operator kickoff is:

```text
use <CURE_REPO_URL> to review <PR_URL>
```

Treat these as the primary inputs:
- `CURE_REPO_URL`
- `PR_URL`

Optional inputs:
- `<CURE_SOURCE>` if a usable local checkout already exists
- `<PROJECT_PATH>` only when the operator explicitly expects project-local wrappers or adjacent config

Do not require the operator to provide a local checkout path or a config path in the primary flow.

## Bootstrap From A Fresh Or Existing Local Setup

This is an assisted workflow, not authorization to bypass local policy. Before package installs, persistent config writes, binary installs/replacements, local agent selection, or secret/network remediation, verify that the operator approved the action. Prefer disposable XDG roots or explicit paths when approval for the default user config tree is unclear.

1. Ensure `git`, `curl`, and `ca-certificates` are present. On fresh Debian-like containers such as `node:latest`, install them only if the operator has approved OS package installation in that environment; otherwise stop with the missing prerequisite.

2. Install `uv` if it is missing and package installation is operator-approved.

macOS / Linux:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Official install docs:
```text
https://docs.astral.sh/uv/getting-started/installation/
```

3. If CURe is already partially configured, inspect the active local setup before creating fresh config files.

Check:
- the active `cure.toml`
- the JSON file resolved from `[chunkhound].base_config_path`
- repo-root `chunkhound.json` and `.chunkhound.json` as ask-first ChunkHound setup hints

If repo-local ChunkHound config exists, summarize what it contains and ask the operator whether it should be reused. Do not silently adopt it.
Use `cure doctor --pr-url <PR_URL> --json` as the source of truth for this when possible: its `repo_local_chunkhound` payload and `repo-local-chunkhound` check surface the same ask-first hint.

4. Choose the package-first bootstrap path that matches the session.

Persistent human install:
```bash
uv tool install cureview
```

Disposable assisted execution:
```bash
uvx --from cureview cure --help
```

Advanced local-development fallback only:
```bash
uv tool install /path/to/cure
```

For local iteration from a checkout:
```bash
uv tool install --editable /path/to/cure
```

Secondary standalone fallback only when the package path is unavailable:
```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh
```

Version-pinned standalone fallback:
```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.8
```

The standalone path is a secondary fallback for Linux x86_64, macOS x86_64, and macOS arm64 only. Run it only when the operator approves the persistent install into `~/.local/bin`. After install, use the same `cure setup` and `cure doctor` flow as the package path.

5. Prefer disposable XDG roots or explicit path overrides when the session should not touch the operator's default config tree or when approval for persistent config writes is unclear.

Disposable bootstrap example:

```bash
tmp_root="$(mktemp -d)"
export XDG_CONFIG_HOME="$tmp_root/config"
export XDG_STATE_HOME="$tmp_root/state"
export XDG_CACHE_HOME="$tmp_root/cache"
```

Equivalent explicit override example:

```bash
cure setup \
  --config /tmp/cure-public/cure.toml \
  --sandbox-root /tmp/cure-public/sandboxes \
  --cache-root /tmp/cure-public/cache
```

6. Run `cure setup` before `cure doctor`.

Human persistent flow:

```bash
cure setup
```

Disposable assisted flow:

```bash
uvx --from cureview cure setup
```

Only run `cure setup` against the default user config tree when the operator has approved that persistent target. Otherwise set disposable XDG roots or pass explicit `--config`, `--sandbox-root`, and `--cache-root` paths first.

`cure setup` writes the default local non-secret config files if they are missing:

```text
~/.config/cure/cure.toml
~/.config/cure/chunkhound-base.json
```

When `--config` or `XDG_CONFIG_HOME` changes the config location, `chunkhound-base.json` is written alongside the selected `cure.toml`.

Minimal `cure.toml` written by `cure setup`:

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
```

If the base JSON file is missing, `cure setup` creates it with `{}` first, then layers the non-secret embedding provider/model config below when a supported key already exists in the environment. It uses the key's presence to select metadata; it must not print, write, or request the secret value in chat.

That structured `review_intelligence` registry is also the source for capability-aware prompt guidance plus the additive `review_intelligence` block in session metadata and `cure doctor --json`. Only `required` sources are preflighted; optional sources stay lazy and surface as `available`, `unavailable`, or `unknown` from facts CURe already staged.

7. Configure non-secret embedding metadata from the current environment when possible.

If `VOYAGE_API_KEY` exists, `cure setup` writes:

```json
{
  "embedding": {
    "provider": "voyage",
    "model": "voyage-code-3"
  }
}
```

If `VOYAGE_API_KEY` is missing but `OPENAI_API_KEY` exists, `cure setup` writes:

```json
{
  "embedding": {
    "provider": "openai",
    "model": "text-embedding-3-small"
  }
}
```

If the file already exists and you want to rewrite it, rerun `cure setup --force`.

8. Assist ChunkHound provisioning and local agent choice:

```bash
cure setup
```

`cure setup` can provision ChunkHound, repair missing non-secret bootstrap files, and persist the Codex local-agent choice only when the selected config target is operator-approved and the choice is explicit. It reuses an existing `chunkhound` already on `PATH` by default. Pass `--chunkhound-source release` or `--chunkhound-source git-main` only when the operator has approved CURe installing or replacing that binary explicitly. Use `--agent codex` on `cure setup` only when Codex is the approved non-interactive choice, and use `cure set-agent codex` to refresh the sticky selection later.

9. Confirm readiness:

```bash
cure doctor --pr-url <PR_URL> --json
```

Codex explicit override example:

```bash
cure doctor --llm-preset codex-cli --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new --llm-preset codex-cli
```

Use that target-aware readiness result as the preflight for the normal PR review lifecycle: `cure pr` and `cure resume`. Jira remains optional for those normal lifecycle commands and is only required for Jira-driven workflows. If Jira context is actually required, follow the generalized secure setup in [JIRA.md](JIRA.md): prefer `~/.netrc` on `api.atlassian.com`, use short-lived `JIRA_API_TOKEN` exports only when needed, and do not store tokens in repo files or chat. For public `github.com` PRs, `gh` authentication is optional when anonymous public fallback is sufficient. `git` is still required.

That indexed ChunkHound-backed path is the default and recommended review workflow:

```bash
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
cure resume <session_id|PR_URL>
```

`cure pr --no-index` remains available only as an advanced opt-out for custom prompt flows that intentionally skip the built-in ChunkHound-backed prompts. It is not the normal or recommended path.

`cure pr` now uses one execution `reasoning_effort` for the whole run. Plan, step, and synth inherit that same resolved effort. On a TTY, PR runs can prompt for model and/or effort when those fields were not explicitly configured. Press Enter keeps the displayed provider defaults. Built-in Codex defaults are explicit: `codex-cli` defaults to effort `high`.

Built-in CLI-provider review runs use a staged CURe-managed ChunkHound helper rather than native agent MCP wiring. CURe exports that helper through `CURE_CHUNKHOUND_HELPER`; the built-in prompt/proof contract is per-template successful helper execution whose captured output contains the final structured output for that call, even if preflight/progress lines appear before it. A successful `"$CURE_CHUNKHOUND_HELPER" search ...` call proves the `search` requirement. A successful `"$CURE_CHUNKHOUND_HELPER" research ...` call proves `code_research` only for templates where that requirement is required or conditional; it remains optional guidance for initial plan and resume-plan. For `search`, that output may be a JSON object with a `results` list or a markdown/text block. Per-template contracts decide whether helper `research` is required, guidance-only, or conditional. Initial plan and resume-plan prompts require helper `search` but do not require helper `research`/`code_research`. Other built-in prompts may still require or conditionally request helper `research`. Plain `chunkhound search`, `chunkhound research`, and `chunkhound mcp` shell usage are not the built-in CLI-provider contract. Historical sessions may still report legacy `mcp_tool_call` evidence.

Helper-backed Codex runs also export `PYTHONSAFEPATH=1` so a ChunkHound daemon started while reviewing the `chunkhound` repo does not import the checked-out repo package by accident. If helper preflight times out, inspect the persisted helper path plus daemon lock/log/runtime metadata in session status or `meta.json` before retrying.

Codex executor paths need internet / network access to obtain code-under-review context. If the sandbox blocks that access, ask the operator for help instead of claiming CURe can guarantee end-to-end setup or runtime access. If autodetect needs to be overridden, rerun the readiness and review commands with `--llm-preset codex-cli`.

10. If the environment is ready, start the review:

```bash
cure pr <PR_URL> --if-reviewed new
```

11. Observe progress:

```bash
cure status <session_id|PR_URL> --json
cure watch <session_id|PR_URL>
```

## What Success Looks Like

Success means:
- `cure pr <PR_URL> --if-reviewed new` creates a sandbox session
- the command prints the created session path to stdout
- `cure status ... --json` returns machine-readable run state
- `cure watch ...` lets a human or assisting agent observe the run; humans remain responsible for interpreting readiness and failures

Common next actions:

```bash
cure resume <session_id|PR_URL>
cure clean closed --json
```

## When To Stop And Ask

Complete only operator-approved non-secret setup before you stop:
- run `cure setup` in an approved or disposable config target
- create `~/.config/cure/cure.toml` only when `cure setup` is unavailable and the operator approved that persistent path; otherwise use explicit/disposable paths or provide manual instructions
- create `~/.config/cure/chunkhound-base.json` only when `cure setup` is unavailable and the operator approved that persistent path; otherwise use explicit/disposable paths or provide manual instructions
- auto-wire non-secret embedding metadata if `VOYAGE_API_KEY` or `OPENAI_API_KEY` already exists without exposing the secret value

When readiness still fails because a required secret is missing, inspect the actual active local files you already know about before you stop:
- the active `cure.toml`
- the JSON file resolved from `[chunkhound].base_config_path`
- for Jira-driven workflows, the active Jira CLI config at `~/.config/.jira/.config.yml` or the path from `JIRA_CONFIG_FILE`
- if repo-root `chunkhound.json` or `.chunkhound.json` exists, summarize it as a setup hint and ask the operator whether it should be reused; do not silently adopt it
- if autodetect needs to be overridden, rerun the readiness and review commands with `--llm-preset codex-cli`.

Before stopping, turn the diagnosis into an exact local remediation recipe:
- if a secret value is missing, do not invent it; tell the operator where to place it locally, prefer a current-shell export for the immediate retry, then a shell profile or existing local secret manager for persistence
- mention only the env vars relevant to the active or auto-selected path, such as `VOYAGE_API_KEY` or `OPENAI_API_KEY`
- for Jira-driven workflows, verify auth with `jira serverinfo` and a minimal `jira issue list ...`; if auth still fails, retry with `env -u JIRA_API_TOKEN ...` to rule out a stale exported token overriding `~/.netrc`
- if non-secret config structure is missing, create it only in an approved or disposable config target; otherwise provide exact manual steps instead of guessing
- never ask the operator to paste a secret into chat, infer secret values, or persist secrets outside operator-approved local mechanisms
- end with the exact rerun command, usually `cure pr <PR_URL> --if-reviewed new`

Stop instead of guessing after you have created any approved non-secret config structure, or provided exact manual steps when config writes were not approved, and then:
- `cure doctor --pr-url <PR_URL> --json` still reports missing prerequisites
- no supported embedding key is present in the environment
- GitHub access or ChunkHound base config are unavailable in a way that `cure doctor --pr-url <PR_URL> --json` does not clear for the target
- the active Codex executor path cannot provide the required internet / network access for code-under-review context
- Jira is unavailable for a Jira-driven workflow
- the operator has not provided a truly missing project-specific fact that cannot be inferred from the local files

## Example: Missing Embedding Secret

If `chunkhound index ...` or `cure doctor --pr-url <PR_URL> --json` fails because neither `VOYAGE_API_KEY` nor `OPENAI_API_KEY` is present, respond in this shape:

1. Identify the active config path you inspected:

```text
I checked ~/.config/cure/cure.toml and its [chunkhound].base_config_path points to ~/.config/cure/chunkhound-base.json.
```

2. Show the exact non-secret block already written or ready to write to the active ChunkHound base config:

```json
{
  "embedding": {
    "provider": "voyage",
    "model": "voyage-code-3"
  }
}
```

3. Recommend env-first secret placement, never secret values in chat:

```bash
export VOYAGE_API_KEY=<your-voyage-api-key>
```

If the operator prefers OpenAI instead, switch the snippet to the OpenAI embedding model above and use:

```bash
export OPENAI_API_KEY=<your-openai-api-key>
```

4. If the existing JSON became stale, tell the operator to rerun `cure setup --force`.

5. End with the rerun command:

```bash
cure pr <PR_URL> --if-reviewed new
```

## Canonical Agent Prompt

```text
Use CURe from <CURE_REPO_URL> to review <PR_URL>.

Required behavior:
- If the operator asked to use CURe, do not perform a manual review outside CURe.
- Treat this as an assisted workflow, not authorization to bypass sandbox, network, filesystem, or security policy.
- Stop and ask before installing packages or binaries, writing persistent config outside disposable roots, choosing or persisting a local agent, handling secrets, or continuing when network/sandbox access is blocked.
- Prefer the public package contract when the operator has approved the install/execution mode:
  - `uv tool install cureview` for persistent human setup
  - `uvx --from cureview cure ...` for disposable or operator-approved agent execution
- If CURe config already exists, inspect the active `cure.toml` and the JSON resolved from `[chunkhound].base_config_path` before creating new config files.
- Look for repo-root `chunkhound.json` and `.chunkhound.json` as ask-first setup hints and ask the operator before reusing them.
- Use a temp XDG root or explicit `--config` / `--sandbox-root` / `--cache-root` overrides when the session should not touch the default `~/.config/cure` layout.
- Use `cure setup` as the primary bootstrap and repair entry point.
- On a TTY, expect `cure setup` to act as an interactive setup wizard that can keep the current configured base config, adopt a repo-root `chunkhound.json` / `.chunkhound.json`, accept an absolute custom base-config path, or generate the default CURe-managed base config.
- If `VOYAGE_API_KEY` is present, let `cure setup` configure Voyage embeddings automatically.
- Otherwise, if `OPENAI_API_KEY` is present, let `cure setup` configure OpenAI embeddings automatically.
- If `chunkhound` is still missing on `PATH`, let `cure setup` or the setup wizard install it only when the operator approved binary installation/replacement; otherwise stop and report the exact command to run.
- Commands that require bootstrap readiness (`pr`, `resume`, `followup`, `cache prime`, and `interactive`) now fail or repair earlier instead of surfacing late config or agent-selection errors. On non-TTY runs, they should fail fast and point back to `cure setup` plus `cure doctor`.
- Then run `cure doctor --pr-url <PR_URL> --json` and use it as the readiness gate for `pr` and `resume`.
- If autodetect needs to be overridden, rerun `cure doctor` and `cure pr` with `--llm-preset codex-cli`.
- Read the `repo_local_chunkhound` payload plus the `repo-local-chunkhound` and `executor-network` checks from `cure doctor` before guessing from raw local files.
- If using Codex execution, treat internet / network access as a prerequisite for obtaining code-under-review context.
- If the environment is ready, start the review with `cure pr <PR_URL> --if-reviewed new`.
- Then report progress with `cure status <session_id|PR_URL> --json` and `cure watch <session_id|PR_URL>`.
- In constrained sandboxes, ask the operator for help instead of promising reliable unattended setup or runtime access.
- If a required embedding secret is still missing, provide the exact local remediation steps for secret placement and the rerun command, then stop.
```
