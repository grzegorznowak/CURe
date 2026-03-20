#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
import threading
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sectioned_review_markdown(*, business: str, technical: str) -> str:
    return "\n".join(
        [
            "**Summary**: ok",
            "",
            "## Business / Product Assessment",
            f"**Verdict**: {business}",
            "",
            "### Strengths",
            "- Business strength",
            "",
            "### In Scope Issues",
            "- None.",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "## Technical Assessment",
            f"**Verdict**: {technical}",
            "",
            "### Strengths",
            "- Technical strength",
            "",
            "### In Scope Issues",
            "- None.",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "### Reusability",
            "- None.",
            "",
        ]
    )


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def run_cmd(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout: float = 20.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise SystemExit(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def build_env(tmp_root: Path, fake_bin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_root / "home")
    env["XDG_CONFIG_HOME"] = str(tmp_root / "xdg_config")
    env["XDG_STATE_HOME"] = str(tmp_root / "xdg_state")
    env["XDG_CACHE_HOME"] = str(tmp_root / "xdg_cache")
    env["TERM"] = "dumb"
    env.pop("CURE_CONFIG", None)
    env.pop("REVIEWFLOW_CONFIG", None)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def write_fake_gh(bin_dir: Path) -> None:
    gh_path = bin_dir / "gh"
    gh_path.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys

args = sys.argv[1:]
if args[:2] == ["auth", "status"]:
    if os.environ.get("RF_FAKE_GH_FAIL_AUTH") == "1":
        print("fake gh auth failure", file=sys.stderr)
        raise SystemExit(1)
    print("github.com")
    raise SystemExit(0)

if args[:1] == ["api"]:
    if os.environ.get("RF_FAKE_GH_FAIL_API") == "1":
        print("fake gh api failure", file=sys.stderr)
        raise SystemExit(1)
    endpoint = ""
    for item in reversed(args[1:]):
        if not item.startswith("-"):
            endpoint = item
            break
    parts = [part for part in endpoint.split("/") if part]
    number = int(parts[-1]) if parts and parts[-1].isdigit() else 0
    payload = {"state": "open", "merged_at": None}
    if number == 41:
        payload = {"state": "closed", "merged_at": None}
    elif number == 42:
        payload = {"state": "open", "merged_at": None}
    elif number == 62:
        payload = {"state": "closed", "merged_at": "2026-03-10T12:00:00+00:00"}
    print(json.dumps(payload))
    raise SystemExit(0)

print(f"unsupported fake gh invocation: {args!r}", file=sys.stderr)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    gh_path.chmod(0o755)


def cli_cmd(binary: Path, sandbox_root: Path, *args: str) -> list[str]:
    return [
        str(binary),
        "--no-config",
        "--sandbox-root",
        str(sandbox_root),
        *args,
    ]


def write_session(
    *,
    root: Path,
    session_id: str,
    status: str,
    created_at: str,
    completed_at: str | None = None,
    resumed_at: str | None = None,
    host: str = "github.com",
    owner: str = "acme",
    repo: str = "repo",
    number: int = 1,
    phase: str = "review",
    llm: dict[str, object] | None = None,
    agent_runtime: dict[str, object] | None = None,
    error: dict[str, object] | None = None,
    followup_name: str | None = None,
) -> Path:
    session_dir = root / session_id
    repo_dir = session_dir / "repo"
    work_dir = session_dir / "work"
    logs_dir = work_dir / "logs"
    repo_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    review_md = session_dir / "review.md"
    review_md.write_text(
        _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
        encoding="utf-8",
    )
    for name in ("cure.log", "chunkhound.log", "codex.log"):
        (logs_dir / name).write_text(f"{name}\n", encoding="utf-8")

    followups: list[dict[str, object]] = []
    if followup_name:
        followups_dir = session_dir / "followups"
        followups_dir.mkdir(parents=True, exist_ok=True)
        followup_path = followups_dir / followup_name
        followup_path.write_text("# Followup\n", encoding="utf-8")
        followups.append(
            {
                "completed_at": "2026-03-10T12:05:00+00:00",
                "output_path": str(followup_path),
            }
        )

    meta: dict[str, object] = {
        "session_id": session_id,
        "status": status,
        "phase": phase,
        "phases": {
            "init": {"status": "done", "started_at": created_at, "finished_at": created_at},
            phase: {"status": status if status in {"done", "error"} else "running", "started_at": created_at},
        },
        "host": host,
        "owner": owner,
        "repo": repo,
        "number": number,
        "title": "Story 26 smoke fixture",
        "created_at": created_at,
        "paths": {
            "repo_dir": str(repo_dir),
            "work_dir": str(work_dir),
            "logs_dir": str(logs_dir),
            "review_md": str(review_md),
        },
        "logs": {
            "cure": str(logs_dir / "cure.log"),
            "chunkhound": str(logs_dir / "chunkhound.log"),
            "codex": str(logs_dir / "codex.log"),
        },
    }
    if completed_at is not None:
        meta["completed_at"] = completed_at
    if resumed_at is not None:
        meta["resumed_at"] = resumed_at
    if llm is not None:
        meta["llm"] = llm
    if agent_runtime is not None:
        meta["agent_runtime"] = agent_runtime
    if error is not None:
        meta["error"] = error
    if followups:
        meta["followups"] = followups

    (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return session_dir


def mutate_terminal_status(meta_path: Path, *, status: str, delay_seconds: float) -> None:
    def update() -> None:
        time.sleep(delay_seconds)
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        payload["status"] = status
        if status == "done":
            payload["completed_at"] = "2026-03-10T12:10:00+00:00"
        else:
            payload["failed_at"] = "2026-03-10T12:10:00+00:00"
            payload["error"] = {"type": "exception", "message": "pty failure"}
        phases = payload.get("phases")
        if isinstance(phases, dict):
            review = phases.get("review")
            if isinstance(review, dict):
                review["status"] = status
                review["finished_at"] = "2026-03-10T12:10:00+00:00"
        meta_path.write_text(json.dumps(payload), encoding="utf-8")

    thread = threading.Thread(target=update, daemon=True)
    thread.start()


def run_pty_watch(
    *,
    binary: Path,
    script_bin: Path,
    env: dict[str, str],
    sandbox_root: Path,
    session_id: str,
) -> int:
    status_file = sandbox_root / f"{session_id}.pty.exit"
    shell_cmd = (
        f"{shlex.quote(str(binary))} --no-config --sandbox-root {shlex.quote(str(sandbox_root))} "
        f"watch {shlex.quote(session_id)} --interval 0.1 --verbosity quiet --no-color; "
        f"rc=$?; printf '%s' \"$rc\" > {shlex.quote(str(status_file))}; exit 0"
    )
    proc = subprocess.run(
        [str(script_bin), "-q", "-c", shell_cmd, "/dev/null"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=20.0,
    )
    ensure(proc.returncode == 0, f"PTY wrapper failed: {proc.stderr}")
    ensure(status_file.is_file(), f"missing PTY exit status for {session_id}")
    return int(status_file.read_text(encoding="utf-8").strip())


def test_commands(primary_bin: Path, alias_bin: Path | None, env: dict[str, str], sandbox_root: Path) -> None:
    proc = run_cmd(cli_cmd(primary_bin, sandbox_root, "commands", "--json"), env=env)
    payload = json.loads(proc.stdout)
    ensure(payload["schema_version"] == 2, "commands schema_version mismatch")
    ensure(payload["kind"] == "cure.commands", "commands kind mismatch")
    names = [entry["name"] for entry in payload["commands"]]
    ensure(names == ["pr", "followup", "resume", "zip", "clean", "status", "watch"], "commands order mismatch")
    ensure("interactive" not in names, "interactive should be absent from curated catalog")
    for entry in payload["commands"]:
        for key in (
            "name",
            "summary",
            "targets",
            "safety",
            "tty",
            "stdout",
            "exit_codes",
            "recommended_invocation",
        ):
            ensure(key in entry, f"missing commands key {key!r}")

    human = run_cmd(cli_cmd(primary_bin, sandbox_root, "commands"), env=env)
    ensure("cure clean closed --json" in human.stdout, "commands human output missing clean")
    ensure("cure status <session_id|PR_URL> --json" in human.stdout, "commands human output missing status")
    ensure("cure watch <session_id|PR_URL>" in human.stdout, "commands human output missing watch")
    ensure("reviewflow" not in human.stdout, "commands human output should not advertise deprecated alias")

    _ = alias_bin


def test_status(binary: Path, env: dict[str, str], sandbox_root: Path) -> None:
    write_session(
        root=sandbox_root,
        session_id="done-older",
        status="done",
        created_at="2026-03-10T10:00:00+00:00",
        completed_at="2026-03-10T10:10:00+00:00",
        number=26,
    )
    write_session(
        root=sandbox_root,
        session_id="running-newer",
        status="running",
        created_at="2026-03-10T11:00:00+00:00",
        resumed_at="2026-03-10T11:05:00+00:00",
        number=26,
        llm={
            "preset": "claude-cli",
            "transport": "cli",
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "reasoning_effort": "high",
            "capabilities": {"supports_resume": True},
        },
        agent_runtime={"profile": "balanced", "provider": "claude", "permission_mode": "dontAsk"},
        followup_name="followup-1.md",
    )
    write_session(
        root=sandbox_root,
        session_id="created-later",
        status="done",
        created_at="2026-03-10T11:00:00+00:00",
        completed_at="2026-03-10T11:10:00+00:00",
        number=27,
    )
    write_session(
        root=sandbox_root,
        session_id="resumed-newest",
        status="error",
        created_at="2026-03-10T09:00:00+00:00",
        resumed_at="2026-03-10T12:00:00+00:00",
        number=27,
        error={"type": "exception", "message": "boom"},
    )
    corrupt_dir = sandbox_root / "corrupt-session"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "meta.json").write_text("{not-json", encoding="utf-8")

    exact = run_cmd(cli_cmd(binary, sandbox_root, "status", "running-newer", "--json"), env=env)
    exact_payload = json.loads(exact.stdout)
    ensure(exact_payload["resolved_target"]["session_id"] == "running-newer", "exact status mismatch")
    ensure(exact_payload["llm"]["summary"] == "llm=claude-cli/claude-sonnet-4-6/high", "llm summary mismatch")
    ensure(exact_payload["agent_runtime"]["profile"] == "balanced", "agent runtime mismatch")
    ensure(exact_payload["latest_artifact"]["path"].endswith("followup-1.md"), "latest artifact mismatch")

    pr_running = run_cmd(
        cli_cmd(binary, sandbox_root, "status", "https://github.com/acme/repo/pull/26", "--json"),
        env=env,
    )
    pr_running_payload = json.loads(pr_running.stdout)
    ensure(pr_running_payload["resolved_target"]["session_id"] == "running-newer", "PR running resolution mismatch")
    ensure(pr_running_payload["resolution_strategy"] == "newest_running", "PR running strategy mismatch")

    pr_fallback = run_cmd(
        cli_cmd(binary, sandbox_root, "status", "https://github.com/acme/repo/pull/27", "--json"),
        env=env,
        check=False,
    )
    ensure(pr_fallback.returncode == 0, "status error session should still exit 0")
    pr_fallback_payload = json.loads(pr_fallback.stdout)
    ensure(pr_fallback_payload["resolved_target"]["session_id"] == "resumed-newest", "PR fallback mismatch")
    ensure(pr_fallback_payload["status"] == "error", "PR fallback status mismatch")

    human = run_cmd(cli_cmd(binary, sandbox_root, "status", "running-newer"), env=env)
    ensure("session=running-newer" in human.stdout, "status human output missing session")
    ensure("status=running" in human.stdout, "status human output missing status")

    invalid = run_cmd(cli_cmd(binary, sandbox_root, "status", "/tmp/not-a-session"), env=env, check=False)
    ensure(invalid.returncode != 0, "path-like status target should fail")
    missing = run_cmd(cli_cmd(binary, sandbox_root, "status", "missing-session"), env=env, check=False)
    ensure(missing.returncode != 0, "missing status target should fail")
    corrupt = run_cmd(cli_cmd(binary, sandbox_root, "status", "corrupt-session"), env=env, check=False)
    ensure(corrupt.returncode != 0, "corrupt session should fail")
    unmatched = run_cmd(
        cli_cmd(binary, sandbox_root, "status", "https://github.com/acme/repo/pull/404"),
        env=env,
        check=False,
    )
    ensure(unmatched.returncode != 0, "unmatched PR should fail")


def test_watch(binary: Path, script_bin: Path, env: dict[str, str], sandbox_root: Path) -> None:
    running_done = write_session(
        root=sandbox_root,
        session_id="watch-running-done",
        status="running",
        created_at="2026-03-10T11:00:00+00:00",
        number=51,
    )
    mutate_terminal_status(running_done / "meta.json", status="done", delay_seconds=0.4)
    proc_done = run_cmd(
        cli_cmd(
            binary,
            sandbox_root,
            "watch",
            "watch-running-done",
            "--interval",
            "0.1",
            "--verbosity",
            "quiet",
            "--no-color",
        ),
        env=env,
        check=False,
    )
    ensure(proc_done.returncode == 0, "non-TTY watch done should exit 0")
    ensure("session=watch-running-done" in proc_done.stdout, "non-TTY watch done missing session")
    ensure("\x1b[" not in proc_done.stdout, "non-TTY watch done emitted ANSI")

    running_error = write_session(
        root=sandbox_root,
        session_id="watch-running-error",
        status="running",
        created_at="2026-03-10T11:00:00+00:00",
        number=52,
    )
    mutate_terminal_status(running_error / "meta.json", status="error", delay_seconds=0.4)
    proc_error = run_cmd(
        cli_cmd(
            binary,
            sandbox_root,
            "watch",
            "watch-running-error",
            "--interval",
            "0.1",
            "--verbosity",
            "quiet",
            "--no-color",
        ),
        env=env,
        check=False,
    )
    ensure(proc_error.returncode != 0, "non-TTY watch error should exit non-zero")
    ensure("status=error" in proc_error.stdout, "non-TTY watch error missing status")
    ensure("\x1b[" not in proc_error.stdout, "non-TTY watch error emitted ANSI")

    pty_env = dict(env)
    pty_env["TERM"] = "xterm-256color"

    pty_done = write_session(
        root=sandbox_root,
        session_id="pty-watch-done",
        status="running",
        created_at="2026-03-10T11:00:00+00:00",
        number=53,
    )
    mutate_terminal_status(pty_done / "meta.json", status="done", delay_seconds=0.4)
    ensure(
        run_pty_watch(
            binary=binary,
            script_bin=script_bin,
            env=pty_env,
            sandbox_root=sandbox_root,
            session_id="pty-watch-done",
        )
        == 0,
        "PTY watch done should exit 0",
    )

    pty_error = write_session(
        root=sandbox_root,
        session_id="pty-watch-error",
        status="running",
        created_at="2026-03-10T11:00:00+00:00",
        number=54,
    )
    mutate_terminal_status(pty_error / "meta.json", status="error", delay_seconds=0.4)
    ensure(
        run_pty_watch(
            binary=binary,
            script_bin=script_bin,
            env=pty_env,
            sandbox_root=sandbox_root,
            session_id="pty-watch-error",
        )
        != 0,
        "PTY watch error should exit non-zero",
    )


def test_clean(binary: Path, env: dict[str, str], sandbox_root: Path) -> None:
    exact_root = sandbox_root / "exact"
    exact_root.mkdir(parents=True, exist_ok=True)
    write_session(
        root=exact_root,
        session_id="exact-clean",
        status="done",
        created_at="2026-03-10T09:00:00+00:00",
        completed_at="2026-03-10T09:05:00+00:00",
        number=60,
    )
    exact = run_cmd(cli_cmd(binary, exact_root, "clean", "exact-clean", "--json"), env=env)
    exact_payload = json.loads(exact.stdout)
    ensure(exact_payload["kind"] == "cure.clean.result", "exact clean kind mismatch")
    ensure(exact_payload["deleted"][0]["session_id"] == "exact-clean", "exact clean deleted wrong session")
    ensure(not (exact_root / "exact-clean").exists(), "exact clean did not delete session")

    invalid_exact = run_cmd(cli_cmd(binary, exact_root, "clean", "exact-clean", "--yes"), env=env, check=False)
    ensure(invalid_exact.returncode != 0, "clean <session> --yes should fail")
    invalid_no_target_yes = run_cmd(cli_cmd(binary, exact_root, "clean", "--yes"), env=env, check=False)
    ensure(invalid_no_target_yes.returncode != 0, "clean --yes should fail")
    invalid_no_target_json = run_cmd(cli_cmd(binary, exact_root, "clean", "--json"), env=env, check=False)
    ensure(invalid_no_target_json.returncode != 0, "clean --json should fail")

    closed_root = sandbox_root / "closed"
    closed_root.mkdir(parents=True, exist_ok=True)
    write_session(
        root=closed_root,
        session_id="closed-clean",
        status="done",
        created_at="2026-03-10T09:00:00+00:00",
        completed_at="2026-03-10T09:05:00+00:00",
        number=41,
    )
    write_session(
        root=closed_root,
        session_id="open-clean",
        status="done",
        created_at="2026-03-10T09:00:00+00:00",
        completed_at="2026-03-10T09:05:00+00:00",
        number=42,
    )
    preview = run_cmd(cli_cmd(binary, closed_root, "clean", "closed", "--json"), env=env)
    preview_payload = json.loads(preview.stdout)
    ensure(preview_payload["kind"] == "cure.clean.preview", "closed preview kind mismatch")
    ensure([item["session_id"] for item in preview_payload["matched"]] == ["closed-clean"], "closed preview mismatch")
    ensure(preview_payload["deleted"] == [], "closed preview should not delete")
    ensure((closed_root / "closed-clean").exists(), "closed preview deleted session")

    execute = run_cmd(cli_cmd(binary, closed_root, "clean", "closed", "--yes", "--json"), env=env)
    execute_payload = json.loads(execute.stdout)
    ensure(execute_payload["kind"] == "cure.clean.result", "closed execute kind mismatch")
    ensure([item["session_id"] for item in execute_payload["deleted"]] == ["closed-clean"], "closed execute mismatch")
    ensure(not (closed_root / "closed-clean").exists(), "closed execute did not delete closed session")
    ensure((closed_root / "open-clean").exists(), "closed execute deleted open session")

    fail_env = dict(env)
    fail_env["RF_FAKE_GH_FAIL_AUTH"] = "1"
    auth_fail = run_cmd(cli_cmd(binary, closed_root, "clean", "closed", "--json"), env=fail_env, check=False)
    ensure(auth_fail.returncode != 0, "clean closed auth failure should be non-zero")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli-bin", required=True)
    parser.add_argument("--alias-bin")
    parser.add_argument("--script-bin", required=True)
    args = parser.parse_args()

    binary = Path(args.cli_bin).resolve()
    alias_bin = Path(args.alias_bin).resolve() if args.alias_bin else None
    script_bin = Path(args.script_bin).resolve()
    ensure(binary.is_file(), f"missing primary CLI binary: {binary}")
    if alias_bin is not None:
        ensure(alias_bin.is_file(), f"missing alias CLI binary: {alias_bin}")
    ensure(script_bin.is_file(), f"missing script binary: {script_bin}")

    with tempfile.TemporaryDirectory(prefix="cure-story26-smoke-") as tmp:
        tmp_root = Path(tmp)
        fake_bin = tmp_root / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        write_fake_gh(fake_bin)
        env = build_env(tmp_root, fake_bin)

        test_commands(binary, alias_bin, env, tmp_root / "commands")
        test_status(binary, env, tmp_root / "status")
        test_watch(binary, script_bin, env, tmp_root / "watch")
        test_clean(binary, env, tmp_root / "clean")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
