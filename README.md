# Reviewflow (ChunkHound + LLM Presets) — PR Review Sandboxes

Goal: create an isolated checkout of a PR, reuse a cached ChunkHound base index, top up indexing for the PR, then run a review agent against that sandbox without touching your source checkout. Reviews use a **sandbox-scoped ChunkHound MCP server** when the selected transport supports it.

Terminology:
- `CURe` = the codebase-under-review. In practice this is the sandbox checkout plus the surrounding PR, ticket, and supporting context the agent mines to understand that specific change accurately.

## Prereqs
- `gh` authenticated (`gh auth login -h github.com`)
- Any tooling referenced by the active reviewflow config `[review_intelligence].tool_prompt_fragment` must be available and authenticated
- The active reviewflow config includes a `[chunkhound]` section with an explicit `base_config_path`
- ChunkHound embedding key available via `CHUNKHOUND_EMBEDDING__API_KEY` (reviewflow will infer it from the configured `[chunkhound].base_config_path` if present)

## Install
Install reviewflow into the current Python environment:
```bash
python3 -m pip install /path/to/reviewflow
```

Or install reviewflow as a uv-managed CLI tool:
```bash
uv tool install /path/to/reviewflow
```

For a live repo-checkout install while iterating locally:
```bash
uv tool install --editable /path/to/reviewflow
```

After either install method, provision ChunkHound from the published release (default) and then run diagnostics:
```bash
reviewflow install
reviewflow doctor
reviewflow doctor --json
```

When `reviewflow` itself is installed via `uv tool`, `reviewflow install` provisions ChunkHound as a `uv` tool too, so `chunkhound` lands in the `uv tool` bin dir and is expected to be runnable from PATH.

Install ChunkHound from the latest upstream `main` instead:
```bash
reviewflow install --chunkhound-source git-main
```

Inspect the executable directory directly if needed:
```bash
uv tool dir --bin
```

## Onboarding a Project
Treat reviewflow as an external CLI tool for the project environment, not as an in-repo Python dependency.

1. Install `reviewflow` into the environment where engineers will run reviews.
   - `python3 -m pip install /path/to/reviewflow`
   - or `uv tool install /path/to/reviewflow`
2. Provision the review dependencies once in that environment.
   - `reviewflow install`
   - `reviewflow doctor`
3. Create a project-specific reviewflow config file and point reviewflow at it.
   - `reviewflow --config /path/to/project.reviewflow.toml ...`
   - or `REVIEWFLOW_CONFIG=/path/to/project.reviewflow.toml`
   - or use a small wrapper if your team wants a stable workspace-scoped file:
     `REVIEWFLOW_CONFIG=/workspaces/.reviewflow.toml reviewflow ...`
4. Put the project defaults into that config file.
   - `[review_intelligence]`
   - `[chunkhound].base_config_path`
   - optional `[paths]`, `[llm]`, `[llm_presets.*]`, `[codex]`, `[multipass]`
5. Add a thin project wrapper if you want a stable team entrypoint.
   - `make review-pr ...`
   - `just review-pr ...`
   - a shell script that exports `REVIEWFLOW_CONFIG` and calls `reviewflow`

The project itself does not need to import reviewflow. It only needs:
- the `reviewflow` executable available
- a project config file
- the required external tools (`gh`, `jira`, `codex`) installed separately if that workflow uses them

## Commands

Prime base cache (per repo + base branch):
```bash
reviewflow cache prime OWNER/REPO --base develop
```

Create sandbox + index + review:
```bash
reviewflow pr https://github.com/OWNER/REPO/pull/123
```

If the PR was already reviewed in this workspace, control how `reviewflow pr` behaves:
```bash
reviewflow pr https://github.com/OWNER/REPO/pull/123 --if-reviewed prompt|new|list|latest
```

Run a follow-up review on an existing session (writes a new markdown under `<session>/followups/`):
```bash
reviewflow followup <session_id>
```

Pick a past completed review and reopen its saved conversation when the provider supports resume:
```bash
reviewflow interactive
```
```bash
reviewflow interactive https://github.com/OWNER/REPO/pull/123
```

Synthesize a final “arbiter” review from the latest generated reviews for the PR’s current HEAD SHA:
```bash
reviewflow zip https://github.com/OWNER/REPO/pull/123
```
- Writes `<host_session>/zips/zip-<timestamp>.md` under the newest relevant completed session.
- Prints the output path to stdout on success (and prints the full markdown to stderr if the TUI is enabled).
- Ignores matching artifacts whose stored verdicts include `REJECT` on either assessment axis.
- Fails fast if no completed non-rejected review artifacts match the PR’s current HEAD SHA (run `pr`/`followup` first).

