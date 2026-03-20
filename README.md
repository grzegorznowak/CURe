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
3. For disposable agent bootstrap, prefer a temp XDG root instead of editing `~/.config/cure` by hand:

```bash
tmp_root="$(mktemp -d)"
export XDG_CONFIG_HOME="$tmp_root/config"
export XDG_STATE_HOME="$tmp_root/state"
export XDG_CACHE_HOME="$tmp_root/cache"
```

4. Bootstrap CURe from the public package instead of cloning the repo:

```bash
uvx --from cureview cure init
uvx --from cureview cure install
uvx --from cureview cure doctor --pr-url <PR_URL> --json
uvx --from cureview cure pr <PR_URL> --if-reviewed new
```

5. `cure init` writes the non-secret local config files if they are missing:

```text
<resolved config dir>/cure.toml
<resolved config dir>/chunkhound-base.json
```

6. If `VOYAGE_API_KEY` already exists, `cure init` writes the Voyage embedding model into the active ChunkHound base config and continues.
7. Otherwise, if `OPENAI_API_KEY` already exists, `cure init` writes the OpenAI embedding model into the active ChunkHound base config and continues.
8. Otherwise, stop only after writing the exact local config path, the minimal snippet to add, the required env var name, and the rerun command.

For public `github.com` PRs, `cure doctor --pr-url <PR_URL> --json` is the readiness gate for `cure pr`, `cure resume`, `cure followup`, and `cure zip`. Jira remains optional for those flows, and `gh` authentication is optional when anonymous public fallback is sufficient. `git` is still required for PR checkout.

## Secondary Standalone Install

The public package remains the default and recommended path:

```bash
uv tool install cureview
```

Use the standalone GitHub Release assets only when the package path is unavailable or inconvenient. The current secondary targets are:
- Linux x86_64
- macOS x86_64
- macOS arm64

Install the latest standalone release:

```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh
```

Pin a specific standalone release:

```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.2
```

The installer downloads the matching release asset into `~/.local/bin/cure`. After that, the bootstrap/readiness flow is unchanged:

```bash
cure init
cure install
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
```

If your platform is not covered by the standalone assets, fall back to the package path instead of inventing a separate bootstrap recipe.

## Jira CLI

Use this only when the workflow actually needs Jira context. Normal public GitHub PR review flows do not require Jira.

This repo uses the `jira` CLI (`ankitpokhrel/jira-cli`) to query and update Jira issues. With scoped Atlassian API tokens, point the CLI at the Atlassian API gateway instead of the site URL directly.

### Jira Site Details

Set your tenant values first:

```bash
JIRA_SITE_URL="https://your-domain.atlassian.net"
JIRA_CLOUD_ID="<your-jira-cloud-id>"
ATLASSIAN_EMAIL="you@example.com"
JIRA_PROJECT_KEY="<your-project-key>"
```

Retrieve the `cloudId` without authentication:

```bash
curl -fsSL "${JIRA_SITE_URL%/}/_edge/tenant_info"
```

If you create an API token with scopes, Jira calls must go via:

```text
https://api.atlassian.com/ex/jira/<JIRA_CLOUD_ID>
```

### Install

The CLI binary should be available as `jira`.

Verify:

```bash
jira version
```

### Auth

Create an API token with scopes at:

```text
https://id.atlassian.com/manage-profile/security/api-tokens
```

Use either `~/.netrc` (recommended) or a short-lived `JIRA_API_TOKEN` env var. Never commit tokens to repo files, shell history snippets, or config checked into source control.

#### Option A: `~/.netrc`

This avoids leaving a stale `JIRA_API_TOKEN` exported in your shell.

Because the CLI server below uses `api.atlassian.com`, the `machine` entry must match that host:

```netrc
machine api.atlassian.com
  login <ATLASSIAN_EMAIL>
  password <JIRA_API_TOKEN>
```

Lock down permissions:

```bash
chmod 600 ~/.netrc
```

If `JIRA_API_TOKEN` is also exported, it takes precedence over `~/.netrc`. If you are using `~/.netrc`, do:

```bash
unset JIRA_API_TOKEN
```

#### Option B: `JIRA_API_TOKEN`

Prefer setting it for a single command or terminal session, not in dotfiles:

```bash
read -s -p "JIRA_API_TOKEN: " JIRA_API_TOKEN; echo
export JIRA_API_TOKEN
```

#### Token Scopes

These scopes are known to work for the workflows below.

