# CURe

[![PyPI](https://img.shields.io/pypi/v/cureview)](https://pypi.org/project/cureview/)
[![License](https://img.shields.io/github/license/grzegorznowak/CURe)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/cureview)](https://pypi.org/project/cureview/)

Review GitHub pull requests inside isolated sandboxes — your working checkout stays untouched, review state lives on disk, and the workflow is resumable.

> If you are an agent or want to install CURe as a reusable skill, start with [SKILL.md](SKILL.md).

## Quickstart

Paste one sentence into any Claude or Codex session:

```text
install <CURE_REPO_URL> to be able to review <PR_URL>
```

Example:

```text
install https://github.com/grzegorznowak/CURe to be able to review https://github.com/grzegorznowak/CURe/pull/1
```

The agent bootstraps CURe, runs the review inside a sandbox, and leaves a `review.md` on disk.

## Why CURe

Use CURe when you want to:
- review a GitHub PR from a disposable sandbox without touching the working repo
- keep review state on disk with resumable, observable sessions
- hand PR review work to an agent without letting it mutate the source checkout

CURe is not for:
- ad-hoc in-place review where the agent works directly in the project checkout
- environments that cannot install tools or authenticate the required external systems

## Installation

### Package install (recommended)

```bash
uv tool install cureview
cure init
cure install
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
```

`cure install` reuses an existing `chunkhound` already on `PATH`. Pass `--chunkhound-source release` to install or replace it explicitly.

### Ephemeral / agent session

```bash
uvx --from cureview cure init
uvx --from cureview cure install
uvx --from cureview cure doctor --pr-url <PR_URL> --json
uvx --from cureview cure pr <PR_URL> --if-reviewed new
```

For the full agent bootstrap contract, see [SKILL.md](SKILL.md).

## What a Review Produces

A finished review run leaves behind resumable session state and a review artifact with stable headings:

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
- **Business / Product Assessment** — product and ticket scope.
- **Technical Assessment** — implementation scope.

## Core Commands

| Command | What it does |
|---|---|
| `cure init` | Write bootstrap config. On a terminal, runs as an interactive setup wizard. |
| `cure doctor --pr-url <PR_URL> --json` | Check readiness before starting a review. |
| `cure pr <PR_URL> --if-reviewed new` | Start a fresh review. |
| `cure status <session_id\|PR_URL> --json` | Check session status. |
| `cure watch <session_id\|PR_URL>` | Stream output from a running session. |
| `cure resume <session_id\|PR_URL>` | Resume a session. |
| `cure zip <PR_URL>` | Synthesize a final review from session state. |
| `cure clean closed --json` | Clean up sessions for closed PRs. |
| `cure clean <session_id>` | Remove a specific session. |

## Other Install Paths

### Standalone binary

Use the standalone GitHub Release assets when the package path is unavailable. Current targets: Linux x86_64, macOS x86_64, macOS arm64.

Install the latest release:

```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh
```

Pin a specific release:

```bash
curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.6
```

The installer downloads `cure` into `~/.local/bin/cure`. After that, use the same four commands from [Installation](#installation).

### Local checkout

Teams that already manage a local CURe checkout:

```bash
git -C <CURE_SOURCE> pull --ff-only
uv tool install /path/to/cure
cure init
cure install
cure doctor --pr-url <PR_URL> --json
cure pr <PR_URL> --if-reviewed new
```

## Minimal Config

Default config files written by `cure init`:

```text
~/.config/cure/cure.toml
~/.config/cure/chunkhound-base.json
```

To use a non-default layout, set `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and `XDG_CACHE_HOME` before `cure init`, or pass `--config`, `--sandbox-root`, and `--cache-root` directly.

Minimal `cure.toml`:

```toml
[paths]
sandbox_root = "/absolute/path/to/sandboxes"
cache_root = "/absolute/path/to/cache"

[chunkhound]
base_config_path = "/absolute/path/to/chunkhound-base.json"
```

`cure init` auto-configures embeddings if `VOYAGE_API_KEY` or `OPENAI_API_KEY` is present.

## Jira Integration

Use this only when the workflow actually needs Jira context. Normal GitHub PR review flows do not require Jira.

For tenant setup, auth, `jira init`, `JIRA_CONFIG_FILE`, common queries, and troubleshooting, use the dedicated [Jira reference](https://github.com/grzegorznowak/CURe/blob/main/JIRA.md).

If Jira context is required in a CURe session, keep auth local, prefer `~/.netrc` for `api.atlassian.com` or a short-lived `JIRA_API_TOKEN`, and point CURe at a non-default Jira CLI config with `JIRA_CONFIG_FILE` when needed.

## Tests

Runs the fast local integration suite:

```bash
./selftest.sh
```