Skip updating the sandbox to the latest PR head (uses current checkout):
```bash
reviewflow followup <session_id> --no-update
```

Resume an aborted multipass review (continues from first missing step):
```bash
reviewflow resume <session_id>
# Or pass a PR URL:
# - If a resumable multipass session exists, it will resume that session.
# - Otherwise it will run a follow-up review against the latest completed session.
reviewflow resume https://github.com/OWNER/REPO/pull/123
```

Select a named preset and override it generically:
```bash
reviewflow pr https://github.com/OWNER/REPO/pull/123 \
  --llm-preset openrouter-responses \
  --llm-model x-ai/grok-4.1-fast \
  --llm-effort high \
  --llm-plan-effort xhigh \
  --llm-max-output-tokens 9000 \
  --llm-header HTTP-Referer=https://academypl.us \
  --llm-set provider='{ sort = "latency" }'
```

Deprecated Codex compatibility flags still work:
```bash
reviewflow pr https://github.com/OWNER/REPO/pull/123 \
  --codex-model gpt-5.3-codex-spark \
  --codex-effort low
```

List sandboxes:
```bash
reviewflow list
```

Show the migration deprecation notice:
```bash
reviewflow migrate-storage
```

Show the same deprecation notice while tolerating the legacy flag:
```bash
reviewflow migrate-storage --apply
```

Delete one sandbox:
```bash
reviewflow clean <session_id>
```

Delete sessions whose PR is already closed or merged:
```bash
reviewflow clean closed
```

Interactive cleanup picker:
```bash
reviewflow clean
```

## Notes
- By default, reviewflow uses XDG-style paths:
  - config: `XDG_CONFIG_HOME/reviewflow/reviewflow.toml` or `~/.config/reviewflow/reviewflow.toml`
  - sandboxes: `XDG_STATE_HOME/reviewflow/sandboxes` or `~/.local/state/reviewflow/sandboxes`
  - cache: `XDG_CACHE_HOME/reviewflow` or `~/.cache/reviewflow`
  - Codex base config: `~/.codex/config.toml`
- Override the active config file with `--config PATH` or `REVIEWFLOW_CONFIG`.
- Use `--no-config` to ignore the reviewflow TOML entirely while still honoring CLI flags and env overrides.
- Relative `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and `XDG_CACHE_HOME` values are ignored; reviewflow falls back to the home-based defaults.
- Override the reviewflow-owned roots with `--sandbox-root`, `--cache-root`, `REVIEWFLOW_SANDBOX_ROOT`, `REVIEWFLOW_CACHE_ROOT`, or `[paths]`.
- `reviewflow migrate-storage` is now only a deprecation/removal path. It exits cleanly and performs no filesystem migration.
- `reviewflow clean` without a session id opens a full-screen TTY cleaner with preset filters (`All`, `Done`, `Error`, `Running`, `Done>24h`, `Done>7d`, `Done>30d`), search, visible-only bulk selection, and delete previews.
- `reviewflow clean closed` queries GitHub for each PR represented by the stored sessions, shows a live progress bar while resolving PR states, previews the matched closed/merged PR sessions, and deletes them only after TTY confirmation.
- The interactive cleaner shows all sessions by default, marks risky entries (`running` or newer than 24h), and requires typed `DELETE` before removing any risky selection.
- Base caches live under the resolved reviewflow cache root.
- ChunkHound is exposed to the review agent via a sandbox-scoped MCP server (configured per run).
- `reviewflow doctor` is read-only: it diagnoses tool presence, config paths, `gh` auth, and Jira config, but does not install or authenticate anything.
- `reviewflow doctor --json` prints the resolved config/sandbox/cache/Codex/ChunkHound paths with their sources (`cli`, `env`, `config`, `default`, or disabled).
- `reviewflow pr` prints progress to **stderr** (phase markers + streamed tool output by default) and prints the sandbox session path to **stdout** on success.
- Built-in review artifacts use a dual-axis format: `Summary`, then `Business / Product Assessment` and `Technical Assessment`, each with its own `Verdict`, `Strengths`, `In Scope Issues`, and `Out of Scope Issues`. `Reusability` lives under the technical assessment. There is no merged final decision.
- `Business / Product Assessment` uses product/ticket scope: Jira is primary, the PR description is secondary, and clarifying Jira/GitHub discussion can expand what counts as `In Scope`.
- `Technical Assessment` uses implementation scope: `In Scope` is limited to code paths, behavior, and responsibilities the PR directly changes or owns.
- The same issue can be `In Scope` for the business/product section and `Out of Scope` for the technical section, or vice versa.
- History/picker/list/dashboard summaries render the stored verdicts compactly as `biz=... tech=...` and show the resolved review-agent summary as `llm=<preset>/<model>/<effort>`.
- Historical review selection and `zip` only see sessions that still exist on disk; `clean closed` can intentionally prune older merged/closed PR history.
- Use `reviewflow interactive` to pick a past completed review and reopen its saved conversation when `meta.llm.capabilities.supports_resume=true`.
- `reviewflow interactive` prints the latest saved review artifact path for the selected session before resuming.
- `openai`, `openrouter`, and `gemini` presets are execution-only in v1: no `interactive` and no multipass `resume`.
- `codex` and `claude` presets support saved resume metadata and `interactive`.
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
- Generated review artifacts normalize sandbox-local file refs to portable `path:line` text instead of embedding absolute sandbox-local Markdown file links.
- Provider-neutral runtime metadata is persisted under `meta.json` in `llm` (`preset`, `transport`, `provider`, resolved model/effort values, runtime overrides, adapter metadata, resume when supported, capabilities`).
- Legacy Codex sessions are still read from `meta.codex`; new Codex runs keep that metadata as a deprecated compatibility mirror.