Read:
- `read:board-scope.admin:jira-software`
- `read:dashboard:jira`
- `read:dashboard.property:jira`
- `read:board-scope:jira-software`
- `read:sprint:jira-software`
- `read:jql:jira`
- `read:jira-work`
- `read:project-category:jira`
- `read:project-role:jira`
- `read:project-type:jira`
- `read:project-version:jira`
- `read:project:jira`
- `read:project.avatar:jira`
- `read:project.component:jira`
- `read:project.email:jira`
- `read:project.feature:jira`
- `read:project.property:jira`
- `read:jira-user`
- `read:issue-details:jira`

Write:
- `write:jira-work`

### Configure `jira-cli`

This generates a local config file at `~/.config/.jira/.config.yml`.

```bash
jira init \
  --installation cloud \
  --server "https://api.atlassian.com/ex/jira/${JIRA_CLOUD_ID}" \
  --login "${ATLASSIAN_EMAIL}" \
  --auth-type basic
```

CURe looks for Jira CLI config at `~/.config/.jira/.config.yml` by default. If you keep Jira CLI config elsewhere, export `JIRA_CONFIG_FILE=/absolute/path/to/.config.yml` before Jira-driven CURe workflows so the sandboxed helper can pick it up.

Sanity checks:

```bash
jira serverinfo
jira issue list -p "${JIRA_PROJECT_KEY}" --plain --columns key,summary --paginate 1
```

`jira me` prints the configured login, but it is not a strong auth check on its own.

### Common Queries

#### Active Sprint Issues Assigned To A User

This uses JQL (`sprint in openSprints()`) so it still works when `jira sprint list --current` is unavailable.

Do not add `ORDER BY` inside `-q`; `jira issue list` appends its own ordering.

```bash
ASSIGNEE_EMAIL="user@example.com"

jira issue list -p "${JIRA_PROJECT_KEY}" \
  -q "assignee = \"${ASSIGNEE_EMAIL}\" AND sprint in openSprints()" \
  --order-by rank --reverse \
  --plain --columns key,summary,status,priority
```

#### My Work

```bash
jira issue list -p "${JIRA_PROJECT_KEY}" \
  -q 'assignee = currentUser() AND statusCategory != Done' \
  --order-by updated \
  --plain --columns key,summary,status,priority
```

### Security Notes

- Never store Jira tokens in repo files or commit history.
- Prefer `~/.netrc` with `chmod 600` or a short-lived session export.
- Scoped tokens may expire; rotate them before they do.

### Troubleshooting

#### `401 Unauthorized`

Common causes:
- `JIRA_API_TOKEN` is exported but stale or invalid, which overrides `~/.netrc`.
- `~/.netrc` has the wrong `machine` host for the configured `--server`.

Quick checks:

```bash
env -u JIRA_API_TOKEN jira serverinfo
env -u JIRA_API_TOKEN jira issue view "${JIRA_PROJECT_KEY}-123" --plain
```

#### `404 Not Found` Or “Issue Does Not Exist Or You Do Not Have Permission”

Jira often returns `404` when you are not authorized to view an issue. Resolve auth first, then confirm you have project and issue permissions.

## Advanced / Pre-Provisioned Environments

Persistent human install should use the public package:

```bash
uv tool install cureview
cure init
cure install
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
```

Teams that already manage a local CURe checkout can keep using that as a secondary local-development flow:
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

By default `cure init` also writes:

```text
~/.config/cure/chunkhound-base.json
```

If you need a disposable or non-default layout, set `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and `XDG_CACHE_HOME` before `cure init`, or pass `--config`, `--sandbox-root`, and `--cache-root` directly to `cure init`.

Minimal config written by `cure init`:

```toml
[paths]
sandbox_root = "/absolute/path/to/sandboxes"
cache_root = "/absolute/path/to/cache"

[review_intelligence]
tool_prompt_fragment = """
Preferred review-intelligence tools:
- Use GitHub MCP for PR context when available.
- Otherwise use gh CLI / gh api.
- Use any additional tools or sources that materially improve understanding of the code under review.
"""

[chunkhound]
base_config_path = "/absolute/path/to/chunkhound-base.json"

[multipass]
# strict = fail closed on invalid grounding
# warn   = record findings and continue
# off    = skip grounding validation
grounding_mode = "strict"
```

If an embedding key is already present in the environment, `cure init` adds the matching embedding block and continues. If no supported key is present, the agent should stop with an exact remediation recipe instead of improvising a manual review.

## Core Commands

Initialize non-secret bootstrap files:

```bash
cure init
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
