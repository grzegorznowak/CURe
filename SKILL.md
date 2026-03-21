---
name: cure
description: Run GitHub pull request reviews in isolated sandboxes with CURe. Use when you need a safe, repeatable PR review workflow with `cure init`, `cure pr`, `cure status`, `cure watch`, follow-up, resume, and zip synthesis.
metadata:
  short-description: Review GitHub PRs in isolated sandboxes with CURe
---

# CURe Skill

Use this file as the standalone agent skill for CURe.

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

## Hard Rule

If the operator asked to use CURe, do not perform a manual review outside CURe. Bootstrap CURe and run `cure`.

## When To Use CURe

Use CURe when:
- you need to review a GitHub PR from a sandbox
- you need a stable start command and observable session state
- you need to bootstrap from a fresh or partially configured environment with explicit readiness checks

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

1. Ensure `git`, `curl`, and `ca-certificates` are present. On fresh Debian-like containers such as `node:latest`, install them if they are missing.

2. Install `uv` if it is missing.

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

Ephemeral agent bootstrap:
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
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.2
```

The standalone path is a secondary fallback for Linux x86_64, macOS x86_64, and macOS arm64 only. After install, use the same `cure init`, `cure install`, and `cure doctor` flow as the package path.

5. Prefer disposable XDG roots or explicit path overrides when the session should not touch the operator's default config tree.

Disposable bootstrap example:

```bash
tmp_root="$(mktemp -d)"
export XDG_CONFIG_HOME="$tmp_root/config"
export XDG_STATE_HOME="$tmp_root/state"
export XDG_CACHE_HOME="$tmp_root/cache"
```

Equivalent explicit override example:

```bash
cure init \
  --config /tmp/cure-public/cure.toml \
  --sandbox-root /tmp/cure-public/sandboxes \
  --cache-root /tmp/cure-public/cache
