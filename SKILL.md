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

3. Install CURe from that local checkout:

```bash
uv tool install /path/to/cure
```

For local iteration from the checkout:

```bash
uv tool install --editable /path/to/cure
```

4. Provision ChunkHound:

```bash
cure install
```

`cure install` provisions ChunkHound only.

5. Confirm readiness:

```bash
cure doctor --pr-url <PR_URL> --json
```

Use that target-aware readiness result as the preflight for the normal PR review lifecycle: `cure pr`, `cure resume`, `cure followup`, and `cure zip`. Jira remains optional for those normal lifecycle commands and is only required for Jira-driven workflows.

6. If the environment is ready, start the review:

```bash
cure pr <PR_URL> --if-reviewed new
```

7. Observe progress:

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

Stop instead of guessing when:
- `cure doctor --pr-url <PR_URL> --json` reports missing prerequisites
- the project config is missing
- the review-intelligence fragment is missing
- GitHub access, provider auth, or ChunkHound base config are unavailable in a way that `cure doctor --pr-url <PR_URL> --json` does not clear for the target
- Jira is unavailable for a Jira-driven workflow
- the operator has not provided the project-specific values the run needs

## Canonical Agent Prompt

```text
Use CURe from <CURE_SOURCE> to review the project at <PROJECT_PATH> for <PR_URL>.

Required behavior:
- If `cure` is already installed and working, use it.
- If `cure` is installed but not working, diagnose and repair or reinstall it from <CURE_SOURCE>.
- If `cure` is not installed, install it from <CURE_SOURCE>.
- After install or repair, run `cure install`.
- Then run `cure doctor --pr-url <PR_URL> --json` and use it as the readiness gate for `pr`, `resume`, `followup`, and `zip`.
- Ask only for the missing configuration, credentials, or project-specific inputs.
- Do not invent config, assume hidden secrets, or skip readiness checks.
- If the environment is ready, start the review with `cure pr <PR_URL> --if-reviewed new`.
- Then report progress with `cure status <session_id|PR_URL> --json` and `cure watch <session_id|PR_URL>`.
- If the environment is not ready for a live review, stop and report the exact missing prerequisites.
```
