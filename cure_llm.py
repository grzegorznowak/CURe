from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import shlex
import shutil
import urllib.error
import urllib.request
from typing import Any

from cure_errors import ReviewflowError
from cure_flows import chunkhound_env, ensure_review_config, materialize_chunkhound_env_config
from cure_output import (
    CodexJsonEventSink,
    _shell_join,
    active_output,
    normalize_markdown_artifact,
    safe_cmd_for_meta,
)
from cure_runtime import (
    CLI_LLM_PROVIDERS,
    HTTP_LLM_PROVIDERS,
    _dedupe_paths,
    _string_dict,
    augment_cli_provider_session_env,
    build_curated_subprocess_env,
    build_http_response_request,
    load_chunkhound_runtime_config,
    resolve_agent_runtime_profile,
    resolve_llm_config,
    toml_string,
)
from cure_sessions import resolve_meta_llm
from meta import write_json, write_redacted_json
from paths import (
    ReviewflowPaths,
    default_codex_base_config_path,
    real_user_home_dir,
)
from run import ReviewflowSubprocessError, run_cmd
from ui import TailBuffer


def _reviewflow():
    import cure as rf

    return rf


def _prepare_gemini_cli_home(*, work_dir: Path) -> tuple[Path, Path]:
    return _reviewflow()._prepare_gemini_cli_home(work_dir=work_dir)


def prepare_gh_config_for_codex(*, dst_root: Path) -> Path | None:
    return _reviewflow().prepare_gh_config_for_codex(dst_root=dst_root)


def prepare_jira_config_for_codex(*, dst_root: Path) -> Path | None:
    return _reviewflow().prepare_jira_config_for_codex(dst_root=dst_root)


def prepare_netrc_for_reviewflow(*, dst_root: Path) -> Path | None:
    return _reviewflow().prepare_netrc_for_reviewflow(dst_root=dst_root)


def write_rf_jira(*, repo_dir: Path) -> Path:
    return _reviewflow().write_rf_jira(repo_dir=repo_dir)


@dataclass(frozen=True)
class LlmResumeInfo:
    provider: str
    session_id: str
    cwd: Path
    command: str


@dataclass(frozen=True)
class LlmRunResult:
    resume: LlmResumeInfo | None = None
    adapter_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CodexResumeInfo:
    session_id: str
    cwd: Path
    command: str


@dataclass(frozen=True)
class CodexRunResult:
    resume: CodexResumeInfo | None = None
    events_log_path: Path | None = None
    events_start_offset: int | None = None
    events_end_offset: int | None = None


_LIVE_PROGRESS_TIMELINE_MAX = 8
_CURE_CHUNKHOUND_HELPER_ENV = "CURE_CHUNKHOUND_HELPER"
_CURE_CHUNKHOUND_ACCESS_MODE = "cli_helper_daemon"