## Prompt profiles (default: `auto`)
If you don’t pass `--prompt` or `--prompt-file`, reviewflow selects a prompt template by profile:
- `auto` (default): chooses `normal` vs `big` based on local git diff stats
- `normal`: packaged builtin `builtin:mrereview_gh_local.md`
- `big`: multipass by default (plan -> steps -> synth), using:
  - `builtin:mrereview_gh_local_big_plan.md`
  - `builtin:mrereview_gh_local_big_step.md`
  - `builtin:mrereview_gh_local_big_synth.md`
  - (single-pass fallback template remains available at `builtin:mrereview_gh_local_big.md`)
- `default`: `builtin:default.md` (no GH/Jira gate)

Auto thresholds (balanced defaults):
- Big if `changed_files >= 30` OR `(additions + deletions) >= 1500`
- Override with: `--big-if-files N` and `--big-if-lines N`

Extra contributor context placeholder (for custom prompts):
- `--agent-desc "..."` or `--agent-desc-file path.txt` populates `$AGENT_DESC`
- Custom prompts may also use `$REVIEW_INTELLIGENCE_GUIDANCE`; if the config is absent, that placeholder renders only the fixed CURe-first guidance.

`--no-index` behavior:
- `--no-index` is only supported with `--prompt/--prompt-file` or `--no-review`.
- Built-in prompt profiles (`auto/normal/big/default`) require ChunkHound MCP and will fail fast if `--no-index` is set.
- Built-in prompt profiles also require the active reviewflow config `[review_intelligence].tool_prompt_fragment`.

## ABORT behavior (mrereview prompts)
The `mrereview_gh_local*` prompts begin with a mandatory business-context gate:
- Prompts perform the gate **in-session** using the configured review-intelligence guidance from the active reviewflow config.
- If the required configured intelligence gathering fails, or the agent cannot gather enough context to understand the requested outcome, the prompt must ABORT with both assessment verdicts set to `REJECT`.

## Review-Intelligence Contract
Built-in prompt profiles compose review-intelligence guidance from two pieces:
- `[review_intelligence].tool_prompt_fragment`
- A fixed CURe-first guidance fragment that tells the agent to use any source or tool that materially improves understanding of the codebase-under-review

