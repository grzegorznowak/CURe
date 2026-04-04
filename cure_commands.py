from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
import tomllib
from typing import TYPE_CHECKING, TextIO

from cure_branding import PRIMARY_CLI_COMMAND
from cure_errors import ReviewflowError
from cure_flows import _has_embedding_config, discover_repo_local_chunkhound_config
from cure_runtime import (
    LOCAL_AGENT_PRESET_BY_NAME,
    REVIEW_INTELLIGENCE_CONFIG_EXAMPLE,
    _doctor_runtime_checks,
    _doctor_runtime_payload,
    load_chunkhound_runtime_config,
    load_reviewflow_chunkhound_config,
    resolve_local_agent_selection,
    toml_string,
)
from cure_sessions import build_status_payload, resolve_observation_target
from paths import ReviewflowPaths

if TYPE_CHECKING:
    from cure_runtime import ReviewflowRuntime


def _reviewflow():
    import cure as rf

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
    multipass = payload.get("multipass") if isinstance(payload.get("multipass"), dict) else {}
    multipass_enabled = bool(multipass.get("enabled") is True)
    multipass_mode = str(multipass.get("mode") or "").strip().lower()
    if multipass and (multipass_enabled or multipass_mode == "multipass"):
        mp_bits: list[str] = []
        step_workers = multipass.get("step_workers")
        effective_step_workers = multipass.get("effective_step_workers")
        if isinstance(step_workers, int) and step_workers > 0:
            if isinstance(effective_step_workers, int) and effective_step_workers > 0:
                mp_bits.append(f"multipass_workers={effective_step_workers}/{step_workers}")
            else:
                mp_bits.append(f"multipass_workers={step_workers}")
        step_states = multipass.get("step_states") if isinstance(multipass.get("step_states"), list) else []
        if step_states:
            queued = 0
            running = 0
            completed = 0
            failed = 0
            reused = 0
            for item in step_states:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "").strip().lower()
                if status == "queued":
                    queued += 1
                elif status in {"running", "awaiting_validation"}:
                    running += 1
                elif status == "completed":
                    completed += 1
                elif status == "reused":
                    reused += 1
                elif status in {"failed", "canceled"}:
                    failed += 1
            state_bits: list[str] = []
            if running:
                state_bits.append(f"{running} running")
            if queued:
                state_bits.append(f"{queued} queued")
            if completed:
                state_bits.append(f"{completed} completed")
            if reused:
                state_bits.append(f"{reused} reused")
            if failed:
                state_bits.append(f"{failed} failed")
            if state_bits:
                mp_bits.append("steps=" + ",".join(state_bits))
        if mp_bits:
            parts.append(" ".join(mp_bits))
    live = payload.get("live_progress") if isinstance(payload.get("live_progress"), dict) else {}
    current = live.get("current") if isinstance(live.get("current"), dict) else {}
    current_text = str((current or {}).get("text") or (live or {}).get("last_agent_message") or "").strip()
    if current_text:
        current_text = " ".join(current_text.split())
        if len(current_text) > 80:
            current_text = current_text[:79] + "…"
        parts.append(f"current={current_text}")
    chunkhound = payload.get("chunkhound") if isinstance(payload.get("chunkhound"), dict) else {}
    access = chunkhound.get("access") if isinstance(chunkhound.get("access"), dict) else {}
    access_stage = str((access or {}).get("preflight_stage") or "").strip()
    access_status = str((access or {}).get("preflight_stage_status") or "").strip()
    access_error = str((access or {}).get("error") or "").strip()
    access_elapsed = access.get("elapsed_seconds")
    show_access = bool(access_stage) and (
        str(payload.get("phase") or "").strip() == "chunkhound_access_preflight"
        or (not bool(access.get("preflight_ok")))
        or access_status in {"running", "error", "timeout"}
    )
    if show_access:
        access_bits = [f"chunkhound={access_stage}"]
        if access_status:
            access_bits.append(access_status)
        if isinstance(access_elapsed, (int, float)):
            access_bits.append(f"{float(access_elapsed):.1f}s")
        if access_error and access_status in {"error", "timeout"}:
            compact_error = " ".join(access_error.split())
            if len(compact_error) > 80:
                compact_error = compact_error[:79] + "…"
            access_bits.append(compact_error)
        parts.append(" ".join(access_bits))
    return " ".join(parts)