def _looks_like_codex_review_artifact(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    markers = (
        "### Steps taken",
        "**Summary**:",
        "## Business / Product Assessment",
        "## Technical Assessment",
        "**Verdict**:",
    )
    if any(marker in value for marker in markers):
        return True
    return len(value) >= 800 and ("\n# " in ("\n" + value) or "\n- " in ("\n" + value))


def _write_text_artifact(path: Path, text: str) -> None:
    body = str(text or "").rstrip("\n")
    if not body:
        return
    path.write_text(body + "\n", encoding="utf-8")


def _progress_meta_dict(progress: Any) -> dict[str, Any] | None:
    meta = getattr(progress, "meta", None)
    return meta if isinstance(meta, dict) else None


def _flush_progress(progress: Any) -> None:
    flush = getattr(progress, "flush", None)
    if callable(flush):
        try:
            flush()
        except Exception:
            pass


def _resolve_codex_events_log_path(*, progress: Any, repo_dir: Path) -> Path:
    meta = _progress_meta_dict(progress)
    logs = (meta.get("logs") if isinstance(meta, dict) and isinstance(meta.get("logs"), dict) else {})
    raw_path = str(logs.get("codex_events") or "").strip()
    if raw_path:
        path = Path(raw_path)
        return ((repo_dir.parent / path).resolve() if not path.is_absolute() else path.resolve())
    path = (repo_dir.parent / "work" / "logs" / "codex.events.jsonl").resolve()
    if isinstance(meta, dict):
        meta.setdefault("logs", {})["codex_events"] = str(path)
        _flush_progress(progress)
    return path


def _resolve_codex_display_log_path(*, progress: Any, repo_dir: Path) -> Path:
    meta = _progress_meta_dict(progress)
    logs = (meta.get("logs") if isinstance(meta, dict) and isinstance(meta.get("logs"), dict) else {})
    raw_path = str(logs.get("codex") or "").strip()
    if raw_path:
        path = Path(raw_path)
        return ((repo_dir.parent / path).resolve() if not path.is_absolute() else path.resolve())
    path = (repo_dir.parent / "work" / "logs" / "codex.log").resolve()
    if isinstance(meta, dict):
        meta.setdefault("logs", {})["codex"] = str(path)
        _flush_progress(progress)
    return path


def _path_size(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return int(path.stat().st_size)
    except OSError:
        return None


def _ensure_codex_live_progress(*, progress: Any, events_log_path: Path) -> None:
    meta = _progress_meta_dict(progress)
    if meta is None:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    live = meta.get("live_progress") if isinstance(meta.get("live_progress"), dict) else {}
    live["source"] = "codex_exec_json"
    live["provider"] = "codex"
    live["status"] = "running"
    live["events_log"] = str(events_log_path)
    live["updated_at"] = now
    live["timeline"] = list(live.get("timeline")) if isinstance(live.get("timeline"), list) else []
    meta["live_progress"] = live
    _flush_progress(progress)


def _record_codex_live_event(*, progress: Any, event: dict[str, Any]) -> None:
    meta = _progress_meta_dict(progress)
    if meta is None:
        return
    text = str(event.get("text") or "").strip()
    event_type = str(event.get("type") or "").strip() or "event"
    timestamp = str(event.get("ts") or "").strip() or datetime.now(timezone.utc).isoformat(timespec="seconds")
    live = meta.get("live_progress") if isinstance(meta.get("live_progress"), dict) else {}
    live["source"] = "codex_exec_json"
    live["provider"] = "codex"
    live["status"] = "running"
    live["updated_at"] = timestamp
    timeline = list(live.get("timeline")) if isinstance(live.get("timeline"), list) else []
    if text:
        normalized = {"ts": timestamp, "type": event_type, "text": text}
        last = timeline[-1] if timeline and isinstance(timeline[-1], dict) else {}
        if last.get("type") != event_type or last.get("text") != text:
            timeline.append(normalized)
        if len(timeline) > _LIVE_PROGRESS_TIMELINE_MAX:
            timeline = timeline[-_LIVE_PROGRESS_TIMELINE_MAX:]
        live["timeline"] = timeline
        current = live.get("current") if isinstance(live.get("current"), dict) else {}
        if event_type == "agent_message":
            live["last_agent_message"] = text
            live["current"] = normalized
        elif bool(event.get("replace_current")) or (not str(current.get("text") or "").strip()):
            live["current"] = normalized
    meta["live_progress"] = live
    _flush_progress(progress)


def _finalize_codex_live_progress(*, progress: Any, status: str) -> None:
    meta = _progress_meta_dict(progress)
    if meta is None:
        return
    live = meta.get("live_progress")
    if not isinstance(live, dict):
        return
    live["status"] = str(status or "done")
    live["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta["live_progress"] = live
    _flush_progress(progress)


def build_codex_exec_cmd(
    *,
    repo_dir: Path,
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    review_md_path: Path,
    prompt: str,
    add_dirs: list[Path] | None = None,
    skip_git_repo_check: bool = False,
    approval_policy: str = "never",
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
    json_output: bool = False,
) -> list[str]:
    overrides = list(codex_config_overrides or [])
    has_explicit_approval_flag = any(flag in {"-a", "--ask-for-approval"} for flag in codex_flags)
    cmd = ["codex", "-C", str(repo_dir), "--add-dir", "/tmp"]
    for add_dir in add_dirs or []:
        cmd.extend(["--add-dir", str(add_dir)])
    cmd.extend(codex_flags)
    if approval_policy and (not dangerously_bypass_approvals_and_sandbox) and (not has_explicit_approval_flag):
        cmd.extend(["-a", approval_policy])
    for override in overrides:
        cmd.extend(["-c", override])
    if include_shell_environment_inherit_all:
        cmd.extend(["-c", "shell_environment_policy.inherit=all"])
    cmd.append("exec")
    if dangerously_bypass_approvals_and_sandbox:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    if skip_git_repo_check:
        cmd.append("--skip-git-repo-check")
    if json_output:
        cmd.append("--json")
    cmd.extend(["--output-last-message", str(review_md_path), "--", prompt])
    return cmd


def run_codex_exec(
    *,
    repo_dir: Path,
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    stream: bool,
    progress: "SessionProgress",
    add_dirs: list[Path] | None = None,
    stream_label: str = "codex",
    approval_policy: str = "never",
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
) -> CodexRunResult:
    started_at = datetime.now(timezone.utc)
    out = active_output()
    codex_events_log_path = _resolve_codex_events_log_path(progress=progress, repo_dir=repo_dir)
    codex_display_log_path = _resolve_codex_display_log_path(progress=progress, repo_dir=repo_dir)
    events_start_offset = _path_size(codex_events_log_path)
    artifact_override: dict[str, str | None] = {"text": None}
    _ensure_codex_live_progress(progress=progress, events_log_path=codex_events_log_path)

    def _handle_codex_event(event: dict[str, Any]) -> None:
        _record_codex_live_event(progress=progress, event=event)
        artifact_text = str(event.get("raw_text") or event.get("text") or "").strip()
        if str(event.get("type") or "").strip() == "agent_message" and _looks_like_codex_review_artifact(
            artifact_text
        ):
            artifact_override["text"] = artifact_text

    cmd = build_codex_exec_cmd(
        repo_dir=repo_dir,
        codex_flags=codex_flags,
        codex_config_overrides=codex_config_overrides,
        review_md_path=output_path,
        prompt=prompt,
        add_dirs=add_dirs,
        skip_git_repo_check=False,
        approval_policy=approval_policy,
        dangerously_bypass_approvals_and_sandbox=dangerously_bypass_approvals_and_sandbox,
        include_shell_environment_inherit_all=include_shell_environment_inherit_all,
        json_output=True,
    )
    progress.record_cmd(cmd)
    try:
        if out is not None:
            out.run_logged_cmd(
                cmd,
                kind="codex",
                cwd=repo_dir,
                env=env,
                check=True,
                stream_requested=True,
                codex_json_events_path=codex_events_log_path,
                codex_event_callback=_handle_codex_event,
            )
        else:
            codex_events_log_path.parent.mkdir(parents=True, exist_ok=True)
            codex_display_log_path.parent.mkdir(parents=True, exist_ok=True)
            with codex_events_log_path.open("a", encoding="utf-8", buffering=1) as raw_fh, codex_display_log_path.open(
                "a", encoding="utf-8", buffering=1
            ) as display_fh:
                sink = CodexJsonEventSink(
                    raw_file=raw_fh,
                    display_file=display_fh,
                    tail=TailBuffer(max_lines=400),
                    also_to=None,
                    on_event=_handle_codex_event,
                )
                run_cmd(
                    cmd,
                    cwd=repo_dir,
                    env=env,
                    check=True,
                    stream=True,
                    stream_to=sink,
                    stream_label=None,
                )
        if artifact_override["text"]:
            _write_text_artifact(output_path, str(artifact_override["text"]))
        normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
        _finalize_codex_live_progress(progress=progress, status="done")
        events_end_offset = _path_size(codex_events_log_path)
        return CodexRunResult(
            resume=find_codex_resume_info(
                repo_dir=repo_dir,
                started_at=started_at,
                env=env,
                codex_flags=codex_flags,
                codex_config_overrides=codex_config_overrides,
                add_dirs=add_dirs,
            ),
            events_log_path=codex_events_log_path,
            events_start_offset=events_start_offset,
            events_end_offset=events_end_offset,
        )
    except ReviewflowSubprocessError as e:
        msg = (e.stderr or "") + "\n" + (e.stdout or "")
        if "skip-git-repo-check" not in msg and "trusted directory" not in msg:
            _finalize_codex_live_progress(progress=progress, status="error")
            raise
        _record_codex_live_event(
            progress=progress,
            event={
                "type": "agent_message",
                "text": "Retrying review with --skip-git-repo-check.",
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "replace_current": True,
            },
        )
        fallback = build_codex_exec_cmd(
            repo_dir=repo_dir,
            codex_flags=codex_flags,
            codex_config_overrides=codex_config_overrides,
            review_md_path=output_path,
            prompt=prompt,
            add_dirs=add_dirs,
            skip_git_repo_check=True,
            approval_policy=approval_policy,
            dangerously_bypass_approvals_and_sandbox=dangerously_bypass_approvals_and_sandbox,
            include_shell_environment_inherit_all=include_shell_environment_inherit_all,
            json_output=True,
        )
        progress.record_cmd(fallback)
        out = active_output()
        try:
            if out is not None:
                out.run_logged_cmd(
                    fallback,
                    kind="codex",
                    cwd=repo_dir,
                    env=env,
                    check=True,
                    stream_requested=True,
                    codex_json_events_path=codex_events_log_path,
                    codex_event_callback=_handle_codex_event,
                )
            else:
                codex_events_log_path.parent.mkdir(parents=True, exist_ok=True)
                codex_display_log_path.parent.mkdir(parents=True, exist_ok=True)
                with codex_events_log_path.open("a", encoding="utf-8", buffering=1) as raw_fh, codex_display_log_path.open(
                    "a", encoding="utf-8", buffering=1
                ) as display_fh:
                    sink = CodexJsonEventSink(
                        raw_file=raw_fh,
                        display_file=display_fh,
                        tail=TailBuffer(max_lines=400),
                        also_to=None,
                        on_event=_handle_codex_event,
                    )
                    run_cmd(
                        fallback,
                        cwd=repo_dir,
                        env=env,
                        check=True,
                        stream=True,
                        stream_to=sink,
                        stream_label=None,
                    )
        except ReviewflowSubprocessError:
            _finalize_codex_live_progress(progress=progress, status="error")
            raise
        if artifact_override["text"]:
            _write_text_artifact(output_path, str(artifact_override["text"]))
        normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
        _finalize_codex_live_progress(progress=progress, status="done")
        events_end_offset = _path_size(codex_events_log_path)
        return CodexRunResult(
            resume=find_codex_resume_info(
                repo_dir=repo_dir,
                started_at=started_at,
                env=env,
                codex_flags=codex_flags,
                codex_config_overrides=codex_config_overrides,
                add_dirs=add_dirs,
            ),
            events_log_path=codex_events_log_path,
            events_start_offset=events_start_offset,
            events_end_offset=events_end_offset,
        )


def build_codex_flags_from_llm_config(
    *, resolved: dict[str, Any], resolution_meta: dict[str, Any], include_sandbox: bool = True
) -> tuple[list[str], dict[str, Any]]:
    base_meta = resolution_meta.get("base_codex_config")
    base_meta = base_meta if isinstance(base_meta, dict) else {}
    reviewflow_defaults = resolution_meta.get("reviewflow_defaults")
    if not isinstance(reviewflow_defaults, dict):
        legacy_defaults = resolution_meta.get("legacy_codex_defaults")
        reviewflow_defaults = dict(legacy_defaults) if isinstance(legacy_defaults, dict) else {}
    flags: list[str] = []
    model = str(resolved.get("model") or "").strip()
    if model:
        flags.extend(["-m", model])
    sandbox_mode = str(base_meta.get("sandbox_mode") or "").strip()
    if include_sandbox and sandbox_mode in {"read-only", "workspace-write", "danger-full-access"}:
        flags.extend(["--sandbox", sandbox_mode])
    if str(base_meta.get("web_search") or "").strip() == "live":
        flags.append("--search")
    reasoning_effort = str(resolved.get("reasoning_effort") or "").strip()
    if reasoning_effort:
        flags.extend(["-c", f"model_reasoning_effort={toml_string(reasoning_effort)}"])
    plan_reasoning_effort = str(resolved.get("plan_reasoning_effort") or "").strip()
    if plan_reasoning_effort:
        flags.extend(["-c", f"plan_mode_reasoning_effort={toml_string(plan_reasoning_effort)}"])
    meta = {
        "base": base_meta,
        "reviewflow_defaults": reviewflow_defaults,
        "resolved": {
            "model": resolved.get("model"),
            "model_source": ((resolution_meta.get("resolved") or {}).get("model_source")),
            "model_reasoning_effort": resolved.get("reasoning_effort"),
            "model_reasoning_effort_source": (
                (resolution_meta.get("resolved") or {}).get("reasoning_effort_source")
            ),
            "plan_mode_reasoning_effort": resolved.get("plan_reasoning_effort"),
            "plan_mode_reasoning_effort_source": (
                (resolution_meta.get("resolved") or {}).get("plan_reasoning_effort_source")
            ),
            "sandbox_mode": base_meta.get("sandbox_mode"),
            "web_search": base_meta.get("web_search"),
            "preset": resolved.get("preset"),
        },
        "flags": list(flags),
    }
    return flags, meta


def _build_env_prefix_assignments(env: dict[str, str], keys: tuple[str, ...]) -> str:
    assignments: list[str] = []
    for key in keys:
        value = str(env.get(key) or "").strip()
        if value:
            assignments.append(f"{key}={shlex.quote(value)}")
    if not assignments:
        return ""
    return "env " + " ".join(assignments) + " "


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    candidates.extend(line.strip() for line in raw.splitlines() if line.strip())
    for candidate in reversed(candidates):
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return None


def _extract_http_response_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    outputs = payload.get("output")
    if not isinstance(outputs, list):
        raise ReviewflowError("HTTP response payload did not contain output text.")
    chunks: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "").strip().lower()
            if part_type in {"output_text", "text"}:
                text = str(part.get("text") or "").strip()
                if text:
                    chunks.append(text)
    if not chunks:
        raise ReviewflowError("HTTP response payload did not contain output text.")
    return "\n\n".join(chunks)


def _run_logged_text_command(*, cmd: list[str], cwd: Path, env: dict[str, str]):
    out = active_output()
    if out is not None:
        return out.run_logged_cmd(
            cmd,
            kind="codex",
            cwd=cwd,
            env=env,
            check=True,
            stream_requested=False,
        )
    return run_cmd(cmd, cwd=cwd, env=env, check=True, stream=False, stream_label="codex")


def build_claude_exec_cmd(
    *,
    command: str,
    model: str | None,
    prompt: str,
    runtime_policy: dict[str, Any] | None = None,
) -> list[str]:
    cmd = [command, "--print", "--output-format", "json"]
    policy = runtime_policy if isinstance(runtime_policy, dict) else {}
    provider_args = policy.get("provider_args")
    if isinstance(provider_args, list):
        cmd.extend([str(item) for item in provider_args])
    elif not policy:
        cmd.append("--dangerously-skip-permissions")
    if bool(policy.get("dangerously_skip_permissions")):
        cmd.append("--dangerously-skip-permissions")
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)
    return cmd


def build_claude_resume_command(
    *,
    repo_dir: Path,
    session_id: str,
    env: dict[str, str],
    command: str,
    runtime_policy: dict[str, Any] | None = None,
) -> str:
    env_prefix = _build_env_prefix_assignments(
        env,
        ("ANTHROPIC_API_KEY", "GH_CONFIG_DIR", "JIRA_CONFIG_FILE", "NETRC", "CURE_WORK_DIR"),
    )
    policy = runtime_policy if isinstance(runtime_policy, dict) else {}
    resume_cmd = [command]
    provider_args = policy.get("provider_args")
    if isinstance(provider_args, list):
        resume_cmd.extend([str(item) for item in provider_args])
    elif not policy:
        resume_cmd.append("--dangerously-skip-permissions")
    if bool(policy.get("dangerously_skip_permissions")):
        resume_cmd.append("--dangerously-skip-permissions")
    resume_cmd.extend(["--resume", session_id])
    return f"cd {shlex.quote(str(repo_dir))} && {env_prefix}{_shell_join(resume_cmd)}"


def run_claude_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    progress: "SessionProgress",
    runtime_policy: dict[str, Any] | None = None,
) -> LlmRunResult:
    cmd = build_claude_exec_cmd(
        command=str(resolved.get("command") or "claude"),
        model=str(resolved.get("model") or "").strip() or None,
        prompt=prompt,
        runtime_policy=runtime_policy,
    )
    progress.record_cmd(cmd)
    result = _run_logged_text_command(cmd=cmd, cwd=repo_dir, env=env)
    payload = _extract_json_object(result.stdout) or {}
    text = str(payload.get("result") or result.stdout or "").strip()
    if not text:
        raise ReviewflowError("Claude did not return any printable review output.")
    output_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
    session_id = str(payload.get("session_id") or "").strip()
    resume = None
    if session_id:
        resume = LlmResumeInfo(
            provider="claude",
            session_id=session_id,
            cwd=repo_dir.resolve(),
            command=build_claude_resume_command(
                repo_dir=repo_dir.resolve(),
                session_id=session_id,
                env=env,
                command=str(resolved.get("command") or "claude"),
                runtime_policy=runtime_policy,
            ),
        )
    return LlmRunResult(resume=resume, adapter_meta={"transport": "cli-claude", "command": safe_cmd_for_meta(cmd)})


