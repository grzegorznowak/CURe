---
name: cure
description: Run GitHub pull request reviews in isolated sandboxes with CURe. Use when you need a safe, repeatable PR review workflow with `cure pr`, `cure status`, `cure watch`, follow-up, resume, and zip synthesis.
metadata:
  short-description: Review GitHub PRs in isolated sandboxes with CURe
---

# CURe Skill

Use this file as the standalone agent skill for CURe.

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

## When To Use CURe

Use CURe when:
- you need to review a GitHub PR from a sandbox
- you need a stable start command and observable session state
- you need to bootstrap from a pristine environment with explicit readiness checks

## Inputs The Agent Needs

Before starting, gather:
- `PR_URL`
- `<CURE_SOURCE>`: the local path where the CURe project is checked out
- `<PROJECT_PATH>` when the operator expects project-local wrappers or adjacent config
- the project's CURe config file, or the exact missing values needed to create it

## Bootstrap From A Pristine Environment

1. Install `uv` if it is missing.

macOS / Linux:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Official install docs:
```text
https://docs.astral.sh/uv/getting-started/installation/
```

2. Check out CURe to a local path such as:

```bash
git clone <CURE_REPO_URL> /path/to/cure
```

3. Refresh that local checkout before using it for reviews:

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

5. Provision ChunkHound:

```bash
cure install
```

`cure install` provisions ChunkHound only.

6. Confirm readiness:

```bash
cure doctor --pr-url <PR_URL> --json
```

Use that target-aware readiness result as the preflight for the normal PR review lifecycle: `cure pr`, `cure resume`, `cure followup`, and `cure zip`. Jira remains optional for those normal lifecycle commands and is only required for Jira-driven workflows.

7. If the environment is ready, start the review:

```bash
cure pr <PR_URL> --if-reviewed new
```

8. Observe progress:

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

When readiness fails because local runtime config or credentials are incomplete, inspect the actual active local files you already know about before you stop:
- the project's `reviewflow.toml`
- the JSON file resolved from `[chunkhound].base_config_path`

Before stopping, turn the diagnosis into an exact local remediation recipe:
- if a secret value is missing, do not invent it; tell the operator where to place it locally, prefer a current-shell export for the immediate retry, then a shell profile or existing local secret manager for persistence
- for ChunkHound embedding setup, explicitly mention supported env vars when relevant, including `OPENAI_API_KEY` and `VOYAGE_API_KEY`
- if non-secret config structure is missing, name the exact local file path to edit and show the minimal snippet to add, using placeholders instead of real secret values
- never ask the operator to paste a secret into chat
- end with the exact rerun command, usually `cure pr <PR_URL> --if-reviewed new`

Stop instead of guessing only after you have provided the exact local remediation steps for config or secret placement when:
- `cure doctor --pr-url <PR_URL> --json` reports missing prerequisites
- the project config is missing
- the review-intelligence fragment is missing
- GitHub access, provider auth, or ChunkHound base config are unavailable in a way that `cure doctor --pr-url <PR_URL> --json` does not clear for the target
- Jira is unavailable for a Jira-driven workflow
- the operator has not provided the project-specific values the run needs

Ask only for the truly missing fact when you cannot infer it from the active local files. Distinguish:
- missing secret values: provide placement guidance first, then stop for the operator to supply the value locally
- missing non-secret config structure: provide the exact file path and snippet first, then stop for the operator to make the local edit
- missing project/operator facts: report what you inspected locally, then ask for only that fact

## Example: ChunkHound Embedding Not Configured

If `chunkhound index ...` or `cure doctor --pr-url <PR_URL> --json` fails with `Error: No embedding provider configured`, respond in this shape:

1. Identify the active config path you inspected:

```text
I checked /path/to/project/reviewflow.toml and its [chunkhound].base_config_path points to /path/to/project/chunkhound-base.json.
```

2. Show the exact non-secret block to add to the active ChunkHound base config:

```json
{
  "embedding": {
    "provider": "openai",
    "model": "text-embedding-3-small"
  }
}
```

If the file already has top-level keys, merge that `embedding` object into the existing JSON instead of replacing the whole file. If the operator uses Voyage instead of OpenAI, use `"provider": "voyage"` with an appropriate Voyage embedding model such as `"voyage-code-3"`.

3. Recommend env-first secret placement, never secret values in chat:

```bash
export OPENAI_API_KEY=<your-openai-api-key>
```

or

```bash
export VOYAGE_API_KEY=<your-voyage-api-key>
```

For persistence, place the same env var in the operator's shell profile or existing local secret manager. Do not ask them to paste the secret into chat.

4. End with the rerun command:

```bash
cure pr <PR_URL> --if-reviewed new
```

## Canonical Agent Prompt

```text
Use CURe from <CURE_SOURCE> to review the project at <PROJECT_PATH> for <PR_URL>.

Required behavior:
- Before using CURe, refresh `<CURE_SOURCE>` with `git -C <CURE_SOURCE> pull --ff-only` when it is a git checkout.
- If `cure` is already installed and working, use the refreshed checkout.
- If `cure` is installed but not working, diagnose and repair or reinstall it from the refreshed `<CURE_SOURCE>`.
- If `cure` is not installed, install it from <CURE_SOURCE>.
- After install or repair, run `cure install`.
- Then run `cure doctor --pr-url <PR_URL> --json` and use it as the readiness gate for `pr`, `resume`, `followup`, and `zip`.
- Inspect the actual active local config files first, especially `reviewflow.toml` and the resolved `chunkhound-base.json` from `[chunkhound].base_config_path`.
- Ask only for the missing project-specific facts after you have provided the exact local remediation steps for config or secret placement.
- Do not invent config, assume hidden secrets, ask for secrets in chat, or skip readiness checks.
- If the environment is ready, start the review with `cure pr <PR_URL> --if-reviewed new`.
- Then report progress with `cure status <session_id|PR_URL> --json` and `cure watch <session_id|PR_URL>`.
- If the environment is not ready for a live review, first provide the exact local remediation steps for config or secret placement, including the file path to edit, a minimal snippet, the supported env vars to place locally, and the rerun command; then stop if the operator still needs to supply the secret value or make the local change.
```