def preferred_cli_invocation(invocation: str) -> str:
    return f"{PRIMARY_CLI_COMMAND} {invocation}"


def build_commands_catalog_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "cure.commands",
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
                ],
            },
            {
                "name": "resume",
                "summary": "Resume a multipass session, or use its existing completed-session PR URL compatibility behavior.",
                "targets": ["session_id", "PR_URL"],
                "safety": "PR URL mode keeps its existing completed-session compatibility behavior.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Human-readable progress only.",
                "exit_codes": {"0": "resume or compatible completed-session flow completed", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("resume <session_id>"),
                "variants": [
                    {
                        "name": "pr_url_compatibility",
                        "summary": "PR URL mode preserves the existing special behavior documented in the README.",
                        "invocation": preferred_cli_invocation("resume <PR_URL>"),
                    },
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
                "variants": [],
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
                "variants": [],
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
                "variants": [],
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


def _path_has_text(path: Path) -> bool:
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return False


def _default_chunkhound_base_config_path(config_path: Path) -> Path:
    return (config_path.parent / "chunkhound-base.json").resolve(strict=False)


def _load_existing_chunkhound_base_config_path(config_path: Path) -> Path | None:
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ReviewflowError(f"Failed to read CURe config at {config_path}: {exc}") from exc
    if not text.strip():
        return None
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ReviewflowError(
            f"Failed to parse existing CURe config at {config_path}; use --force to replace it."
        ) from exc
    chunkhound = raw.get("chunkhound")
    if not isinstance(chunkhound, dict):
        return None
    raw_path = str(chunkhound.get("base_config_path") or "").strip()
    if not raw_path:
        return None
    resolved = Path(raw_path).expanduser()
    if not resolved.is_absolute():
        resolved = config_path.parent / resolved
    return resolved.resolve(strict=False)


def _auto_embedding_block() -> dict[str, str] | None:
    if os.environ.get("VOYAGE_API_KEY"):
        return {"provider": "voyage", "model": "voyage-code-3"}
    if os.environ.get("OPENAI_API_KEY"):
        return {"provider": "openai", "model": "text-embedding-3-small"}
    return None


def _render_init_config(*, runtime: ReviewflowRuntime, chunkhound_base_config_path: Path) -> str:
    lines = [
        "# Generated by `cure init`.",
        "# This file is intentionally non-secret and safe to edit locally.",
        "",
        "[paths]",
        f"sandbox_root = {json.dumps(str(runtime.paths.sandbox_root))}",
        f"cache_root = {json.dumps(str(runtime.paths.cache_root))}",
        "",
        REVIEW_INTELLIGENCE_CONFIG_EXAMPLE.rstrip(),
        "",
        "[chunkhound]",
        f"base_config_path = {json.dumps(str(chunkhound_base_config_path))}",
        "",
    ]
    return "\n".join(lines)


def _default_chunkhound_base_config_payload() -> dict[str, object]:
    payload: dict[str, object] = {}
    embedding = _auto_embedding_block()
    if embedding is not None:
        payload["embedding"] = embedding
    return payload


def _write_chunkhound_base_config_file(path: Path) -> str:
    payload = _default_chunkhound_base_config_payload()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    embedding = payload.get("embedding")
    if isinstance(embedding, dict):
        provider = str(embedding.get("provider") or "").strip()
        if provider:
            return f" ({provider} embedding defaults)"
    return ""


def _stream_is_tty(stream: TextIO | None) -> bool:
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _validate_chunkhound_base_config_choice(path: Path) -> Path:
    rf = _reviewflow()
    resolved = path.expanduser().resolve(strict=False)
    rf._read_chunkhound_json_config(resolved)  # type: ignore[attr-defined]
    return resolved


def _resolved_runtime_config_for_repo_local_discovery(*, runtime: ReviewflowRuntime) -> dict[str, object] | None:
    if not runtime.config_enabled:
        return None
    try:
        _, _, resolved = load_chunkhound_runtime_config(config_path=runtime.config_path, require=True)
        return resolved
    except ReviewflowError:
        return None


def _collect_chunkhound_base_config_choices(
    *,
    runtime: ReviewflowRuntime,
    invocation_cwd: Path,
) -> tuple[list[dict[str, str]], int, dict[str, object]]:
    choices: list[dict[str, str]] = []
    seen: set[Path] = set()
    current_path: Path | None = None
    current_valid = False
    discovery = discover_repo_local_chunkhound_config(
        invocation_cwd=invocation_cwd,
        pr=None,
        resolved_runtime_config=_resolved_runtime_config_for_repo_local_discovery(runtime=runtime),
    )
    try:
        cfg, _ = load_reviewflow_chunkhound_config(config_path=runtime.config_path, require=True)
        assert cfg is not None
        current_path = cfg.base_config_path.resolve(strict=False)
        current_valid = True
    except ReviewflowError:
        current_path = _load_existing_chunkhound_base_config_path(runtime.config_path)
        if current_path is not None:
            current_path = current_path.resolve(strict=False)

    def add_choice(*, kind: str, path: Path, label: str) -> None:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            return
        try:
            _validate_chunkhound_base_config_choice(resolved)
        except ReviewflowError:
            return
        choices.append({"kind": kind, "path": str(resolved), "label": label})
        seen.add(resolved)

    if current_valid and current_path is not None:
        add_choice(kind="current", path=current_path, label=f"Keep current configured base config ({current_path})")

    if str(discovery.get("candidate_state") or "") == "candidate":
        config_path_raw = str(discovery.get("config_path") or "").strip()
        config_file_name = str(discovery.get("config_file_name") or "").strip()
        if config_path_raw:
            candidate = Path(config_path_raw).resolve(strict=False)
            label_name = config_file_name or candidate.name
            add_choice(
                kind="repo_local",
                path=candidate,
                label=f"Use repo-local {label_name} ({candidate})",
            )

    for preferred_name in ("chunkhound.json", ".chunkhound.json"):
        add_choice(
            kind="invocation_cwd",
            path=invocation_cwd / preferred_name,
            label=f"Use {preferred_name} from the current directory ({(invocation_cwd / preferred_name).resolve(strict=False)})",
        )

    generated_path = _default_chunkhound_base_config_path(runtime.config_path)
    choices.append(
        {
            "kind": "generated_default",
            "path": str(generated_path),
            "label": f"Generate or refresh the CURe default base config ({generated_path})",
        }
    )

    default_index = len(choices) - 1
    if current_valid and current_path is not None:
        for idx, item in enumerate(choices):
            if Path(item["path"]) == current_path:
                default_index = idx
                break
    else:
        for preferred_name in ("chunkhound.json", ".chunkhound.json"):
            for idx, item in enumerate(choices):
                if Path(item["path"]).name == preferred_name:
                    default_index = idx
                    return choices, default_index, discovery
    return choices, default_index, discovery


def _upsert_chunkhound_base_config_path(*, config_path: Path, runtime: ReviewflowRuntime, base_config_path: Path) -> bool:
    rendered = _render_init_config(runtime=runtime, chunkhound_base_config_path=base_config_path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(rendered, encoding="utf-8")
        return True
    except OSError as exc:
        raise ReviewflowError(f"Failed to read CURe config at {config_path}: {exc}") from exc

    if not text.strip():
        config_path.write_text(rendered, encoding="utf-8")
        return True

    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        config_path.write_text(rendered, encoding="utf-8")
        return True

    new_line = f"base_config_path = {toml_string(str(base_config_path))}"
    lines = text.splitlines()
    replaced = False
    in_chunkhound = False
    insert_at: int | None = None

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[[") and stripped.endswith("]]"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_chunkhound and not replaced:
                insert_at = idx
                break
            in_chunkhound = stripped == "[chunkhound]"
            continue
        if in_chunkhound and stripped.startswith("base_config_path"):
            lines[idx] = new_line
            replaced = True
            break

    if not replaced:
        if insert_at is None and in_chunkhound:
            insert_at = len(lines)
        if insert_at is not None:
            lines.insert(insert_at, new_line)
        else:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend(["[chunkhound]", new_line])

    updated = "\n".join(lines)
    if text.endswith("\n") or not updated.endswith("\n"):
        updated += "\n"
    if updated == text:
        return False
    config_path.write_text(updated, encoding="utf-8")
    return True


def _upsert_llm_default_preset(*, config_path: Path, default_preset: str) -> bool:
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        text = ""
    except OSError as exc:
        raise ReviewflowError(f"Failed to read CURe config at {config_path}: {exc}") from exc

    new_line = f"default_preset = {toml_string(default_preset)}"
    if not text.strip():
        config_path.write_text("[llm]\n" + new_line + "\n", encoding="utf-8")
        return True

    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ReviewflowError(f"Failed to parse CURe config at {config_path}: {exc}") from exc

    lines = text.splitlines()
    replaced = False
    in_llm = False
    insert_at: int | None = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[[") and stripped.endswith("]]"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_llm and not replaced:
                insert_at = idx
                break
            in_llm = stripped == "[llm]"
            continue
        if in_llm and stripped.startswith("default_preset"):
            lines[idx] = new_line
            replaced = True
            break

    if not replaced:
        if insert_at is None and in_llm:
            insert_at = len(lines)
        if insert_at is not None:
            lines.insert(insert_at, new_line)
        else:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend(["[llm]", new_line])

    updated = "\n".join(lines)
    if text.endswith("\n") or not updated.endswith("\n"):
        updated += "\n"
    if updated == text:
        return False
    config_path.write_text(updated, encoding="utf-8")
    return True


def _ensure_bootstrap_files(
    *,
    runtime: ReviewflowRuntime,
    force: bool = False,
    stdout: TextIO | None = None,
) -> Path:
    out_stream = stdout or sys.stdout
    config_path = runtime.config_path
    existing_base_path = None if force else _load_existing_chunkhound_base_config_path(config_path)
    chunkhound_base_config_path = existing_base_path or _default_chunkhound_base_config_path(config_path)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    chunkhound_base_config_path.parent.mkdir(parents=True, exist_ok=True)

    config_changed = False
    if force or not _path_has_text(config_path):
        config_path.write_text(
            _render_init_config(
                runtime=runtime,
                chunkhound_base_config_path=chunkhound_base_config_path,
            ),
            encoding="utf-8",
        )
        config_changed = True
        print(f"Wrote CURe config: {config_path}", file=out_stream)
    else:
        config_changed = _upsert_chunkhound_base_config_path(
            config_path=config_path,
            runtime=runtime,
            base_config_path=chunkhound_base_config_path,
        )
        if config_changed:
            print(f"Updated CURe config: {config_path}", file=out_stream)
        else:
            print(f"Left existing CURe config unchanged: {config_path}", file=out_stream)

    if force or not _path_has_text(chunkhound_base_config_path):
        suffix = _write_chunkhound_base_config_file(chunkhound_base_config_path)
        print(f"Wrote ChunkHound base config: {chunkhound_base_config_path}{suffix}", file=out_stream)
    else:
        print(f"Left existing ChunkHound base config unchanged: {chunkhound_base_config_path}", file=out_stream)
    return chunkhound_base_config_path


def _agent_guidance_lines(*, command_name: str) -> list[str]:
    return [
        "Supported local coding agents are `codex` and `claude`, detected from executables on PATH.",
        f"Run `{PRIMARY_CLI_COMMAND} setup --agent codex` or `{PRIMARY_CLI_COMMAND} setup --agent claude` to persist a choice.",
        f"Use `{PRIMARY_CLI_COMMAND} set-agent codex|claude` to change the saved choice later.",
        f"Inspect readiness with `{PRIMARY_CLI_COMMAND} doctor --json` before retrying `{PRIMARY_CLI_COMMAND} {command_name}`.",
    ]


def _prompt_for_agent_choice(
    *,
    installed_agents: list[str],
    default_agent: str | None,
    stdin: TextIO,
    stderr: TextIO,
) -> str:
    choices_display = "/".join(installed_agents)
    default_suffix = f" (default: {default_agent})" if default_agent else ""
    while True:
        raw = _read_wizard_line(
            prompt=f"Select local coding agent [{choices_display}]{default_suffix}: ",
            stdin=stdin,
            stderr=stderr,
        )
        if raw is None:
            raise ReviewflowError("setup wizard input failed.")
        text = str(raw).strip().lower()
        if not text and default_agent:
            return default_agent
        if text in installed_agents:
            return text
        stderr.write("Rejected: choose one of the installed supported agents.\n\n")
        stderr.flush()


def _resolve_bootstrap_agent_choice(
    *,
    runtime: ReviewflowRuntime,
    cli_agent: str | None,
    command_name: str,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    interactive: bool,
) -> dict[str, object]:
    selection = resolve_local_agent_selection(
        base_codex_config_path=runtime.codex_base_config_path,
        reviewflow_config_path=runtime.config_path,
        config_enabled=runtime.config_enabled,
        cli_agent=cli_agent,
        env=os.environ,
    )
    status = str(selection.get("status") or "").strip()
    if status in {"ready", "auto_selectable"}:
        return {
            "agent": selection.get("effective_agent"),
            "persist": (status == "auto_selectable"),
            "detail": selection.get("detail"),
            "selection": selection,
        }
    if interactive:
        in_stream = stdin or sys.stdin
        err_stream = stderr or sys.stderr
        installed_agents = list(selection.get("installed_agents") or [])
        if not installed_agents:
            raise ReviewflowError(
                str(selection.get("detail") or "no supported local coding agent executable is installed on PATH")
            )
        chosen = _prompt_for_agent_choice(
            installed_agents=installed_agents,
            default_agent=str(selection.get("hinted_agent") or "").strip() or None,
            stdin=in_stream,
            stderr=err_stream,
        )
        return {
            "agent": chosen,
            "persist": True,
            "detail": f"selected `{chosen}` during interactive setup",
            "selection": selection,
        }
    detail = str(selection.get("detail") or "local coding agent readiness is blocked")
    raise ReviewflowError("\n".join([detail, *_agent_guidance_lines(command_name=command_name)]))


def _wizard_summary_lines(
    *,
    selected_path: Path,
    selected_agent: str | None,
    will_install: bool,
    install_source: str | None,
) -> list[str]:
    lines = [
        "",
        "Setup summary:",
        f"- ChunkHound base config: {selected_path}",
    ]
    if selected_agent:
        lines.append(f"- Local coding agent: {selected_agent}")
    if will_install:
        lines.append(f"- Run cure install now: yes (source={install_source})")
    else:
        lines.append("- Run cure install now: no")
    return lines


def _read_wizard_line(*, prompt: str, stdin: TextIO, stderr: TextIO) -> str | None:
    try:
        stderr.write(prompt)
        stderr.flush()
        return stdin.readline()
    except Exception:
        return None


def run_chunkhound_setup_wizard(
    *,
    runtime: ReviewflowRuntime,
    cli_agent: str | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> bool:
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout
    err_stream = stderr or sys.stderr
    if not (_stream_is_tty(in_stream) and _stream_is_tty(err_stream)):
        raise ReviewflowError("setup wizard requires a TTY on stdin/stderr.")

    choices, default_index, discovery = _collect_chunkhound_base_config_choices(
        runtime=runtime,
        invocation_cwd=Path.cwd(),
    )
    while True:
        err_stream.write("\nCURe setup wizard\n")
        err_stream.write("Choose the ChunkHound base config source to persist in cure.toml.\n")
        for idx, item in enumerate(choices, start=1):
            marker = " (default)" if idx - 1 == default_index else ""
            err_stream.write(f"{idx}. {item['label']}{marker}\n")
        if str(discovery.get("candidate_state") or "") not in {"candidate", "absent"}:
            reason = str(discovery.get("reason") or "unknown")
            config_hint = str(discovery.get("config_path") or "").strip()
            if config_hint:
                err_stream.write(f"Hint: repo-local ChunkHound candidate was not auto-selectable ({reason}: {config_hint}).\n")
            else:
                err_stream.write(f"Hint: repo-local ChunkHound candidate was not auto-selectable ({reason}).\n")
        raw = _read_wizard_line(
            prompt=f"Select source [default {default_index + 1}; or enter an absolute path]: ",
            stdin=in_stream,
            stderr=err_stream,
        )
        if raw is None:
            raise ReviewflowError("setup wizard input failed.")
        text = str(raw).strip()
        if not text:
            selected = choices[default_index]
        elif text.isdigit() and 1 <= int(text) <= len(choices):
            selected = choices[int(text) - 1]
        else:
            candidate = Path(text).expanduser()
            if not candidate.is_absolute():
                err_stream.write("Rejected: custom path must be absolute.\n\n")
                err_stream.flush()
                continue
            try:
                resolved = _validate_chunkhound_base_config_choice(candidate)
            except ReviewflowError as exc:
                err_stream.write(f"Rejected: {exc}\n\n")
                err_stream.flush()
                continue
            selected = {
                "kind": "custom_absolute",
                "path": str(resolved),
                "label": f"Use custom absolute base config ({resolved})",
            }

        selected_path = Path(selected["path"]).resolve(strict=False)
        agent_choice = _resolve_bootstrap_agent_choice(
            runtime=runtime,
            cli_agent=cli_agent,
            command_name="setup",
            stdin=in_stream,
            stderr=err_stream,
            interactive=True,
        )
        selected_agent = str(agent_choice.get("agent") or "").strip() or None
        chunkhound_missing = shutil.which("chunkhound") is None
        run_install = False
        install_source: str | None = None
        if chunkhound_missing:
            install_raw = _read_wizard_line(
                prompt="ChunkHound is not available on PATH. Run cure install now? [y/N]: ",
                stdin=in_stream,
                stderr=err_stream,
            )
            install_choice = str(install_raw or "").strip().lower()
            run_install = install_choice in {"y", "yes"}
            if run_install:
                source_raw = _read_wizard_line(
                    prompt="Install source [release/git-main] (default: release): ",
                    stdin=in_stream,
                    stderr=err_stream,
                )
                source_text = str(source_raw or "").strip().lower()
                install_source = "git-main" if source_text == "git-main" else "release"

        for line in _wizard_summary_lines(
            selected_path=selected_path,
            selected_agent=selected_agent,
            will_install=run_install,
            install_source=install_source,
        ):
            err_stream.write(line + "\n")
        confirm_raw = _read_wizard_line(
            prompt="Apply this setup? [y/N]: ",
            stdin=in_stream,
            stderr=err_stream,
        )
        if str(confirm_raw or "").strip().lower() not in {"y", "yes"}:
            raise ReviewflowError("Setup canceled.")

        config_changed = _upsert_chunkhound_base_config_path(
            config_path=runtime.config_path,
            runtime=runtime,
            base_config_path=selected_path,
        )
        if config_changed:
            print(f"Updated CURe config: {runtime.config_path}", file=out_stream)
        else:
            print(f"Left existing CURe config unchanged: {runtime.config_path}", file=out_stream)
        if selected_agent:
            preset = LOCAL_AGENT_PRESET_BY_NAME[selected_agent]
            preset_changed = _upsert_llm_default_preset(
                config_path=runtime.config_path,
                default_preset=preset,
            )
            action = "Updated" if preset_changed else "Left unchanged"
            print(
                f"{action} saved local agent preference: {selected_agent} ({preset})",
                file=out_stream,
            )

        if selected["kind"] == "generated_default":
            suffix = _write_chunkhound_base_config_file(selected_path)
            print(f"Wrote ChunkHound base config: {selected_path}{suffix}", file=out_stream)
        if chunkhound_missing and not run_install:
            raise ReviewflowError(
                "ChunkHound CLI is still not available on PATH. "
                f"Run `{PRIMARY_CLI_COMMAND} install` before retrying the original command."
            )
        if run_install:
            assert install_source is not None
            _reviewflow().install_flow(argparse.Namespace(chunkhound_source=install_source))
            if shutil.which("chunkhound") is None:
                raise ReviewflowError(
                    "ChunkHound installation completed but `chunkhound` is still not available on PATH. "
                    f"Retry `{PRIMARY_CLI_COMMAND} install --chunkhound-source {install_source}` after fixing PATH."
                )
        return True


def _bootstrap_gate_problem_lines(*, command_name: str, runtime: ReviewflowRuntime, args: argparse.Namespace) -> list[str]:
    lines = [f"CURe bootstrap is not ready for `{PRIMARY_CLI_COMMAND} {command_name}`."]
    if not runtime.config_enabled:
        lines.append("`--no-config` disables the CURe bootstrap config, so the setup wizard cannot persist a base config.")
    else:
        try:
            chunkhound_cfg, _, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
                config_path=runtime.config_path,
                require=True,
            )
        except ReviewflowError as exc:
            lines.append(str(exc))
        else:
            if not _has_embedding_config(resolved_config=resolved_chunkhound_cfg, env=os.environ):
                lines.append(f"ChunkHound embedding config is missing from {chunkhound_cfg.base_config_path}.")
                lines.append(
                    "Add an `embedding` block, set `CHUNKHOUND_EMBEDDING__API_KEY` / `VOYAGE_API_KEY` / `OPENAI_API_KEY`, or rerun `cure setup`."
                )
    if shutil.which("chunkhound") is None:
        lines.append("ChunkHound CLI is not available on PATH.")
    agent_selection = resolve_local_agent_selection(
        base_codex_config_path=runtime.codex_base_config_path,
        reviewflow_config_path=runtime.config_path,
        config_enabled=runtime.config_enabled,
        cli_preset=getattr(args, "llm_preset", None),
        env=os.environ,
    )
    if bool(agent_selection.get("blocking")):
        lines.append(str(agent_selection.get("detail") or "local coding agent readiness is blocked"))

    discovery = discover_repo_local_chunkhound_config(invocation_cwd=Path.cwd(), pr=None, resolved_runtime_config=None)
    state = str(discovery.get("candidate_state") or "").strip()
    if state == "candidate":
        lines.append(f"Repo-local candidate: {discovery.get('config_path')}")
    elif str(discovery.get("config_path") or "").strip():
        lines.append(
            "Repo-local hint not ready to assume: "
            f"{discovery.get('config_path')} ({discovery.get('reason') or 'unknown'})"
        )

    lines.append(f"Run `{PRIMARY_CLI_COMMAND} setup` in a TTY to configure CURe bootstrap.")
    lines.extend(_agent_guidance_lines(command_name=command_name))
    pr_url = str(getattr(args, "pr_url", "") or "").strip()
    if pr_url:
        lines.append(f"Inspect readiness with `{PRIMARY_CLI_COMMAND} doctor --pr-url {pr_url} --json`.")
    else:
        lines.append(f"Inspect readiness with `{PRIMARY_CLI_COMMAND} doctor --json`.")
    return lines


def ensure_chunkhound_bootstrap_ready(
    args: argparse.Namespace,
    *,
    runtime: ReviewflowRuntime,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> bool:
    command_name = str(getattr(args, "cmd", "") or "").strip()
    gated = {
        "pr",
        "resume",
        "followup",
        "interactive",
    }
    if command_name == "cache" and str(getattr(args, "cache_cmd", "") or "").strip() == "prime":
        gated.add("cache")
    if command_name not in gated:
        return False

    ready = runtime.config_enabled
    embedding_missing = False
    if ready:
        try:
            _, _, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
                config_path=runtime.config_path,
                require=True,
            )
        except ReviewflowError:
            ready = False
        else:
            embedding_missing = not _has_embedding_config(
                resolved_config=resolved_chunkhound_cfg,
                env=os.environ,
            )
            if embedding_missing:
                ready = False
    agent_selection = resolve_local_agent_selection(
        base_codex_config_path=runtime.codex_base_config_path,
        reviewflow_config_path=runtime.config_path,
        config_enabled=runtime.config_enabled,
        cli_preset=getattr(args, "llm_preset", None),
        env=os.environ,
    )
    if ready and shutil.which("chunkhound") is not None and not bool(agent_selection.get("blocking")):
        return False

    in_stream = stdin or sys.stdin
    err_stream = stderr or sys.stderr
    if _stream_is_tty(in_stream) and _stream_is_tty(err_stream) and runtime.config_enabled:
        return run_chunkhound_setup_wizard(
            runtime=runtime,
            cli_agent=getattr(args, "agent", None),
            stdin=in_stream,
            stdout=stdout,
            stderr=err_stream,
        )

    raise ReviewflowError("\n".join(_bootstrap_gate_problem_lines(command_name=command_name, runtime=runtime, args=args)))


def init_flow(
    args: argparse.Namespace,
    *,
    runtime: ReviewflowRuntime,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    if _stream_is_tty(stdin or sys.stdin) and _stream_is_tty(stderr or sys.stderr):
        run_chunkhound_setup_wizard(
            runtime=runtime,
            cli_agent=getattr(args, "agent", None),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
        return 0

    out_stream = stdout or sys.stdout
    _ensure_bootstrap_files(runtime=runtime, force=bool(getattr(args, "force", False)), stdout=out_stream)
    agent_choice = _resolve_bootstrap_agent_choice(
        runtime=runtime,
        cli_agent=getattr(args, "agent", None),
        command_name=str(getattr(args, "cmd", "") or "setup"),
        interactive=False,
    )
    selected_agent = str(agent_choice.get("agent") or "").strip() or None
    if selected_agent:
        preset = LOCAL_AGENT_PRESET_BY_NAME[selected_agent]
        changed = _upsert_llm_default_preset(config_path=runtime.config_path, default_preset=preset)
        action = "Updated" if changed else "Left unchanged"
        print(f"{action} saved local agent preference: {selected_agent} ({preset})", file=out_stream)
    print(f"Next: {PRIMARY_CLI_COMMAND} install", file=out_stream)
    return 0


def setup_flow(
    args: argparse.Namespace,
    *,
    runtime: ReviewflowRuntime,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    return init_flow(args, runtime=runtime, stdin=stdin, stdout=stdout, stderr=stderr)


def set_agent_flow(
    args: argparse.Namespace,
    *,
    runtime: ReviewflowRuntime,
    stdout: TextIO | None = None,
) -> int:
    out_stream = stdout or sys.stdout
    _ensure_bootstrap_files(runtime=runtime, stdout=out_stream)
    selected_agent = str(getattr(args, "agent", "") or "").strip().lower()
    choice = _resolve_bootstrap_agent_choice(
        runtime=runtime,
        cli_agent=selected_agent,
        command_name="set-agent",
        interactive=False,
    )
    resolved_agent = str(choice.get("agent") or "").strip()
    preset = LOCAL_AGENT_PRESET_BY_NAME[resolved_agent]
    changed = _upsert_llm_default_preset(config_path=runtime.config_path, default_preset=preset)
    action = "Updated" if changed else "Left unchanged"
    print(f"{action} saved local agent preference: {resolved_agent} ({preset})", file=out_stream)
    return 0


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


def doctor_flow(args: argparse.Namespace, *, runtime: ReviewflowRuntime) -> int:
    pr_url = str(getattr(args, "pr_url", "") or "").strip() or None
    checks = _doctor_runtime_checks(
        runtime,
        cli_profile=getattr(args, "agent_runtime_profile", None),
        pr_url=pr_url,
        args=args,
    )
    if bool(getattr(args, "json_output", False)):
        ok_count = sum(1 for item in checks if item.status == "ok")
        warn_count = sum(1 for item in checks if item.status == "warn")
        fail_count = sum(1 for item in checks if item.status == "fail")
        payload = _doctor_runtime_payload(
            runtime,
            cli_profile=getattr(args, "agent_runtime_profile", None),
            pr_url=pr_url,
            args=args,
        )
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
    "init_flow",
    "interactive_flow",
    "pr_flow",
    "preferred_cli_invocation",
    "resume_flow",
    "set_agent_flow",
    "setup_flow",
    "status_flow",
    "watch_flow",
    "zip_flow",
]