def build_gemini_exec_cmd(
    *,
    command: str,
    model: str | None,
    prompt: str,
    runtime_policy: dict[str, Any] | None = None,
) -> list[str]:
    cmd = [command]
    policy = runtime_policy if isinstance(runtime_policy, dict) else {}
    provider_args = policy.get("provider_args")
    if isinstance(provider_args, list):
        cmd.extend([str(item) for item in provider_args])
    if model:
        cmd.extend(["-m", model])
    cmd.extend(["-p", prompt])
    return cmd


def run_gemini_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    progress: "SessionProgress",
    runtime_policy: dict[str, Any] | None = None,
) -> LlmRunResult:
    cmd = build_gemini_exec_cmd(
        command=str(resolved.get("command") or "gemini"),
        model=str(resolved.get("model") or "").strip() or None,
        prompt=prompt,
        runtime_policy=runtime_policy,
    )
    progress.record_cmd(cmd)
    result = _run_logged_text_command(cmd=cmd, cwd=repo_dir, env=env)
    payload = _extract_json_object(result.stdout)
    text = str((payload or {}).get("response") or result.stdout or "").strip()
    if not text:
        raise ReviewflowError("Gemini did not return any printable review output.")
    output_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
    return LlmRunResult(resume=None, adapter_meta={"transport": "cli-gemini", "command": safe_cmd_for_meta(cmd)})


