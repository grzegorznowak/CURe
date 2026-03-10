#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile \
  /workspaces/reviewflow/reviewflow.py \
  /workspaces/reviewflow/run.py \
  /workspaces/reviewflow/paths.py \
  /workspaces/reviewflow/meta.py \
  /workspaces/reviewflow/ui.py

python3 -m unittest discover -s /workspaces/reviewflow/tests -p 'test_*.py'

# Optional: real network/auth acceptance test (Codex must be available + Jira must be authenticated).
# Usage:
#   REVIEWFLOW_ACCEPTANCE_JIRA_KEY=ABAU-985 /workspaces/reviewflow/selftest.sh
if [[ -n "${REVIEWFLOW_ACCEPTANCE_JIRA_KEY:-}" ]]; then
  python3 /workspaces/reviewflow/reviewflow.py jira-smoke "${REVIEWFLOW_ACCEPTANCE_JIRA_KEY}"
fi
