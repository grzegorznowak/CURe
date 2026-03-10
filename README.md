# Reviewflow (ChunkHound + Codex) — PR Review Sandboxes

Goal: create an isolated checkout of a PR, reuse a cached ChunkHound base index, top up indexing for the PR, then run an agentic Codex review (`codex exec`) — without touching `/workspaces/academy+/projects/*`. Reviews use a **sandbox-scoped ChunkHound MCP server** (one per sandbox).

## Prereqs
- `gh` authenticated (`gh auth login -h github.com`)
- `jira` configured (`jira init`) if using the default prompt profiles (`auto/normal/big`)
- Review config exists: `/workspaces/.chunkhound.review.json`
- ChunkHound embedding key available via `CHUNKHOUND_EMBEDDING__API_KEY` (reviewflow will infer it from `/workspaces/.chunkhound.json` if present)

## Commands

Prime base cache (per repo + base branch):
```bash
python3 /workspaces/reviewflow/reviewflow.py cache prime OWNER/REPO --base develop
```

Create sandbox + index + review:
```bash
python3 /workspaces/reviewflow/reviewflow.py pr https://github.com/OWNER/REPO/pull/123
```

If the PR was already reviewed in this workspace, control how `reviewflow pr` behaves:
```bash
python3 /workspaces/reviewflow/reviewflow.py pr https://github.com/OWNER/REPO/pull/123 --if-reviewed prompt|new|list|latest
```

Run a follow-up review on an existing session (writes a new markdown under `<session>/followups/`):
```bash
python3 /workspaces/reviewflow/reviewflow.py followup <session_id>
```

Pick a past completed review and reopen its saved Codex conversation:
```bash
python3 /workspaces/reviewflow/reviewflow.py interactive
```
```bash
python3 /workspaces/reviewflow/reviewflow.py interactive https://github.com/OWNER/REPO/pull/123
```

Synthesize a final “arbiter” review from the latest generated reviews for the PR’s current HEAD SHA:
```bash
python3 /workspaces/reviewflow/reviewflow.py zip https://github.com/OWNER/REPO/pull/123
```
- Writes `<host_session>/zips/zip-<timestamp>.md` under the newest relevant completed session.
- Prints the output path to stdout on success (and prints the full markdown to stderr if the TUI is enabled).
- Fails fast if no completed review artifacts match the PR’s current HEAD SHA (run `pr`/`followup` first).

Skip updating the sandbox to the latest PR head (uses current checkout):
```bash
python3 /workspaces/reviewflow/reviewflow.py followup <session_id> --no-update
```

Resume an aborted multipass review (continues from first missing step):
```bash
python3 /workspaces/reviewflow/reviewflow.py resume <session_id>
# Or pass a PR URL:
# - If a resumable multipass session exists, it will resume that session.
# - Otherwise it will run a follow-up review against the latest completed session.
python3 /workspaces/reviewflow/reviewflow.py resume https://github.com/OWNER/REPO/pull/123
```

Tune model/effort for parallel reviews:
```bash
python3 /workspaces/reviewflow/reviewflow.py pr https://github.com/OWNER/REPO/pull/123 \
  --codex-model gpt-5.3-codex-spark \
  --codex-effort low
```

List sandboxes:
```bash
python3 /workspaces/reviewflow/reviewflow.py list
```

Delete one sandbox:
```bash
python3 /workspaces/reviewflow/reviewflow.py clean <session_id>
```

## Notes
- Sandboxes are created under `/workspaces/academy+/.tmp/review-sandboxes/` and kept until manually cleaned.
- Base caches are stored under `/workspaces/.reviewflow-cache/`.
- ChunkHound is exposed to the review agent via a sandbox-scoped MCP server (configured per run).
- `reviewflow pr` prints progress to **stderr** (phase markers + streamed tool output by default) and prints the sandbox session path to **stdout** on success.
- Use `reviewflow interactive` to pick a past completed review and reopen its saved Codex conversation.
- `reviewflow interactive` prints the latest saved review artifact path for the selected session before resuming.
- Interactive runs start a split-pane **TUI dashboard** on stderr by default (when stderr is a TTY and `TERM != dumb`).
  - Disable with: `--ui off`
  - Force-enable (TTY only): `--ui on`
- Use `--verbosity quiet|normal|debug` to control how much the dashboard shows (default: `normal`).
  - While the TUI is running you can change verbosity live:
    - `v` cycles (`quiet → normal → debug`)
    - `1/2/3` set `quiet/normal/debug`
    - `h`/`?` toggles help
    - `Ctrl+L` forces redraw
- Use `--quiet` to suppress progress output entirely.
- Use `--no-stream` to hide tool output tail panes (logs still go to disk).
- `meta.json` is written early and updated throughout the run so you can watch progress from another terminal.
- Full logs are written under `<session>/work/logs/` (reviewflow/chunkhound/codex) and their paths are recorded in `meta.json`.
- Generated review artifacts normalize sandbox-local file refs to portable `path:line` text instead of embedding absolute `/workspaces/...` Markdown file links.
- The latest resume hint is persisted under `meta.json` in `codex.resume` (`session_id`, `cwd`, `command`).