def run_http_response_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    output_path: Path,
    prompt: str,
    progress: "SessionProgress",
) -> LlmRunResult:
    request_meta = build_http_response_request(resolved, prompt=prompt)
    cmd_meta = ["http-responses", str(resolved.get("provider") or "?"), str(request_meta["url"])]
    progress.record_cmd(cmd_meta)
    payload_bytes = json.dumps(request_meta["json"]).encode("utf-8")
    req = urllib.request.Request(
        str(request_meta["url"]),
        data=payload_bytes,
        headers=request_meta["headers"],
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status_code = int(getattr(resp, "status", 200))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ReviewflowSubprocessError(cmd=cmd_meta, cwd=repo_dir, exit_code=int(getattr(e, "code", 1) or 1), stdout="", stderr=body) from e
    except urllib.error.URLError as e:
        raise ReviewflowSubprocessError(cmd=cmd_meta, cwd=repo_dir, exit_code=1, stdout="", stderr=str(e)) from e

    out = active_output()
    if out is not None:
        try:
            out.stream_sink("codex").write(body)
        except Exception:
            pass

    payload = _extract_json_object(body)
    if payload is None:
        raise ReviewflowError("HTTP llm provider returned non-JSON output.")
    text = _extract_http_response_output_text(payload)
    output_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
    return LlmRunResult(
        resume=None,
        adapter_meta={
            "transport": "http-responses",
            "status_code": status_code,
            "url": request_meta["url"],
            "response_id": str(payload.get("id") or "").strip() or None,
        },
    )


def run_llm_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    resolution_meta: dict[str, Any],
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    stream: bool,
    progress: "SessionProgress",
    add_dirs: list[Path] | None = None,
    codex_config_overrides: list[str] | None = None,
    runtime_policy: dict[str, Any] | None = None,
) -> LlmRunResult:
    rf = _reviewflow()
    provider = str(resolved.get("provider") or "").strip().lower()
    if provider == "codex":
        codex_flags, _ = rf.build_codex_flags_from_llm_config(
            resolved=resolved,
            resolution_meta=resolution_meta,
        )
        policy = runtime_policy if isinstance(runtime_policy, dict) else {}
        codex_flags = list(policy.get("codex_flags") or codex_flags)
        codex_config_overrides = list(policy.get("codex_config_overrides") or codex_config_overrides or [])
        result = rf.run_codex_exec(
            repo_dir=repo_dir,
            codex_flags=codex_flags,
            codex_config_overrides=codex_config_overrides,
            output_path=output_path,
            prompt=prompt,
            env=env,
            stream=stream,
            progress=progress,
            add_dirs=list(policy.get("add_dirs") or add_dirs or []),
            approval_policy=str(policy.get("approval_policy") or "never"),
            dangerously_bypass_approvals_and_sandbox=bool(policy.get("dangerously_bypass_approvals_and_sandbox", True)),
            include_shell_environment_inherit_all=bool(policy.get("include_shell_environment_inherit_all", False)),
        )
        resume = None
        if result.resume is not None:
            resume = LlmResumeInfo(
                provider="codex",
                session_id=result.resume.session_id,
                cwd=result.resume.cwd,
                command=result.resume.command,
            )
        return LlmRunResult(
            resume=resume,
            adapter_meta={
                "transport": "cli-codex",
                "flags": codex_flags,
                "codex_events_path": str(result.events_log_path) if result.events_log_path is not None else None,
                "codex_events_start_offset": result.events_start_offset,
                "codex_events_end_offset": result.events_end_offset,
            },
        )
    if provider == "claude":
        return rf.run_claude_exec(
            repo_dir=repo_dir,
            resolved=resolved,
            output_path=output_path,
            prompt=prompt,
            env=env,
            progress=progress,
            runtime_policy=runtime_policy,
        )
    if provider == "gemini":
        return rf.run_gemini_exec(
            repo_dir=repo_dir,
            resolved=resolved,
            output_path=output_path,
            prompt=prompt,
            env=env,
            progress=progress,
            runtime_policy=runtime_policy,
        )
    if provider in HTTP_LLM_PROVIDERS:
        return rf.run_http_response_exec(
            repo_dir=repo_dir,
            resolved=resolved,
            output_path=output_path,
            prompt=prompt,
            progress=progress,
        )
    raise ReviewflowError(f"Unsupported llm provider: {provider!r}")


def codex_mcp_overrides_for_reviewflow(
    *,
    enable_sandbox_chunkhound: bool,
    sandbox_repo_dir: Path,
    chunkhound_db_path: Path | None = None,
    chunkhound_cwd: Path | None = None,
    chunkhound_config_path: Path | None = None,
    paths: ReviewflowPaths,
) -> list[str]:
    _ = paths
    overrides: list[str] = []
    overrides.append(f"mcp_servers.chunk-hound.command={toml_string('chunkhound')}")
    overrides.append(f"mcp_servers.chunk-hound.args={json.dumps(['mcp', str(sandbox_repo_dir)])}")
    overrides.append("mcp_servers.chunk-hound.enabled=false")
    overrides.append("mcp_servers.chunk-hound.tool_timeout_sec=12000")
    _ = enable_sandbox_chunkhound, chunkhound_db_path, chunkhound_cwd, chunkhound_config_path
    return overrides


