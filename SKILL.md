---
name: cure
description: Run GitHub pull request reviews in isolated sandboxes with CURe. Use when you need a safe, repeatable PR review workflow with `cure pr`, `cure status`, `cure watch`, follow-up, resume, and zip synthesis.
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
- you need to bootstrap from a pristine environment with explicit readiness checks

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

## Bootstrap From A Pristine Environment

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

3. Materialize a local CURe checkout.

If no usable local checkout exists:
```bash
git clone <CURE_REPO_URL> /path/to/cure
```

If a local checkout already exists:
```bash
git -C /path/to/cure pull --ff-only
```

4. Install CURe from that local checkout:

```bash
uv tool install /path/to/cure
```

For local iteration from the checkout:

```bash
uv tool install --editable /path/to/cure
```

5. Create the default local non-secret config files if they are missing:

```text
~/.config/reviewflow/reviewflow.toml
~/.config/reviewflow/chunkhound-base.json
```

Minimal `~/.config/reviewflow/reviewflow.toml`:

```toml
[review_intelligence]
tool_prompt_fragment = """
Preferred review-intelligence tools:
- Use GitHub MCP for PR context when available.
- Otherwise use gh CLI / gh api.
- Use any additional tools or sources that materially improve understanding of the code under review.
"""

[chunkhound]
base_config_path = "~/.config/reviewflow/chunkhound-base.json"
```

If `~/.config/reviewflow/chunkhound-base.json` is missing, create it with `{}` first, then layer the embedding config below.

6. Auto-wire embeddings from the current environment when possible.

If `VOYAGE_API_KEY` exists, write:

```json
{
  "embedding": {
    "provider": "voyage",
    "model": "voyage-code-3"
  }
}
```

If `VOYAGE_API_KEY` is missing but `OPENAI_API_KEY` exists, write:

```json
{
  "embedding": {
    "provider": "openai",
    "model": "text-embedding-3-small"
  }
}
```

If the file already has top-level keys, merge the `embedding` object into the existing JSON instead of replacing the whole file.

7. Provision ChunkHound:

```bash
cure install
```

`cure install` provisions ChunkHound only.

8. Confirm readiness:

```bash
cure doctor --pr-url <PR_URL> --json
```

Use that target-aware readiness result as the preflight for the normal PR review lifecycle: `cure pr`, `cure resume`, `cure followup`, and `cure zip`. Jira remains optional for those normal lifecycle commands and is only required for Jira-driven workflows. For public `github.com` PRs, `gh` authentication is optional when anonymous public fallback is sufficient. `git` is still required.

9. If the environment is ready, start the review:

```bash
cure pr <PR_URL> --if-reviewed new
```

10. Observe progress:

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
- create `~/.config/reviewflow/reviewflow.toml` if it is missing
- create `~/.config/reviewflow/chunkhound-base.json` if it is missing
- auto-wire embeddings if `VOYAGE_API_KEY` or `OPENAI_API_KEY` already exists

When readiness still fails because a required secret is missing, inspect the actual active local files you already know about before you stop:
- the active `reviewflow.toml`
- the JSON file resolved from `[chunkhound].base_config_path`

Before stopping, turn the diagnosis into an exact local remediation recipe:
- if a secret value is missing, do not invent it; tell the operator where to place it locally, prefer a current-shell export for the immediate retry, then a shell profile or existing local secret manager for persistence
- mention only the env vars relevant to the active or auto-selected path, such as `VOYAGE_API_KEY` or `OPENAI_API_KEY`
- if non-secret config structure is missing, create it yourself instead of stopping
- never ask the operator to paste a secret into chat
- end with the exact rerun command, usually `cure pr <PR_URL> --if-reviewed new`

Stop instead of guessing only after you have already created the non-secret config structure and then:
- `cure doctor --pr-url <PR_URL> --json` still reports missing prerequisites
- no supported embedding key is present in the environment
- GitHub access or ChunkHound base config are unavailable in a way that `cure doctor --pr-url <PR_URL> --json` does not clear for the target
- Jira is unavailable for a Jira-driven workflow
- the operator has not provided a truly missing project-specific fact that cannot be inferred from the local files

## Example: Missing Embedding Secret

If `chunkhound index ...` or `cure doctor --pr-url <PR_URL> --json` fails because neither `VOYAGE_API_KEY` nor `OPENAI_API_KEY` is present, respond in this shape:

1. Identify the active config path you inspected:

```text
I checked ~/.config/reviewflow/reviewflow.toml and its [chunkhound].base_config_path points to ~/.config/reviewflow/chunkhound-base.json.
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

4. End with the rerun command:

```bash
cure pr <PR_URL> --if-reviewed new
```

## Canonical Agent Prompt

```text
Use CURe from <CURE_REPO_URL> to review <PR_URL>.

Required behavior:
- If the operator asked to use CURe, do not perform a manual review outside CURe.
- Materialize a local CURe checkout from `<CURE_REPO_URL>` if one is not already available, or refresh the existing checkout with `git -C <CURE_SOURCE> pull --ff-only`.
- If `cure` is already installed and working, use it.
- If `cure` is installed but not working, diagnose and repair or reinstall it from the local CURe checkout.
- If `cure` is not installed, install it from the local CURe checkout.
- Create the default non-secret config files under `~/.config/reviewflow/` when they are missing.
- If `VOYAGE_API_KEY` is present, configure Voyage embeddings automatically.
- Otherwise, if `OPENAI_API_KEY` is present, configure OpenAI embeddings automatically.
- After install or repair, run `cure install`.
- Then run `cure doctor --pr-url <PR_URL> --json` and use it as the readiness gate for `pr`, `resume`, `followup`, and `zip`.
- If the environment is ready, start the review with `cure pr <PR_URL> --if-reviewed new`.
- Then report progress with `cure status <session_id|PR_URL> --json` and `cure watch <session_id|PR_URL>`.
- If a required embedding secret is still missing, provide the exact local remediation steps for secret placement and the rerun command, then stop.
```
