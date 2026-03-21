# Jira CLI Reference

Use this only when the workflow actually needs Jira context. Normal public GitHub PR review flows do not require Jira.

This repo uses the `jira` CLI (`ankitpokhrel/jira-cli`) to query and update Jira issues. With scoped Atlassian API tokens, point the CLI at the Atlassian API gateway instead of the site URL directly.

## Jira Site Details

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

## Install

The CLI binary should be available as `jira`.

Verify:

```bash
jira version
```

## Auth

Create an API token with scopes at:

```text
https://id.atlassian.com/manage-profile/security/api-tokens
```

Use either `~/.netrc` (recommended) or a short-lived `JIRA_API_TOKEN` env var. Never commit tokens to repo files, shell history snippets, or config checked into source control.

### Option A: `~/.netrc`

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

### Option B: `JIRA_API_TOKEN`

Prefer setting it for a single command or terminal session, not in dotfiles:

```bash
read -s -p "JIRA_API_TOKEN: " JIRA_API_TOKEN; echo
export JIRA_API_TOKEN
```

### Token Scopes

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

## Configure `jira-cli`

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

## Common Queries

### Active Sprint Issues Assigned To A User

This uses JQL (`sprint in openSprints()`) so it still works when `jira sprint list --current` is unavailable.

Do not add `ORDER BY` inside `-q`; `jira issue list` appends its own ordering.

```bash
ASSIGNEE_EMAIL="user@example.com"

jira issue list -p "${JIRA_PROJECT_KEY}" \
  -q "assignee = \"${ASSIGNEE_EMAIL}\" AND sprint in openSprints()" \
  --order-by rank --reverse \
  --plain --columns key,summary,status,priority
```

### My Work

```bash
jira issue list -p "${JIRA_PROJECT_KEY}" \
  -q 'assignee = currentUser() AND statusCategory != Done' \
  --order-by updated \
  --plain --columns key,summary,status,priority
```

## Security Notes

- Never store Jira tokens in repo files or commit history.
- Prefer `~/.netrc` with `chmod 600` or a short-lived session export.
- Scoped tokens may expire; rotate them before they do.

## Troubleshooting

### `401 Unauthorized`

Common causes:
- `JIRA_API_TOKEN` is exported but stale or invalid, which overrides `~/.netrc`.
- `~/.netrc` has the wrong `machine` host for the configured `--server`.

Quick checks:

```bash
env -u JIRA_API_TOKEN jira serverinfo
env -u JIRA_API_TOKEN jira issue view "${JIRA_PROJECT_KEY}-123" --plain
```

### `404 Not Found` Or “Issue Does Not Exist Or You Do Not Have Permission”

Jira often returns `404` when you are not authorized to view an issue. Resolve auth first, then confirm you have project and issue permissions.