Schema:
```toml
[paths]
# Optional overrides for reviewflow-owned storage.
sandbox_root = "/absolute/path/to/reviewflow-sandboxes"
cache_root = "/absolute/path/to/reviewflow-cache"

[review_intelligence]
tool_prompt_fragment = """
Preferred review-intelligence tools:
- Use GitHub MCP for PR context when available.
- Otherwise use gh CLI / gh api.
- Use the approved tracker tooling for ticket context.
- Use any additional tools or sources that materially improve understanding of the codebase-under-review (CURe).
"""

[llm]
default_preset = "team_codex"

[llm_presets.team_codex]
preset = "codex-cli"
model = "gpt-5.4"
reasoning_effort = "high"
plan_reasoning_effort = "xhigh"
env = {}

[llm_presets.fast_router]
preset = "openrouter-responses"
api_key = "..."
model = "x-ai/grok-4.1-fast"
reasoning_effort = "high"
plan_reasoning_effort = "xhigh"
max_output_tokens = 9000
headers = { "HTTP-Referer" = "https://academypl.us", "X-OpenRouter-Title" = "reviewflow" }
request = {}

# Direct built-in preset ids also work in default_preset / --llm-preset:
# codex-cli
# claude-cli
# gemini-cli
# openai-responses
# openrouter-responses

[llm_presets.openai_default]
preset = "openai-responses"
api_key = "..."
model = "gpt-5.4"
reasoning_effort = "high"
plan_reasoning_effort = "xhigh"
text_verbosity = "low"
store = false
include = []
metadata = {}
headers = {}
request = {}

[codex]
# Optional: override the base Codex config path used for legacy/default Codex resolution.
base_config_path = "/absolute/path/to/codex-config.toml"

# Deprecated compatibility defaults for Codex-only runs.
model = "gpt-5.2"
model_reasoning_effort = "high"
plan_mode_reasoning_effort = "xhigh"

[multipass]
# Optional defaults for big-profile reviews (CLI flags override these).
enabled = true
max_steps = 20
```

Behavior:
- Built-in prompts fail fast if `[review_intelligence].tool_prompt_fragment` is missing or empty.
- There is no special URL-gateway policy in the review prompt contract.
- Tool and source choice is judged by whether it materially improves understanding of the CURe.

## ChunkHound Config Sourcing
Reviewflow derives review/session ChunkHound configs from the explicit `[chunkhound].base_config_path` declared in the active reviewflow config, then applies a narrow reviewflow-owned override layer before pinning the per-run database path.

Schema:
```toml
[chunkhound]
base_config_path = "/absolute/path/to/chunkhound-base.json"

[chunkhound.indexing]
# Optional: when set, each list replaces the corresponding list in the base config.
include = ["**/*.py", "**/*.ts"]
exclude = ["**/.claude/**", "**/openspec/**"]
per_file_timeout_seconds = 6
per_file_timeout_min_size_kb = 128

[chunkhound.research]
algorithm = "hybrid"
```

Behavior:
- `base_config_path` is required and has no default.
- Reviewflow reads the base ChunkHound JSON from that path, applies the selected overrides above, then writes a session-local `chunkhound.json`.
- Reviewflow still force-overrides the database provider/path for base caches and session-local DBs.
- Reviewflow-owned list overrides use replace semantics, not merge semantics.
- Secrets and provider-specific config stay in the base ChunkHound config file rather than being duplicated into the reviewflow config.

## LLM preset notes
- Presets are the main operator surface for `pr`, `followup`, `resume`, and `zip`.
- Built-in preset ids supported in v1:
  - `codex-cli`
  - `claude-cli`
  - `gemini-cli`
  - `openai-responses`
  - `openrouter-responses`
- Named blocks under `[llm_presets.*]` must set `preset = "<built-in-id>"` and then only override relevant fields.
- `--llm-*` overrides take precedence over preset values.
- Deprecated `--codex-*` flags still work for Codex compatibility mode and apply after generic `--llm-*` overrides.
- Public config no longer requires `transport`, `provider`, `endpoint`, `base_url`, or `command` for built-in presets.
- Legacy explicit Story 20 preset blocks are still read as deprecated compatibility input and normalized onto the built-in ids above.
- Legacy `[codex]` defaults are mapped to a synthetic `legacy_codex` preset when no named preset is selected.

## Codex transport notes
- Codex runs still use base settings from the resolved Codex config path (`--codex-config`, `REVIEWFLOW_CODEX_CONFIG`, `[codex].base_config_path`, then `~/.codex/config.toml`), plus optional overrides from the active reviewflow config.
- Review runs disable any non-sandbox ChunkHound MCP server from the base Codex config and inject a sandbox-scoped ChunkHound MCP server for the sandbox repo.
  - Reviewflow materializes a session-local ChunkHound config at `<session>/work/chunkhound/chunkhound.json` (derived from `[chunkhound].base_config_path` plus reviewflow overrides) and pins the session DB location there.
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
./selftest.sh
```

Optional real Jira-in-Codex acceptance check (networked; requires working Jira auth in this container):
```bash
REVIEWFLOW_ACCEPTANCE_JIRA_KEY=ABAU-985 ./selftest.sh
```

Or run directly:
```bash
reviewflow jira-smoke ABAU-985
```
