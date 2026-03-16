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
"$tmpdir/venv/bin/cure" --help >/dev/null
"$tmpdir/venv/bin/cure" doctor --help >/dev/null
"$tmpdir/venv/bin/reviewflow" --help >/dev/null 2>&1
"$tmpdir/venv/bin/reviewflow" doctor --help >/dev/null 2>&1
python3 "$repo_root/tests/story26_cli_smoke.py" \
  --cli-bin "$tmpdir/venv/bin/cure" \
  --alias-bin "$tmpdir/venv/bin/reviewflow" \
  --script-bin /usr/bin/script

mkdir -p "$tmpdir/home"
uv_bin_dir="$(HOME="$tmpdir/home" uv tool dir --bin)"
HOME="$tmpdir/home" uv tool install --force --editable "$repo_root"
"$uv_bin_dir/cure" --help >/dev/null
"$uv_bin_dir/cure" doctor --help >/dev/null
"$uv_bin_dir/reviewflow" --help >/dev/null 2>&1
"$uv_bin_dir/reviewflow" doctor --help >/dev/null 2>&1
python3 "$repo_root/tests/story26_cli_smoke.py" \
  --cli-bin "$uv_bin_dir/cure" \
  --alias-bin "$uv_bin_dir/reviewflow" \
  --script-bin /usr/bin/script
