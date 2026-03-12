#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -m py_compile \
  "$repo_root/reviewflow.py" \
  "$repo_root/run.py" \
  "$repo_root/paths.py" \
  "$repo_root/meta.py" \
  "$repo_root/ui.py" \
  "$repo_root/prompts/__init__.py"

python3 -m unittest discover -s "$repo_root/tests" -p 'test_*.py'

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
python3 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install "$repo_root"
"$tmpdir/venv/bin/reviewflow" --help >/dev/null
"$tmpdir/venv/bin/reviewflow" doctor --help >/dev/null

mkdir -p "$tmpdir/home"
uv_bin_dir="$(HOME="$tmpdir/home" uv tool dir --bin)"
HOME="$tmpdir/home" uv tool install --force --editable "$repo_root"
"$uv_bin_dir/reviewflow" --help >/dev/null
"$uv_bin_dir/reviewflow" doctor --help >/dev/null

# Optional: real network/auth acceptance test (Codex must be available + Jira must be authenticated).
# Usage:
#   REVIEWFLOW_ACCEPTANCE_JIRA_KEY=ABAU-985 ./selftest.sh
if [[ -n "${REVIEWFLOW_ACCEPTANCE_JIRA_KEY:-}" ]]; then
  "$tmpdir/venv/bin/reviewflow" jira-smoke "${REVIEWFLOW_ACCEPTANCE_JIRA_KEY}"
fi
