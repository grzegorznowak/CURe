# CURe

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

It is for two audiences:
- human operators who want a repeatable way to hand PR review work to agents without letting them mutate the source checkout
- agentic sessions that need a clear, reusable bootstrap contract from a pristine environment

If you are an agent, or you want to install CURe as a reusable skill, start with [SKILL.md](SKILL.md). This README is the human/operator overview.

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

Use the target-aware readiness gate before a live review lifecycle command:

```bash
cure doctor --pr-url <PR_URL> --json
```

For public `github.com` PRs, this readiness check is the preflight for `cure pr`, `cure resume`, `cure followup`, and `cure zip`. Jira remains optional for normal PR review lifecycle work and is only required for Jira-driven flows.

## Human + Agent Sync

To make CURe work well with agents, the operator should provide four things:
- the local CURe checkout path
- the project config path
- authenticated external tools where needed, except where target-aware public `github.com` fallback is explicitly sufficient
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