## Prompt profiles (default: `auto`)
If you don’t pass `--prompt` or `--prompt-file`, reviewflow selects a prompt template by profile:
- `auto` (default): chooses `normal` vs `big` based on local git diff stats
- `normal`: `/workspaces/reviewflow/prompts/mrereview_gh_local.md`
- `big`: multipass by default (plan -> steps -> synth), using:
  - `/workspaces/reviewflow/prompts/mrereview_gh_local_big_plan.md`
  - `/workspaces/reviewflow/prompts/mrereview_gh_local_big_step.md`
  - `/workspaces/reviewflow/prompts/mrereview_gh_local_big_synth.md`
  - (single-pass fallback template remains available at `/workspaces/reviewflow/prompts/mrereview_gh_local_big.md`)
- `default`: `/workspaces/reviewflow/prompts/default.md` (legacy, no GH/Jira gate)

Auto thresholds (balanced defaults):
- Big if `changed_files >= 30` OR `(additions + deletions) >= 1500`
- Override with: `--big-if-files N` and `--big-if-lines N`

Extra contributor context placeholder (for custom prompts):
- `--agent-desc "..."` or `--agent-desc-file path.txt` populates `$AGENT_DESC`

`--no-index` behavior:
- `--no-index` is only supported with `--prompt/--prompt-file` or `--no-review`.
- Built-in prompt profiles (`auto/normal/big/default`) require ChunkHound MCP and will fail fast if `--no-index` is set.

## ABORT behavior (mrereview prompts)
The `mrereview_gh_local*` prompts begin with a mandatory business-context gate:
- Prompts perform the gate **in-session** by running `gh` + `jira` themselves (no prefetch).
- If any required `gh`/`jira` read fails OR if no Jira key is found, the prompt must ABORT with `Decision: REJECT`.
- URL fetching is enrichment, not a separate ABORT gate. Prompts only crawl URLs from human-authored PR/Jira text, ignore machine-generated metadata URLs, skip duplicate GitHub resources already covered by `gh`, and continue on URL-only fetch failures unless business context is blocked.
- URL fetching (if needed) must use the sandbox-local `./rf-fetch-url` helper (enforces an allowlist).

## Allowlisted URL crawling
Reviewflow can provide an allowlist for safe URL crawling via `/workspaces/.reviewflow.toml` (optional).

Schema:
```toml
[crawl]
allow_hosts = ["github.com", "api.github.com"]
timeout_seconds = 20
max_bytes = 2000000

[codex]
# Optional defaults for review runs (CLI flags override these).
model = "gpt-5.2"
model_reasoning_effort = "high"
plan_mode_reasoning_effort = "xhigh"

[multipass]
# Optional defaults for big-profile reviews (CLI flags override these).
enabled = true
max_steps = 20
```

Defaults (when the file is missing/invalid):
- `allow_hosts = ["github.com", "api.github.com"]`
- `timeout_seconds = 20`
- `max_bytes = 2000000`

For supported `github.com` / `api.github.com` PR, issue, comment, and review URLs, `rf-fetch-url` routes through authenticated `gh api` using the sandbox GH config. Other allowlisted hosts continue to use direct HTTP fetches.

## Codex config notes
- `reviewflow pr` runs `codex exec` using base settings parsed from `/workspaces/academy+/.codex/config.toml`, plus optional overrides from `/workspaces/.reviewflow.toml` and `--codex-*` flags.
- Review runs disable the project-level ChunkHound MCP server (which indexes `/workspaces`) and inject a sandbox-scoped ChunkHound MCP server for the sandbox repo.
  - Reviewflow materializes a session-local ChunkHound config at `<session>/work/chunkhound/chunkhound.json` (derived from `/workspaces/.chunkhound.review.json`) that pins the session DB location.
  - Session-local ChunkHound DB lives under `<session>/work/chunkhound/.chunkhound.db` (daemon state also lives under `<session>/work/chunkhound/`).
  - MCP startup timeout is set to 20 seconds for the sandbox server.
  - Prompts instruct using MCP tools `search` and `code_research` (a.k.a. `chunkhound.search` / `chunkhound.code_research`).
- `gh` auth is made available to the Codex run by copying `~/.config/gh` (or `$GH_CONFIG_DIR`) into `<session>/work/gh_config` and setting `GH_CONFIG_DIR` to that copied path.
- `jira` auth is made available to the Codex run by copying the Jira CLI config file (default `~/.config/.jira/.config.yml` or `$JIRA_CONFIG_FILE`) into `<session>/work/jira_config` and setting `JIRA_CONFIG_FILE` to that copied path.
- Reviewflow also writes a sandbox-local `./rf-jira` helper which requires `JIRA_CONFIG_FILE`, forces `HOME`/`NETRC` from the real user home, and retries a few times on intermittent `401 Unauthorized` responses.
  - Debug: set `RF_JIRA_DEBUG=1` to print non-secret env diagnostics (HOME/NETRC path + existence) on each invocation.
  - Retry tuning: set `RF_JIRA_401_RETRIES=<n>` (default: 4).
- `/tmp` is added as a writable directory for the Codex sandbox via `--add-dir /tmp`.
- Reviewflow also sets `REVIEWFLOW_WORK_DIR=<session>/work` for the agent to store scratch files outside the repo tree.
- Review runs add `--dangerously-bypass-approvals-and-sandbox` so the agent can run `gh`/`jira` network reads in-session.

## Tests
Fast local checks (no network):
```bash
/workspaces/reviewflow/selftest.sh
```

Optional real Jira-in-Codex acceptance check (networked; requires working Jira auth in this container):
```bash
REVIEWFLOW_ACCEPTANCE_JIRA_KEY=ABAU-985 /workspaces/reviewflow/selftest.sh
```

Or run directly:
```bash
python3 /workspaces/reviewflow/reviewflow.py jira-smoke ABAU-985
```