def _require_provider_command(command: str, *, provider: str) -> str:
    name = str(command or provider).strip() or provider
    if shutil.which(name) is None:
        raise ReviewflowError(
            f"Required {provider} command not found on PATH: {name}. "
            "Install the provider CLI or choose a different llm preset."
        )
    return name


def _stage_review_auth_support(*, work_dir: Path, repo_dir: Path, env: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    staged_paths: dict[str, str] = {}
    gh_cfg = prepare_gh_config_for_codex(dst_root=work_dir)
    if gh_cfg:
        env["GH_CONFIG_DIR"] = str(gh_cfg)
        staged_paths["gh_config_dir"] = str(gh_cfg)
    jira_cfg = prepare_jira_config_for_codex(dst_root=work_dir)
    if jira_cfg:
        env["JIRA_CONFIG_FILE"] = str(jira_cfg)
        staged_paths["jira_config_file"] = str(jira_cfg)
    netrc = prepare_netrc_for_reviewflow(dst_root=work_dir)
    if netrc:
        env["NETRC"] = str(netrc)
        staged_paths["netrc"] = str(netrc)
    env["CURE_WORK_DIR"] = str(work_dir)
    staged_paths["cure_work_dir"] = str(work_dir)
    rf_jira = write_rf_jira(repo_dir=repo_dir)
    staged_paths["rf_jira"] = str(rf_jira)
    return env, staged_paths


def write_chunkhound_helper(
    *,
    work_dir: Path,
    repo_dir: Path,
    chunkhound_config_path: Path | None,
    chunkhound_db_path: Path | None,
    chunkhound_cwd: Path | None,
) -> Path:
    repo_root = repo_dir.resolve(strict=False)
    helper_cwd = (chunkhound_cwd or repo_root).resolve(strict=False)
    helper_cfg = (chunkhound_config_path or (helper_cwd / "chunkhound.json")).resolve(strict=False)
    helper_db = (chunkhound_db_path or (repo_root / ".chunkhound.db")).resolve(strict=False)
    helper_path = (work_dir / "bin" / "cure-chunkhound").resolve(strict=False)
    helper_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_DIR = Path({json.dumps(str(repo_root))})
CHUNKHOUND_CWD = Path({json.dumps(str(helper_cwd))})
CHUNKHOUND_CONFIG = Path({json.dumps(str(helper_cfg))})
CHUNKHOUND_DB = Path({json.dumps(str(helper_db))})
HELPER_PATH = Path(__file__).resolve()
DAEMON_LOCK_PATH = (REPO_DIR / ".chunkhound" / "daemon.lock").resolve()
DAEMON_LOG_PATH = (REPO_DIR / ".chunkhound" / "daemon.log").resolve()


def _emit(payload: dict[str, Any], *, exit_code: int) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\\n")
    sys.stdout.flush()
    return exit_code


def _read_lock() -> dict[str, Any]:
    try:
        raw = json.loads(DAEMON_LOCK_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {{}}
    except Exception:
        return {{}}


def _base_cmd() -> list[str]:
    return ["chunkhound", "mcp", "--config", str(CHUNKHOUND_CONFIG), str(REPO_DIR)]


class JsonRpcSession:
    def __init__(self) -> None:
        self._next_id = 1
        self.proc = subprocess.Popen(
            _base_cmd(),
            cwd=str(CHUNKHOUND_CWD),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        if self.proc.stdin is None or self.proc.stdout is None or self.proc.stderr is None:
            raise RuntimeError("chunkhound mcp stdio pipes are unavailable")

    def close(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _read_message(self) -> dict[str, Any]:
        headers: dict[str, str] = {{}}
        while True:
            line = self.proc.stdout.readline()
            if line == b"":
                stderr_text = b""
                try:
                    stderr_text = self.proc.stderr.read() or b""
                except Exception:
                    pass
                detail = stderr_text.decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or "chunkhound mcp closed its stdio stream")
            if line in {{b"\\r\\n", b"\\n"}}:
                break
            key, _, value = line.decode("utf-8", errors="replace").partition(":")
            headers[key.strip().lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except Exception as exc:
            raise RuntimeError("invalid MCP content-length header") from exc
        body = self.proc.stdout.read(length)
        if len(body) != length:
            raise RuntimeError("incomplete MCP message body")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected MCP payload type")
        return payload

    def _write_message(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        message = f"Content-Length: {{len(raw)}}\\r\\n\\r\\n".encode("utf-8") + raw
        self.proc.stdin.write(message)
        self.proc.stdin.flush()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {{"jsonrpc": "2.0", "id": request_id, "method": method}}
        if params is not None:
            payload["params"] = params
        self._write_message(payload)
        while True:
            message = self._read_message()
            if message.get("id") == request_id:
                return message

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {{"jsonrpc": "2.0", "method": method}}
        if params is not None:
            payload["params"] = params
        self._write_message(payload)


def _extract_result_content(response: dict[str, Any]) -> Any:
    if "error" in response:
        error = response.get("error")
        raise RuntimeError(json.dumps(error, sort_keys=True))
    result = response.get("result")
    if not isinstance(result, dict):
        return result
    if bool(result.get("isError")):
        raise RuntimeError(json.dumps(result, sort_keys=True))
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0] if isinstance(content[0], dict) else {{}}
        text = str(first.get("text") or "")
        stripped = text.strip()
        if stripped:
            try:
                return json.loads(stripped)
            except Exception:
                return stripped
    return result


def _tool_payload(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.command == "search":
        payload: dict[str, Any] = {{
            "query": args.query,
            "type": args.type,
            "page_size": args.page_size,
            "offset": args.offset,
        }}
        if args.path:
            payload["path"] = args.path
        return "search", payload
    payload = {{"query": args.query}}
    if args.path:
        payload["path"] = args.path
    return "code_research", payload


def _run_preflight(session: JsonRpcSession, args: argparse.Namespace) -> dict[str, Any]:
    init_response = session.request(
        "initialize",
        {{
            "protocolVersion": "2025-03-26",
            "capabilities": {{}},
            "clientInfo": {{"name": "cure-chunkhound-helper", "version": "1"}},
        }},
    )
    if "error" in init_response:
        raise RuntimeError(json.dumps(init_response["error"], sort_keys=True))
    session.notify("notifications/initialized", {{}})
    tools_response = session.request("tools/list", {{}})
    if "error" in tools_response:
        raise RuntimeError(json.dumps(tools_response["error"], sort_keys=True))
    tools_payload = tools_response.get("result") if isinstance(tools_response.get("result"), dict) else {{}}
    tools = tools_payload.get("tools") if isinstance(tools_payload, dict) else []
    available = sorted(
        str(tool.get("name") or "").strip()
        for tool in tools
        if isinstance(tool, dict) and str(tool.get("name") or "").strip()
    )
    lock_payload = _read_lock()
    return {{
        "ok": "search" in available and "code_research" in available,
        "command": "preflight",
        "available_tools": available,
        "helper_path": str(HELPER_PATH),
        "daemon_lock_path": str(DAEMON_LOCK_PATH),
        "daemon_socket_path": str(lock_payload.get("socket_path") or ""),
        "daemon_log_path": str(DAEMON_LOG_PATH),
        "daemon_pid": lock_payload.get("pid"),
        "chunkhound_command": _base_cmd(),
    }}


def _run_tool(args: argparse.Namespace) -> dict[str, Any]:
    session = JsonRpcSession()
    try:
        preflight = _run_preflight(session, args)
        if not preflight.get("ok"):
            raise RuntimeError("required ChunkHound tools are unavailable")
        tool_name, payload = _tool_payload(args)
        response = session.request("tools/call", {{"name": tool_name, "arguments": payload}})
        result = _extract_result_content(response)
        return {{
            "ok": True,
            "command": args.command,
            "tool_name": tool_name,
            "query": args.query,
            "path": args.path,
            "result": result,
            "helper_path": str(HELPER_PATH),
            "daemon_lock_path": preflight.get("daemon_lock_path"),
            "daemon_socket_path": preflight.get("daemon_socket_path"),
            "daemon_log_path": preflight.get("daemon_log_path"),
            "daemon_pid": preflight.get("daemon_pid"),
        }}
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=str(HELPER_PATH), description="CURe-managed ChunkHound helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("preflight")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--type", choices=["regex", "semantic"], default="semantic")
    search_parser.add_argument("--path")
    search_parser.add_argument("--page-size", type=int, default=10)
    search_parser.add_argument("--offset", type=int, default=0)

    research_parser = subparsers.add_parser("research")
    research_parser.add_argument("query")
    research_parser.add_argument("--path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "preflight":
        session = JsonRpcSession()
        try:
            payload = _run_preflight(session, args)
        except Exception as exc:
            return _emit({{
                "ok": False,
                "command": "preflight",
                "error": str(exc),
                "helper_path": str(HELPER_PATH),
                "daemon_lock_path": str(DAEMON_LOCK_PATH),
                "daemon_log_path": str(DAEMON_LOG_PATH),
            }}, exit_code=1)
        finally:
            session.close()
        return _emit(payload, exit_code=0 if payload.get("ok") else 1)
    try:
        payload = _run_tool(args)
        return _emit(payload, exit_code=0)
    except Exception as exc:
        return _emit({{
            "ok": False,
            "command": args.command,
            "tool_name": "code_research" if args.command == "research" else "search",
            "query": getattr(args, "query", None),
            "path": getattr(args, "path", None),
            "error": str(exc),
            "helper_path": str(HELPER_PATH),
            "daemon_lock_path": str(DAEMON_LOCK_PATH),
            "daemon_log_path": str(DAEMON_LOG_PATH),
        }}, exit_code=1)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    helper_path.write_text(script, encoding="utf-8")
    helper_path.chmod(0o755)
    return helper_path


SENSITIVE_STAGED_PATH_KEYS = ("gh_config_dir", "jira_config_file", "netrc")


def cleanup_sensitive_staged_paths(staged_paths: dict[str, Any] | None) -> None:
    if not isinstance(staged_paths, dict):
        return
    for key in SENSITIVE_STAGED_PATH_KEYS:
        raw = str(staged_paths.get(key) or "").strip()
        if not raw:
            continue
        target = Path(raw)
        if key in {"jira_config_file", "netrc"}:
            target = target.parent
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink(missing_ok=True)
        except Exception:
            continue


def _reviewflow_chunkhound_mcp_entry(
    *,
    sandbox_repo_dir: Path,
    chunkhound_config_path: Path | None,
    chunkhound_db_path: Path | None,
    chunkhound_cwd: Path | None,
    trust: bool | None = None,
) -> dict[str, Any]:
    ch_db = chunkhound_db_path or (sandbox_repo_dir / ".chunkhound.db")
    ch_cwd = chunkhound_cwd or sandbox_repo_dir
    ch_cfg = chunkhound_config_path or (ch_cwd / "chunkhound.json")
    args = ["mcp", "--config", str(ch_cfg), str(sandbox_repo_dir)]
    if chunkhound_config_path is None:
        args[3:3] = ["--database-provider", "duckdb", "--db", str(ch_db)]
    entry: dict[str, Any] = {"command": "chunkhound", "args": args, "cwd": str(ch_cwd)}
    if trust is not None:
        entry["trust"] = bool(trust)
    return entry


def _write_json_file(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    return path


def prepare_review_agent_runtime(
    *,
    args: argparse.Namespace,
    resolved: dict[str, Any],
    resolution_meta: dict[str, Any],
    reviewflow_config_path: Path,
    config_enabled: bool,
    repo_dir: Path,
    session_dir: Path,
    work_dir: Path,
    base_env: dict[str, str],
    chunkhound_config_path: Path | None,
    chunkhound_db_path: Path | None,
    chunkhound_cwd: Path | None,
    enable_mcp: bool,
    interactive: bool,
    paths: ReviewflowPaths,
) -> dict[str, Any]:
    transport = str(resolved.get("transport") or "").strip().lower()
    provider = str(resolved.get("provider") or "").strip().lower()
    profile, profile_source, runtime_cfg, runtime_meta = resolve_agent_runtime_profile(
        cli_value=getattr(args, "agent_runtime_profile", None),
        config_path=reviewflow_config_path,
        config_enabled=config_enabled,
    )
    env = build_curated_subprocess_env(extra_env=base_env)
    env = augment_cli_provider_session_env(env=env, provider=provider)
    env.update(_string_dict(resolved.get("env")))
    env, staged_paths = _stage_review_auth_support(work_dir=work_dir, repo_dir=repo_dir, env=env)
    add_dirs = _dedupe_paths([session_dir, work_dir])
    runtime: dict[str, Any] = {
        "profile": profile,
        "profile_source": profile_source,
        "provider": provider,
        "transport": transport,
        "command": str(resolved.get("command") or provider).strip() or None,
        "env": env,
        "add_dirs": add_dirs,
        "staged_paths": staged_paths,
        "dangerously_bypass_approvals_and_sandbox": False,
        "dangerously_skip_permissions": False,
        "sandbox_mode": None,
        "approval_policy": None,
        "permission_mode": None,
        "approval_mode": None,
        "codex_flags": [],
        "codex_config_overrides": [],
        "provider_args": [],
        "config": {
            "resolved_profile": profile,
            "profile_source": profile_source,
            "agent_runtime": runtime_meta.get("agent_runtime"),
        },
    }
    if transport != "cli" or provider not in CLI_LLM_PROVIDERS:
        runtime["command"] = str(resolved.get("command") or "") or None
        runtime["metadata"] = {
            "profile": profile,
            "profile_source": profile_source,
            "provider": provider,
            "transport": transport,
            "supported": False,
            "detail": "agent runtime profiles apply only to CLI coding-agent providers",
            "env_keys": sorted(env.keys()),
            "add_dirs": [str(path) for path in add_dirs],
            "staged_paths": dict(staged_paths),
        }
        return runtime

    command = _require_provider_command(str(resolved.get("command") or provider), provider=provider)
    runtime["command"] = command
    if provider == "codex":
        if enable_mcp:
            chunkhound_helper = write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=chunkhound_config_path,
                chunkhound_db_path=chunkhound_db_path,
                chunkhound_cwd=chunkhound_cwd,
            )
            env[_CURE_CHUNKHOUND_HELPER_ENV] = str(chunkhound_helper)
            runtime["staged_paths"]["chunkhound_helper"] = str(chunkhound_helper)
        codex_flags, _ = build_codex_flags_from_llm_config(resolved=resolved, resolution_meta=resolution_meta, include_sandbox=False)
        if profile == "balanced":
            runtime["sandbox_mode"] = "workspace-write"
            runtime["approval_policy"] = "on-request" if interactive else "never"
        elif profile == "strict":
            runtime["sandbox_mode"] = "read-only"
            runtime["approval_policy"] = "on-request" if interactive else "never"
        elif profile == "permissive":
            runtime["dangerously_bypass_approvals_and_sandbox"] = True
        else:
            raise ReviewflowError(f"Unsupported codex agent runtime profile: {profile!r}")
        if runtime["sandbox_mode"]:
            codex_flags.extend(["--sandbox", str(runtime["sandbox_mode"])])
        if runtime["approval_policy"]:
            codex_flags.extend(["-a", str(runtime["approval_policy"])])
        runtime["codex_flags"] = codex_flags
        runtime["codex_config_overrides"] = codex_mcp_overrides_for_reviewflow(
            enable_sandbox_chunkhound=enable_mcp,
            sandbox_repo_dir=repo_dir,
            chunkhound_db_path=chunkhound_db_path,
            chunkhound_cwd=chunkhound_cwd,
            chunkhound_config_path=chunkhound_config_path,
            paths=paths,
        )
    elif provider == "claude":
        claude_dir = work_dir / "claude"
        settings_path = _write_json_file(claude_dir / "settings.json", {})
        runtime["staged_paths"]["claude_settings"] = str(settings_path)
        provider_args: list[str] = ["--setting-sources", "user", "--settings", str(settings_path)]
        for add_dir in add_dirs:
            provider_args.extend(["--add-dir", str(add_dir)])
        if enable_mcp:
            mcp_path = _write_json_file(
                claude_dir / "mcp.json",
                {
                    "mcpServers": {
                        "cure-chunkhound": _reviewflow_chunkhound_mcp_entry(
                            sandbox_repo_dir=repo_dir,
                            chunkhound_config_path=chunkhound_config_path,
                            chunkhound_db_path=chunkhound_db_path,
                            chunkhound_cwd=chunkhound_cwd,
                        )
                    }
                },
            )
            runtime["staged_paths"]["claude_mcp_config"] = str(mcp_path)
            provider_args.extend(["--mcp-config", str(mcp_path), "--strict-mcp-config"])
        if profile == "balanced":
            runtime["permission_mode"] = "default" if interactive else "dontAsk"
        elif profile == "strict":
            runtime["permission_mode"] = "plan"
        elif profile == "permissive":
            runtime["dangerously_skip_permissions"] = True
        else:
            raise ReviewflowError(f"Unsupported claude agent runtime profile: {profile!r}")
        if runtime["permission_mode"]:
            provider_args.extend(["--permission-mode", str(runtime["permission_mode"])])
        runtime["provider_args"] = provider_args
    elif provider == "gemini":
        gemini_cfg = runtime_cfg.get("gemini")
        gemini_cfg = gemini_cfg if isinstance(gemini_cfg, dict) else {}
        configured_sandbox = str(gemini_cfg.get("sandbox") or "").strip() or None
        seatbelt_profile = str(gemini_cfg.get("seatbelt_profile") or "").strip() or None
        if profile == "balanced":
            runtime["approval_mode"] = "auto_edit"
            env["GEMINI_SANDBOX"] = configured_sandbox or "true"
        elif profile == "strict":
            runtime["approval_mode"] = "plan"
            if not configured_sandbox:
                raise ReviewflowError(
                    "Gemini strict agent runtime requires [agent_runtime.gemini].sandbox to be configured."
                )
            env["GEMINI_SANDBOX"] = configured_sandbox
        elif profile == "permissive":
            runtime["approval_mode"] = "yolo"
            if configured_sandbox:
                env["GEMINI_SANDBOX"] = configured_sandbox
        else:
            raise ReviewflowError(f"Unsupported gemini agent runtime profile: {profile!r}")
        if seatbelt_profile:
            env["SEATBELT_PROFILE"] = seatbelt_profile
        home_root, cli_dir = _prepare_gemini_cli_home(work_dir=work_dir)
        trusted_folders_path = _write_json_file(
            cli_dir / "trustedFolders.json",
            {str(repo_dir.resolve(strict=False)): "TRUST_FOLDER"},
        )
        system_settings: dict[str, Any] = {}
        if enable_mcp:
            system_settings["mcpServers"] = {
                "cure-chunkhound": _reviewflow_chunkhound_mcp_entry(
                    sandbox_repo_dir=repo_dir,
                    chunkhound_config_path=chunkhound_config_path,
                    chunkhound_db_path=chunkhound_db_path,
                    chunkhound_cwd=chunkhound_cwd,
                    trust=False,
                )
            }
            system_settings["mcp"] = {"allowed": ["cure-chunkhound"]}
        system_settings_path = _write_json_file(work_dir / "gemini" / "system-settings.json", system_settings)
        env["GEMINI_CLI_HOME"] = str(home_root)
        env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(system_settings_path)
        runtime["staged_paths"]["gemini_home"] = str(home_root)
        runtime["staged_paths"]["gemini_trusted_folders"] = str(trusted_folders_path)
        runtime["staged_paths"]["gemini_system_settings"] = str(system_settings_path)
        provider_args = ["--output-format", "json", "--approval-mode", str(runtime["approval_mode"])]
        for add_dir in add_dirs:
            provider_args.extend(["--include-directories", str(add_dir)])
        runtime["provider_args"] = provider_args
    else:
        raise ReviewflowError(f"Unsupported CLI provider for agent runtime preparation: {provider!r}")

    runtime["metadata"] = {
        "profile": runtime["profile"],
        "profile_source": runtime["profile_source"],
        "provider": runtime["provider"],
        "sandbox_mode": runtime["sandbox_mode"],
        "approval_policy": runtime["approval_policy"],
        "permission_mode": runtime["permission_mode"],
        "approval_mode": runtime["approval_mode"],
        "dangerously_bypass_approvals_and_sandbox": bool(runtime["dangerously_bypass_approvals_and_sandbox"]),
        "dangerously_skip_permissions": bool(runtime["dangerously_skip_permissions"]),
        "chunkhound_access_mode": (
            _CURE_CHUNKHOUND_ACCESS_MODE
            if provider == "codex" and bool(runtime["staged_paths"].get("chunkhound_helper"))
            else None
        ),
        "env_keys": sorted(env.keys()),
        "add_dirs": [str(path) for path in add_dirs],
        "staged_paths": dict(runtime["staged_paths"]),
    }
    return runtime


def _parse_iso_dt(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _load_codex_session_meta(session_log_path: Path) -> dict[str, Any] | None:
    try:
        with session_log_path.open("r", encoding="utf-8") as fh:
            first_line = fh.readline().strip()
    except Exception:
        return None
    if not first_line:
        return None
    try:
        data = json.loads(first_line)
    except Exception:
        return None
    if data.get("type") != "session_meta":
        return None
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else None


def _iter_codex_session_logs(*, codex_root: Path, started_at: datetime) -> list[Path]:
    sessions_root = codex_root / "sessions"
    if not sessions_root.is_dir():
        return []
    dates = {started_at.astimezone(timezone.utc).date(), datetime.now(timezone.utc).date()}
    logs: set[Path] = set()
    for day in dates:
        day_dir = sessions_root / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
        if not day_dir.is_dir():
            continue
        logs.update(day_dir.glob("rollout-*.jsonl"))
    return sorted(logs, reverse=True)


def _iter_codex_session_logs_for_dates(*, codex_root: Path, dates: set[date]) -> list[Path]:
    sessions_root = codex_root / "sessions"
    if not sessions_root.is_dir():
        return []
    logs: set[Path] = set()
    for day in dates:
        day_dir = sessions_root / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
        if not day_dir.is_dir():
            continue
        logs.update(day_dir.glob("rollout-*.jsonl"))
    return sorted(logs, reverse=True)


def _find_codex_session_log_by_id(
    *, codex_root: Path, session_id: str, created_at: str | None, completed_at: str | None
) -> Path | None:
    session_id = str(session_id or "").strip()
    if not session_id:
        return None
    candidate_dates: set[date] = {datetime.now(timezone.utc).date()}
    for raw in (completed_at, created_at):
        dt = _parse_iso_dt(str(raw or "").strip())
        if dt is None:
            continue
        dt = dt.astimezone(timezone.utc)
        candidate_dates.add((dt - timedelta(days=1)).date())
        candidate_dates.add(dt.date())
        candidate_dates.add((dt + timedelta(days=1)).date())
    searched: set[Path] = set()
    for session_log in _iter_codex_session_logs_for_dates(codex_root=codex_root, dates=candidate_dates):
        searched.add(session_log)
        payload = _load_codex_session_meta(session_log)
        if payload and str(payload.get("id") or "").strip() == session_id:
            return session_log
    sessions_root = codex_root / "sessions"
    if not sessions_root.is_dir():
        return None
    for session_log in sorted(sessions_root.rglob("rollout-*.jsonl"), reverse=True):
        if session_log in searched:
            continue
        payload = _load_codex_session_meta(session_log)
        if payload and str(payload.get("id") or "").strip() == session_id:
            return session_log
    return None


def _codex_session_meta_is_subagent(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("forked_from_id") or "").strip():
        return True
    source = payload.get("source")
    return isinstance(source, dict) and isinstance(source.get("subagent"), dict)


def build_codex_resume_command(
    *,
    repo_dir: Path,
    session_id: str,
    env: dict[str, str],
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    add_dirs: list[Path] | None = None,
    approval_policy: str | None = None,
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
) -> str:
    _ = add_dirs
    assignments: list[str] = []
    has_explicit_approval_flag = any(flag in {"-a", "--ask-for-approval"} for flag in codex_flags)
    for key in ("GH_CONFIG_DIR", "JIRA_CONFIG_FILE", "NETRC", "CURE_WORK_DIR"):
        value = str(env.get(key) or "").strip()
        if value:
            assignments.append(f"{key}={shlex.quote(value)}")
    resume_cmd: list[str] = ["codex", "resume", "--add-dir", "/tmp"]
    if approval_policy and (not dangerously_bypass_approvals_and_sandbox) and (not has_explicit_approval_flag):
        resume_cmd.extend(["-a", approval_policy])
    resume_cmd.extend(codex_flags)
    for override in codex_config_overrides or []:
        resume_cmd.extend(["-c", override])
    if include_shell_environment_inherit_all:
        resume_cmd.extend(["-c", "shell_environment_policy.inherit=all"])
    if dangerously_bypass_approvals_and_sandbox:
        resume_cmd.append("--dangerously-bypass-approvals-and-sandbox")
    resume_cmd.append(session_id)
    env_prefix = ""
    if assignments:
        env_prefix = "env " + " ".join(assignments) + " "
    return f"cd {shlex.quote(str(repo_dir))} && {env_prefix}{_shell_join(resume_cmd)}"


def find_codex_resume_info(
    *,
    repo_dir: Path,
    started_at: datetime,
    env: dict[str, str],
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    add_dirs: list[Path] | None = None,
    codex_root: Path | None = None,
    approval_policy: str | None = None,
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
) -> CodexResumeInfo | None:
    codex_home = codex_root or (real_user_home_dir() / ".codex")
    repo_root = repo_dir.resolve(strict=False)
    best: tuple[datetime, CodexResumeInfo] | None = None
    window_start = started_at - timedelta(minutes=5)
    for session_log in _iter_codex_session_logs(codex_root=codex_home, started_at=started_at):
        payload = _load_codex_session_meta(session_log)
        if not payload:
            continue
        originator = str(payload.get("originator") or "").strip()
        if originator not in {"codex_exec", "codex_cli_rs"}:
            continue
        raw_cwd = str(payload.get("cwd") or "").strip()
        if not raw_cwd or Path(raw_cwd).resolve(strict=False) != repo_root:
            continue
        raw_session_id = str(payload.get("id") or "").strip()
        if not raw_session_id:
            continue
        raw_timestamp = str(payload.get("timestamp") or "").strip()
        timestamp = _parse_iso_dt(raw_timestamp)
        if timestamp is None or timestamp < window_start or _codex_session_meta_is_subagent(payload):
            continue
        info = CodexResumeInfo(
            session_id=raw_session_id,
            cwd=repo_root,
            command=build_codex_resume_command(
                repo_dir=repo_root,
                session_id=raw_session_id,
                env=env,
                codex_flags=codex_flags,
                codex_config_overrides=codex_config_overrides,
                add_dirs=add_dirs,
                approval_policy=approval_policy,
                dangerously_bypass_approvals_and_sandbox=dangerously_bypass_approvals_and_sandbox,
                include_shell_environment_inherit_all=include_shell_environment_inherit_all,
            ),
        )
        if best is None or timestamp > best[0]:
            best = (timestamp, info)
    return best[1] if best else None


def codex_resume_meta_dict(info: CodexResumeInfo | None) -> dict[str, str] | None:
    if info is None:
        return None
    return {"session_id": info.session_id, "cwd": str(info.cwd), "command": info.command}


def record_codex_resume(container: dict[str, Any], info: CodexResumeInfo | None) -> str | None:
    payload = codex_resume_meta_dict(info)
    if payload is None:
        return None
    container["resume"] = payload
    return str(payload["command"])


def llm_resume_meta_dict(info: LlmResumeInfo | None) -> dict[str, str] | None:
    if info is None:
        return None
    return {
        "provider": str(info.provider),
        "session_id": info.session_id,
        "cwd": str(info.cwd),
        "command": info.command,
    }


def record_llm_resume(container: dict[str, Any], info: LlmResumeInfo | None) -> str | None:
    payload = llm_resume_meta_dict(info)
    if payload is None:
        return None
    container["resume"] = payload
    return str(payload["command"])
