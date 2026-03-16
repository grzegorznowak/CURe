from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from cure_branding import DEPRECATED_CLI_ALIAS, PRIMARY_CLI_COMMAND
from cure_runtime import (
    _doctor_runtime_checks,
    _doctor_runtime_payload,
)
from cure_sessions import build_status_payload, resolve_observation_target
from paths import ReviewflowPaths

if TYPE_CHECKING:
    from reviewflow import ReviewflowRuntime


def _reviewflow():
    import reviewflow as rf

    return rf


def _watch_line_for_payload(payload: dict[str, object]) -> str:
    pr = payload.get("pr") if isinstance(payload.get("pr"), dict) else {}
    repo_slug = f"{pr.get('owner')}/{pr.get('repo')}#{pr.get('number')}"
    parts = [
        f"session={payload.get('session_id')}",
        f"repo={repo_slug}",
        f"status={payload.get('status')}",
        f"phase={payload.get('phase')}",
    ]
    latest_artifact = payload.get("latest_artifact") if isinstance(payload.get("latest_artifact"), dict) else {}
    latest_path = str((latest_artifact or {}).get("path") or "").strip()
    if latest_path:
        parts.append(f"artifact={latest_path}")
    llm = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
    llm_summary = str((llm or {}).get("summary") or "").strip()
    if llm_summary:
        parts.append(llm_summary)
    return " ".join(parts)


def preferred_cli_invocation(invocation: str) -> str:
    return f"{PRIMARY_CLI_COMMAND} {invocation}"


def deprecated_cli_invocation(invocation: str) -> str:
    return f"{DEPRECATED_CLI_ALIAS} {invocation}"


def deprecated_alias_variant(invocation: str) -> dict[str, str]:
    return {
        "name": "deprecated_alias",
        "summary": "Temporary one-release alias; prints a deprecation warning on stderr.",
        "invocation": deprecated_cli_invocation(invocation),
    }


