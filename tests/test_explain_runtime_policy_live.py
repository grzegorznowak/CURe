"""Opt-in live proof for explain's interactive-parity runtime policy.

Run with:

    CURE_RUN_LIVE_POLICY=1 python -m pytest tests/test_explain_runtime_policy_live.py -v

The fixture is disposable. A real Codex run must mutate only its tracked probe
file while the explain flow announces the effective permissive policy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import cure as rf


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("CURE_RUN_LIVE_POLICY") != "1",
        reason="set CURE_RUN_LIVE_POLICY=1 to run the live explain policy proof",
    ),
    pytest.mark.skipif(sys.platform != "linux", reason="live Codex policy proof is Linux-only"),
]


def test_live_explain_announces_and_exercises_interactive_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("codex") is None:
        pytest.skip("codex CLI is unavailable")

    sandbox_root = tmp_path / "sessions"
    session_dir = sandbox_root / "live-policy"
    repo = session_dir / "repo"
    work = session_dir / "work"
    repo.mkdir(parents=True)
    work.mkdir()
    probe = repo / "policy-probe.txt"
    probe.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "live@test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "live test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "policy-probe.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)

    review_md = session_dir / "review.md"
    review_md.write_text("# Final review\n\nThe policy probe is ready.\n", encoding="utf-8")
    meta = {
        "session_id": "live-policy",
        "status": "done",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "pr_url": "https://github.com/acme/repo/pull/999999",
        "host": "github.com",
        "owner": "acme",
        "repo": "repo",
        "number": 999999,
        "paths": {
            "session_dir": str(session_dir),
            "repo_dir": str(repo),
            "work_dir": str(work),
            "review_md": str(review_md),
        },
    }
    (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    monkeypatch.setattr(
        rf,
        "resolve_llm_config_from_args",
        lambda *args, **kwargs: (
            {"provider": "codex", "preset": "codex-cli"},
            {"base_codex_config": {"sandbox_mode": "read-only"}},
        ),
    )
    monkeypatch.setattr(
        rf,
        "load_builtin_prompt_text",
        lambda _name: (
            "This is a bounded live permission test. Replace the complete contents of "
            "policy-probe.txt with exactly: after-policy-proof\\n. Then briefly explain that change."
        ),
    )
    args = argparse.Namespace(
        pr_url=meta["pr_url"],
        explain_prompt=None,
        open_in_codex=False,
        quiet=False,
        no_stream=True,
        verbosity="normal",
    )
    paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=tmp_path / "cache")
    assert rf._explain_flow_impl(args, paths=paths) == 0

    captured = capsys.readouterr()
    assert "EXPLAIN mode: sandbox=None approval=None bypass=True" in captured.err
    assert probe.read_text(encoding="utf-8") == "after-policy-proof\n"
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert " M policy-probe.txt" in status
