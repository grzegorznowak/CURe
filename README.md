# CURe

CURe ("Code Under Review") is a CLI for running pull request reviews inside isolated sandboxes, with ChunkHound-backed code search/research and a configurable review agent on top.

It is for two audiences:
- human operators who want a repeatable way to hand PR review work to agents without letting them mutate the source checkout
- agentic sessions that need a clear, reusable bootstrap contract from a pristine environment

If you are an agent, or you want to install CURe as a reusable skill, start with [SKILL.md](SKILL.md).

## Quickstart

For a human operator, the default kickoff is one sentence:

```text
use <CURE_REPO_URL> to review <PR_URL>
```

Example:

```text
use https://github.com/grzegorznowak/CURe to review https://github.com/chunkhound/chunkhound/pull/220
```

That should be enough to start the CURe system. The operator should not need to provide a local checkout path, a config path, or a handwritten bootstrap recipe in the primary flow.

If the operator asked to use CURe, the agent should bootstrap CURe and run `cure`. It should not do a manual review outside CURe.

## What CURe Is For

Use CURe when you want to:
- review a GitHub PR from a disposable sandbox instead of the working repo
- standardize how humans and agents start, observe, resume, and clean review runs
- give an agent a single documented path from "nothing installed" to "review in progress"

CURe is not for:
- ad-hoc in-place repo review where the agent should work directly in the project checkout
- environments that cannot install tools or authenticate the required external systems

## Agent Bootstrap From That Prompt

When the only instruction is `use <CURE_REPO_URL> to review <PR_URL>`, the agent should:
1. Ensure the local environment has `git`, `curl`, and `ca-certificates`. On fresh Debian-like containers such as `node:latest`, install them if they are missing.
2. Install `uv` if it is missing.
3. Clone CURe to a disposable local path, or refresh an existing local checkout with `git -C <CURE_SOURCE> pull --ff-only`.
4. Install CURe from that local checkout with `uv tool install /path/to/cure`.
5. Create the default local non-secret config files if they are missing:

```text
~/.config/cure/cure.toml
~/.config/cure/chunkhound-base.json
```

6. If `VOYAGE_API_KEY` already exists, write a Voyage embedding block into the active ChunkHound base config and continue.
7. Otherwise, if `OPENAI_API_KEY` already exists, write an OpenAI embedding block into the active ChunkHound base config and continue.
8. Otherwise, stop only after writing the exact local config path, the minimal snippet to add, the required env var name, and the rerun command.
9. Run `cure install`.
10. Run `cure doctor --pr-url <PR_URL> --json`.
11. If ready, start the review with `cure pr <PR_URL> --if-reviewed new`.

For public `github.com` PRs, `cure doctor --pr-url <PR_URL> --json` is the readiness gate for `cure pr`, `cure resume`, `cure followup`, and `cure zip`. Jira remains optional for those flows, and `gh` authentication is optional when anonymous public fallback is sufficient. `git` is still required for PR checkout.

## Advanced / Pre-Provisioned Environments

Teams that already manage a local CURe checkout can keep using that flow:
- keep CURe in a stable local path
- refresh it with `git -C <CURE_SOURCE> pull --ff-only`
- install it with `uv tool install /path/to/cure`
- keep any project-specific wrappers or config beside that checkout

Those details are secondary. The primary operator contract stays `use <CURE_REPO_URL> to review <PR_URL>`.

## Minimal Config

Default config path:

```text
~/.config/cure/cure.toml
```

Minimal config:

```toml
[review_intelligence]
tool_prompt_fragment = """
Preferred review-intelligence tools:
- Use GitHub MCP for PR context when available.
- Otherwise use gh CLI / gh api.
- Use any additional tools or sources that materially improve understanding of the code under review.
"""

[chunkhound]
base_config_path = "~/.config/cure/chunkhound-base.json"
```

Default ChunkHound base config path:

```text
~/.config/cure/chunkhound-base.json
```

If an embedding key is already present in the environment, the agent should add the matching embedding block and continue. If no supported key is present, the agent should stop with an exact remediation recipe instead of improvising a manual review.

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
- humans should only need a short kickoff prompt
- agents bootstrap the review workflow instead of improvising one
- the project checkout stays untouched
- reviews become repeatable instead of prompt-by-prompt improvisation

## Tests

Fast local check:

```bash
./selftest.sh
```