def build_commands_catalog_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "reviewflow.commands",
        "commands": [
            {
                "name": "pr",
                "summary": "Create a new review session for a PR.",
                "targets": ["PR_URL"],
                "safety": "Use `--if-reviewed new` for stable agent-safe start semantics.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Prints the created session directory path on success.",
                "exit_codes": {"0": "review started", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("pr <PR_URL> --if-reviewed new"),
                "variants": [
                    {
                        "name": "compatibility",
                        "summary": "Bare `pr` keeps current prompt-or-new compatibility behavior.",
                        "invocation": preferred_cli_invocation("pr <PR_URL>"),
                    },
                    deprecated_alias_variant("pr <PR_URL>"),
                ],
            },
            {
                "name": "followup",
                "summary": "Run a follow-up review inside an existing session sandbox.",
                "targets": ["session_id"],
                "safety": "Reuses the existing sandbox and appends a new follow-up artifact.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Human-readable progress only; follow-up artifact path is not a stable stdout contract.",
                "exit_codes": {"0": "follow-up completed", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("followup <session_id>"),
                "variants": [deprecated_alias_variant("followup <session_id>")],
            },
            {
                "name": "resume",
                "summary": "Resume a multipass session, or use its existing PR URL compatibility behavior.",
                "targets": ["session_id", "PR_URL"],
                "safety": "PR URL mode keeps its special resume-or-followup behavior for compatibility.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Human-readable progress only.",
                "exit_codes": {"0": "resume or compatible follow-up completed", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("resume <session_id>"),
                "variants": [
                    {
                        "name": "pr_url_compatibility",
                        "summary": "PR URL mode preserves the existing special behavior documented in the README.",
                        "invocation": preferred_cli_invocation("resume <PR_URL>"),
                    },
                    deprecated_alias_variant("resume <session_id>"),
                ],
            },
            {
                "name": "zip",
                "summary": "Synthesize a final arbiter review for the PR's current HEAD.",
                "targets": ["PR_URL"],
                "safety": "Reads existing review artifacts; does not create a new sandbox.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Prints the generated zip markdown path on success.",
                "exit_codes": {"0": "zip completed", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("zip <PR_URL>"),
                "variants": [deprecated_alias_variant("zip <PR_URL>")],
            },
            {
                "name": "clean",
                "summary": "Delete an exact session, preview closed-session cleanup, or use the TTY cleaner.",
                "targets": ["session_id", "closed"],
                "safety": "Bulk cleanup is preview-first with `clean closed --json`; exact delete rejects `--yes`.",
                "tty": "Required only for `clean` with no target and `clean closed` without `--yes`.",
                "stdout": "Structured JSON on `--json`; otherwise human-readable cleanup output.",
                "exit_codes": {"0": "cleanup query or deletion completed", "2": "usage, lookup, or runtime error"},
                "recommended_invocation": preferred_cli_invocation("clean closed --json"),
                "variants": [
                    {
                        "name": "bulk_execute",
                        "summary": "Execute closed-session cleanup after previewing matches.",
                        "invocation": preferred_cli_invocation("clean closed --yes --json"),
                    },
                    {
                        "name": "exact_delete",
                        "summary": "Delete one exact session with a structured result.",
                        "invocation": preferred_cli_invocation("clean <session_id> --json"),
                    },
                    deprecated_alias_variant("clean <session_id>"),
                ],
            },
            {
                "name": "status",
                "summary": "Resolve a session or PR URL and report the current recorded run state.",
                "targets": ["session_id", "PR_URL"],
                "safety": "Read-only view backed by `meta.json` and recorded artifacts/logs.",
                "tty": "No TTY required.",
                "stdout": "Human-readable single-line status by default, structured JSON with `--json`.",
                "exit_codes": {"0": "target resolved", "2": "invalid target, lookup failure, or corrupt metadata"},
                "recommended_invocation": preferred_cli_invocation("status <session_id|PR_URL> --json"),
                "variants": [deprecated_alias_variant("status <session_id|PR_URL>")],
            },
            {
                "name": "watch",
                "summary": "Attach to a recorded session and follow progress until completion.",
                "targets": ["session_id", "PR_URL"],
                "safety": "Read-only attach flow; uses the same resolver as `status`.",
                "tty": "TTY mode reuses the existing dashboard; non-TTY mode prints plain polling lines.",
                "stdout": "Progress lines until the session reaches `done` or `error`.",
                "exit_codes": {
                    "0": "session finished with status=done",
                    "1": "session finished with status=error",
                    "2": "invalid target, lookup failure, or corrupt metadata",
                },
                "recommended_invocation": preferred_cli_invocation("watch <session_id|PR_URL>"),
                "variants": [deprecated_alias_variant("watch <session_id|PR_URL>")],
            },
        ],
    }


def commands_flow(args: argparse.Namespace, *, stdout: TextIO | None = None) -> int:
    out = stdout or sys.stdout
    payload = build_commands_catalog_payload()
    if bool(getattr(args, "json_output", False)):
        print(json.dumps(payload, indent=2, sort_keys=True), file=out)
        return 0
    for command in payload["commands"]:
        print(f"{command['name']}: {command['summary']}", file=out)
        print(f"  {command['recommended_invocation']}", file=out)
        for variant in command.get("variants", []):
            if isinstance(variant, dict) and str(variant.get("invocation") or "").strip():
                print(f"    {variant['name']}: {variant['invocation']}", file=out)
    return 0


def status_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdout: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    payload = build_status_payload(str(getattr(args, "target", "") or ""), sandbox_root=paths.sandbox_root)
    if bool(getattr(args, "json_output", False)):
        print(json.dumps(payload, indent=2, sort_keys=True), file=out)
        return 0
    print(_watch_line_for_payload(payload), file=out)
    return 0


def watch_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    rf = _reviewflow()
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    target = str(getattr(args, "target", "") or "")
    resolved = resolve_observation_target(target, sandbox_root=paths.sandbox_root, command_name="watch")
    interval = max(0.0, float(getattr(args, "interval", 2.0) or 0.0))
    verbosity = rf._coerce_ui_verbosity(str(getattr(args, "verbosity", "normal") or "normal"))

    try:
        is_tty = bool(out.isatty()) and bool(err.isatty())
    except Exception:
        is_tty = False

    if is_tty:
        color = rf._stream_supports_color(out) and (not bool(getattr(args, "no_color", False)))
        while True:
            out.write("\x1b[2J\x1b[H")
            out.flush()
            status = rf._render_ui_preview(
                session_dir=resolved.session_dir,
                meta_path=resolved.meta_path,
                verbosity=verbosity,
                color=color,
                width=None,
                height=None,
                final_newline=False,
                stdout=out,
            )
            if status in {"done", "error"}:
                return 0 if status == "done" else 1
            time.sleep(interval if interval > 0 else 0.2)

    last_line = None
    while True:
        payload = build_status_payload(resolved.session_id, sandbox_root=paths.sandbox_root, command_name="watch")
        line = _watch_line_for_payload(payload)
        if line != last_line:
            print(line, file=out)
            out.flush()
            last_line = line
        status = str(payload.get("status") or "").strip().lower()
        if status in {"done", "error"}:
            return 0 if status == "done" else 1
        time.sleep(interval if interval > 0 else 0.2)


def cache_prime(
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    host: str,
    owner: str,
    repo: str,
    base_ref: str,
    force: bool = False,
    quiet: bool = False,
    no_stream: bool = False,
) -> int:
    rf = _reviewflow()
    return rf.cache_prime(
        paths=paths,
        config_path=config_path,
        host=host,
        owner=owner,
        repo=repo,
        base_ref=base_ref,
        force=force,
        quiet=quiet,
        no_stream=no_stream,
    )


def cache_status(*, paths: ReviewflowPaths, host: str, owner: str, repo: str, base_ref: str) -> int:
    rf = _reviewflow()
    return rf.cache_status(paths=paths, host=host, owner=owner, repo=repo, base_ref=base_ref)


def pr_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    rf = _reviewflow()
    return rf._pr_flow_impl(
        args,
        paths=paths,
        config_path=config_path,
        codex_base_config_path=codex_base_config_path,
    )


def resume_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    rf = _reviewflow()
    return rf._resume_flow_impl(
        args,
        paths=paths,
        config_path=config_path,
        codex_base_config_path=codex_base_config_path,
    )


def followup_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    rf = _reviewflow()
    return rf._followup_flow_impl(
        args,
        paths=paths,
        config_path=config_path,
        codex_base_config_path=codex_base_config_path,
    )


def zip_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    rf = _reviewflow()
    return rf._zip_flow_impl(
        args,
        paths=paths,
        config_path=config_path,
        codex_base_config_path=codex_base_config_path,
    )


def interactive_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    rf = _reviewflow()
    return rf._interactive_flow_impl(
        args,
        paths=paths,
        config_path=config_path,
        stdin=stdin,
        stderr=stderr,
    )


def clean_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    rf = _reviewflow()
    session_id = str(getattr(args, "session_id", "") or "").strip()
    json_output = bool(getattr(args, "json_output", False))
    auto_yes = bool(getattr(args, "yes", False))
    out_stream = stdout or sys.stdout
    if (not session_id) and (json_output or auto_yes):
        raise rf.ReviewflowError("clean with no target does not accept --yes or --json.")
    if session_id == "closed":
        return rf.clean_closed_flow(args, paths=paths, stdin=stdin, stdout=out_stream, stderr=stderr)
    if session_id:
        if auto_yes:
            raise rf.ReviewflowError("clean <session_id> does not accept --yes.")
        return rf.clean_session(session_id, paths=paths, stdout=out_stream, json_output=json_output)
    return rf.interactive_clean_flow(args, paths=paths, stdin=stdin, stderr=stderr)


def jira_smoke_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    rf = _reviewflow()
    return rf._jira_smoke_flow_impl(
        args,
        paths=paths,
        config_path=config_path,
        codex_base_config_path=codex_base_config_path,
    )


def doctor_flow(args: argparse.Namespace, *, runtime: ReviewflowRuntime) -> int:
    checks = _doctor_runtime_checks(runtime, cli_profile=getattr(args, "agent_runtime_profile", None))
    if bool(getattr(args, "json_output", False)):
        ok_count = sum(1 for item in checks if item.status == "ok")
        warn_count = sum(1 for item in checks if item.status == "warn")
        fail_count = sum(1 for item in checks if item.status == "fail")
        payload = _doctor_runtime_payload(runtime, cli_profile=getattr(args, "agent_runtime_profile", None))
        payload["checks"] = [
            {"name": item.name, "status": item.status, "detail": item.detail} for item in checks
        ]
        payload["summary"] = {"ok": ok_count, "warn": warn_count, "fail": fail_count}
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if fail_count == 0 else 1

    ok_count = sum(1 for item in checks if item.status == "ok")
    warn_count = sum(1 for item in checks if item.status == "warn")
    fail_count = sum(1 for item in checks if item.status == "fail")
    for item in checks:
        print(f"[{item.status}] {item.name}: {item.detail}")
    print(f"summary: ok={ok_count} warn={warn_count} fail={fail_count}")
    return 0 if fail_count == 0 else 1


__all__ = [
    "build_commands_catalog_payload",
    "cache_prime",
    "cache_status",
    "clean_flow",
    "commands_flow",
    "doctor_flow",
    "followup_flow",
    "interactive_flow",
    "jira_smoke_flow",
    "pr_flow",
    "preferred_cli_invocation",
    "resume_flow",
    "status_flow",
    "watch_flow",
    "zip_flow",
]
