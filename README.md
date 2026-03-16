# CURe

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

It is for two audiences:
- human operators who want a repeatable way to hand PR review work to agents without letting them mutate the source checkout
- agentic sessions that need a clear, reusable bootstrap contract from a pristine environment

## What CURe Is For

Use CURe when you want to:
- review a GitHub PR from a disposable sandbox instead of the working repo
- standardize how humans and agents start, observe, resume, and clean review runs
- give an agent a single documented path from “nothing installed” to “review in progress”

CURe is not for:
- ad-hoc in-place repo review where the agent should work directly in the project checkout
- environments that cannot install tools or authenticate the required external systems

## Human Snapshot

CURe is an external tool that sits beside a project.

The operator workflow is:
1. Install `uv` once.
2. Check out CURe to a local path.
3. Install CURe from that path.
4. Make sure the project-specific config and external auth are available.
5. Hand the agent a PR URL and the CURe path.

If you only remember one command, it is:

```bash
cure pr <PR_URL> --if-reviewed new
```

That is the canonical “start a fresh review” path for both humans and agents.

## Agent Skill

Treat this section as a portable remote skill for a fresh agent session.

### When To Use CURe

Use CURe when:
- you need to review a GitHub PR from a sandbox
- you need a stable start command and observable session state
- you need to bootstrap from a pristine environment with explicit readiness checks

### Inputs The Agent Needs

Before starting, gather:
- `PR_URL`
- `<CURE_SOURCE>`: the local path where the CURe project is checked out
- `<PROJECT_PATH>` when the operator expects project-local wrappers or adjacent config
- the project’s CURe config file, or the exact missing values needed to create it

### Bootstrap From A Pristine Environment

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
cure doctor --json
```

6. If the environment is ready, start the review:

```bash
cure pr <PR_URL> --if-reviewed new
```

7. Observe progress:

```bash
cure status <session_id|PR_URL> --json
cure watch <session_id|PR_URL>
```

### What Success Looks Like

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

### When To Stop And Ask

Stop instead of guessing when:
- `cure doctor --json` reports missing prerequisites
- the project config is missing
- the review-intelligence fragment is missing
- `gh`, Jira, provider auth, or ChunkHound base config are unavailable
- the operator has not provided the project-specific values the run needs

### Canonical Agent Prompt

```text
Use CURe from <CURE_SOURCE> to review the project at <PROJECT_PATH> for <PR_URL>.

Required behavior:
- If `cure` is already installed and working, use it.
- If `cure` is installed but not working, diagnose and repair or reinstall it from <CURE_SOURCE>.
- If `cure` is not installed, install it from <CURE_SOURCE>.
- After install or repair, run `cure install`.
- Then run `cure doctor --json` and use it as the readiness gate.
- Ask only for the missing configuration, credentials, or project-specific inputs.
- Do not invent config, assume hidden secrets, or skip readiness checks.
- If the environment is ready, start the review with `cure pr <PR_URL> --if-reviewed new`.
- Then report progress with `cure status <session_id|PR_URL> --json` and `cure watch <session_id|PR_URL>`.
- If the environment is not ready for a live review, stop and report the exact missing prerequisites.
```

## Human + Agent Sync

To make CURe work well with agents, the operator should provide four things:
- the local CURe checkout path
- the project config path
- authenticated external tools where needed
- a clear PR URL to start from

The operator should not need to teach each agent a custom workflow. The goal is that every agent starts from the same CURe contract and the same canonical `cure pr <PR_URL> --if-reviewed new` entrypoint.

Wrappers are optional. Use them only when they simplify handoff; do not hide the core `cure` contract behind project-specific magic.

## Minimal Config

```toml
[review_intelligence]
tool_prompt_fragment = """
Preferred review-intelligence tools:
- Use GitHub MCP for PR context when available.
- Otherwise use gh CLI / gh api.
- Use any additional tools or sources that materially improve understanding of the code under review.
"""

[chunkhound]
base_config_path = "/absolute/path/to/chunkhound-base.json"
```

## Core Commands

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

Resume or follow up:

```bash
cure resume <session_id|PR_URL>
cure followup <session_id>
```

Synthesize a final review:

```bash
cure zip <PR_URL>
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

## What CURe Produces

CURe produces:
- a sandbox session directory
- review markdown artifacts
- optional follow-up and zip artifacts
- machine-readable session state for status/watch tooling

Review output uses two independent lenses:
- Business / Product Assessment uses product/ticket scope.
- Technical Assessment uses implementation scope.

## Practical Premise

The value proposition is simple:
- humans keep control of project setup, config, and credentials
- agents get a stable, safe review workflow
- the project checkout stays untouched
- reviews become repeatable instead of prompt-by-prompt improvisation

## Tests

Fast local check:

```bash
./selftest.sh
```