```

6. Run `cure init` before `cure install` or `cure doctor`.

Human persistent flow:

```bash
cure init
```

Agent ephemeral flow:

```bash
uvx --from cureview cure init
```

`cure init` writes the default local non-secret config files if they are missing:

```text
~/.config/cure/cure.toml
~/.config/cure/chunkhound-base.json
```

When `--config` or `XDG_CONFIG_HOME` changes the config location, `chunkhound-base.json` is written alongside the selected `cure.toml`.

Minimal `cure.toml` written by `cure init`:

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

If the base JSON file is missing, `cure init` creates it with `{}` first, then layers the embedding config below when a supported key already exists in the environment.

That structured `review_intelligence` registry is also the source for capability-aware prompt guidance plus the additive `review_intelligence` block in session metadata and `cure doctor --json`. Only `required` sources are preflighted; optional sources stay lazy and surface as `available`, `unavailable`, or `unknown` from facts CURe already staged.

7. Auto-wire embeddings from the current environment when possible.

If `VOYAGE_API_KEY` exists, `cure init` writes:

```json
{
  "embedding": {
    "provider": "voyage",
    "model": "voyage-code-3"
  }
}
```

If `VOYAGE_API_KEY` is missing but `OPENAI_API_KEY` exists, `cure init` writes:

```json
{
  "embedding": {
    "provider": "openai",
    "model": "text-embedding-3-small"
  }
}
```

If the file already exists and you want to rewrite it, rerun `cure init --force`.

8. Provision ChunkHound:

```bash
cure install
```

`cure install` provisions ChunkHound only.
It reuses an existing `chunkhound` already on `PATH` by default. Pass `--chunkhound-source release` or `--chunkhound-source git-main` only when you want CURe to install or replace that binary explicitly.

9. Confirm readiness:

```bash
cure doctor --pr-url <PR_URL> --json
```

Use that target-aware readiness result as the preflight for the normal PR review lifecycle: `cure pr`, `cure resume`, `cure followup`, and `cure zip`. Jira remains optional for those normal lifecycle commands and is only required for Jira-driven workflows. If Jira context is actually required, follow the generalized secure setup in [JIRA.md](JIRA.md): prefer `~/.netrc` on `api.atlassian.com`, use short-lived `JIRA_API_TOKEN` exports only when needed, and do not store tokens in repo files or chat. For public `github.com` PRs, `gh` authentication is optional when anonymous public fallback is sufficient. `git` is still required.

That indexed ChunkHound-backed path is the default and recommended review workflow:

```bash
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
cure resume <session_id|PR_URL>
```

`cure pr --no-index` remains available only as an advanced opt-out for custom prompt flows that intentionally skip the built-in ChunkHound-backed prompts. It is not the normal or recommended path.

Built-in Codex review runs use a staged CURe-managed ChunkHound helper rather than native agent MCP wiring. CURe exports that helper through `CURE_CHUNKHOUND_HELPER`; the built-in prompt/proof contract is successful `"$CURE_CHUNKHOUND_HELPER" search ...` and `"$CURE_CHUNKHOUND_HELPER" research ...` execution with JSON output, and helper `research` satisfies the `code_research` requirement. Plain `chunkhound search`, `chunkhound research`, and `chunkhound mcp` shell usage are not the built-in Codex contract. Historical sessions may still report legacy `mcp_tool_call` evidence.

Helper-backed Codex runs also export `PYTHONSAFEPATH=1` so a ChunkHound daemon started while reviewing the `chunkhound` repo does not import the checked-out repo package by accident. If helper preflight times out, inspect the persisted helper path plus daemon lock/log/runtime metadata in session status or `meta.json` before retrying.

Codex and Claude executor paths need internet / network access to obtain code-under-review context. If the sandbox blocks that access, ask the operator for help instead of pretending CURe can always bootstrap fully autonomously.

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
- `cure watch ...` lets another human or agent follow the run

Common follow-up actions:

```bash
cure followup <session_id>
cure resume <session_id|PR_URL>
cure zip <PR_URL>
cure clean closed --json
```

## When To Stop And Ask

Bootstrap everything non-secret before you stop:
- run `cure init`
- create `~/.config/cure/cure.toml` only when `cure init` is unavailable or the session explicitly requires a manual path
- create `~/.config/cure/chunkhound-base.json` only when `cure init` is unavailable or the session explicitly requires a manual path
- auto-wire embeddings if `VOYAGE_API_KEY` or `OPENAI_API_KEY` already exists

When readiness still fails because a required secret is missing, inspect the actual active local files you already know about before you stop:
- the active `cure.toml`
- the JSON file resolved from `[chunkhound].base_config_path`
- for Jira-driven workflows, the active Jira CLI config at `~/.config/.jira/.config.yml` or the path from `JIRA_CONFIG_FILE`
- if repo-root `chunkhound.json` or `.chunkhound.json` exists, summarize it as a setup hint and ask the operator whether it should be reused; do not silently adopt it

Before stopping, turn the diagnosis into an exact local remediation recipe:
- if a secret value is missing, do not invent it; tell the operator where to place it locally, prefer a current-shell export for the immediate retry, then a shell profile or existing local secret manager for persistence
- mention only the env vars relevant to the active or auto-selected path, such as `VOYAGE_API_KEY` or `OPENAI_API_KEY`
- for Jira-driven workflows, verify auth with `jira serverinfo` and a minimal `jira issue list ...`; if auth still fails, retry with `env -u JIRA_API_TOKEN ...` to rule out a stale exported token overriding `~/.netrc`
- if non-secret config structure is missing, create it yourself instead of stopping
- never ask the operator to paste a secret into chat
- end with the exact rerun command, usually `cure pr <PR_URL> --if-reviewed new`

Stop instead of guessing only after you have already created the non-secret config structure and then:
- `cure doctor --pr-url <PR_URL> --json` still reports missing prerequisites
- no supported embedding key is present in the environment
- GitHub access or ChunkHound base config are unavailable in a way that `cure doctor --pr-url <PR_URL> --json` does not clear for the target
- the active executor path is Codex or Claude and the environment cannot provide the required internet / network access for code-under-review context
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

4. If the existing JSON became stale, tell the operator to rerun `cure init --force`.

5. End with the rerun command:

```bash
cure pr <PR_URL> --if-reviewed new
```

## Canonical Agent Prompt

```text
Use CURe from <CURE_REPO_URL> to review <PR_URL>.

Required behavior:
- If the operator asked to use CURe, do not perform a manual review outside CURe.
- Prefer the public package contract:
  - `uv tool install cureview` for persistent human setup
  - `uvx --from cureview cure ...` for disposable agent execution
- If CURe config already exists, inspect the active `cure.toml` and the JSON resolved from `[chunkhound].base_config_path` before creating new config files.
- Look for repo-root `chunkhound.json` and `.chunkhound.json` as ask-first setup hints and ask the operator before reusing them.
- Use a temp XDG root or explicit `--config` / `--sandbox-root` / `--cache-root` overrides when the session should not touch the default `~/.config/cure` layout.
- Run `cure init` before `cure install`.
- If `VOYAGE_API_KEY` is present, let `cure init` configure Voyage embeddings automatically.
- Otherwise, if `OPENAI_API_KEY` is present, let `cure init` configure OpenAI embeddings automatically.
- After install or repair, run `cure install`.
- Then run `cure doctor --pr-url <PR_URL> --json` and use it as the readiness gate for `pr`, `resume`, `followup`, and `zip`.
- Read the `repo_local_chunkhound` payload plus the `repo-local-chunkhound` and `executor-network` checks from `cure doctor` before guessing from raw local files.
- If using Codex or Claude execution, treat internet / network access as a prerequisite for obtaining code-under-review context.
- If the environment is ready, start the review with `cure pr <PR_URL> --if-reviewed new`.
- Then report progress with `cure status <session_id|PR_URL> --json` and `cure watch <session_id|PR_URL>`.
- In constrained sandboxes, ask the operator for help instead of promising end-to-end zero-state bootstrap.
- If a required embedding secret is still missing, provide the exact local remediation steps for secret placement and the rerun command, then stop.
```
