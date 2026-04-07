from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Callable

from cure_errors import ReviewflowError
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
    _raise_removed_gemini_support,
    _string_dict,
    augment_cli_provider_session_env,
    build_curated_subprocess_env,
    build_http_response_request,
    resolve_agent_runtime_profile,
    toml_string,
)
from meta import write_json
from paths import (
    ReviewflowPaths,
    real_user_home_dir,
)
from run import ReviewflowSubprocessError, run_cmd
from ui import TailBuffer

if TYPE_CHECKING:
    from cure import SessionProgress


def _reviewflow():
    import cure as rf

    return rf


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


_LIVE_PROGRESS_TIMELINE_MAX = 12
_CURE_CHUNKHOUND_HELPER_ENV = "CURE_CHUNKHOUND_HELPER"
_CURE_CHUNKHOUND_DRY_RUN_ENV = "CURE_CHUNKHOUND_DRY_RUN"
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


def _compact_live_progress_text(text: object, *, max_chars: int = 240) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return value[:max_chars]
    return value[: max_chars - 1] + "…"


def _looks_like_json_payload_line(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw or not raw.startswith("{"):
        return False
    try:
        parsed = json.loads(raw)
    except Exception:
        return False
    return isinstance(parsed, dict)


def _looks_like_pathish_progress_line(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if re.fullmatch(r"[`'\"]?(?:[.~]{0,2}/|[A-Za-z]:\\)[^ \t`'\"]+[`'\"]?", raw):
        return True
    if re.fullmatch(r"[`'\"]?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+[`'\"]?", raw):
        return True
    return False


def _summarize_claude_text_block(text: object) -> str:
    compact = _compact_live_progress_text(text, max_chars=120)
    if not compact:
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", compact)
    if match:
        return _compact_live_progress_text(match.group(1), max_chars=120)
    return compact


def _summarize_claude_tool_result(
    tool_result: dict[str, Any] | None,
    *,
    tool_name: str | None = None,
    tool_input_payload: str | None = None,
    bash_command: str | None = None,
) -> str:
    payload = tool_result if isinstance(tool_result, dict) else {}
    name = str(tool_name or "").strip()
    raw_input = str(tool_input_payload or "").strip()
    context = ""
    parsed_input = None
    if raw_input:
        try:
            parsed_input = json.loads(raw_input)
        except Exception:
            parsed_input = None
    if name == "Bash":
        command = str(bash_command or "").strip()
        if not command and isinstance(parsed_input, dict):
            command = str(parsed_input.get("command") or "").strip()
        if command:
            context = command
    elif name == "Read" and isinstance(parsed_input, dict):
        file_path = str(parsed_input.get("file_path") or parsed_input.get("path") or "").strip()
        offset = parsed_input.get("offset")
        limit = parsed_input.get("limit")
        if file_path:
            context = file_path
            if isinstance(offset, int) and isinstance(limit, int) and limit > 0:
                context = f"{context}:{offset + 1}-{offset + limit}"
    for key in ("stdout", "stderr"):
        source = str(payload.get(key) or "")
        for raw_line in source.splitlines():
            raw_line = str(raw_line or "").strip()
            if not raw_line:
                continue
            if _looks_like_json_payload_line(raw_line):
                continue
            line = _compact_live_progress_text(raw_line)
            if _looks_like_pathish_progress_line(line):
                continue
            if re.fullmatch(r"[#*_`~=\-]{3,}", line):
                continue
            if context and line != context:
                return f"{context} - {line}"
            return context or line
    return context


def _ensure_text_cli_live_progress(*, progress: Any, provider: str, label: str) -> None:
    meta = _progress_meta_dict(progress)
    if meta is None:
        return
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = _compact_live_progress_text(label)
    current = {"type": "provider_status", "text": text, "ts": timestamp}
    live = meta.get("live_progress") if isinstance(meta.get("live_progress"), dict) else {}
    live["source"] = f"{provider}_exec_text"
    live["provider"] = provider
    live["status"] = "running"
    live["updated_at"] = timestamp
    live["current"] = current
    timeline = list(live.get("timeline")) if isinstance(live.get("timeline"), list) else []
    last = timeline[-1] if timeline and isinstance(timeline[-1], dict) else {}
    if last.get("text") != text or last.get("type") != "provider_status":
        timeline.append(current)
    if len(timeline) > _LIVE_PROGRESS_TIMELINE_MAX:
        timeline = timeline[-_LIVE_PROGRESS_TIMELINE_MAX:]
    live["timeline"] = timeline
    meta["live_progress"] = live
    _flush_progress(progress)


def _set_text_cli_live_current(
    *,
    progress: Any,
    provider: str,
    text: str,
    event_type: str = "provider_output",
    add_timeline: bool = False,
) -> None:
    meta = _progress_meta_dict(progress)
    raw = str(text or "").strip()
    if meta is None or not raw:
        return
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item = {"type": event_type, "text": _compact_live_progress_text(raw), "ts": timestamp}
    live = meta.get("live_progress") if isinstance(meta.get("live_progress"), dict) else {}
    live["source"] = f"{provider}_exec_text"
    live["provider"] = provider
    live["status"] = "running"
    live["updated_at"] = timestamp
    live["current"] = item
    if add_timeline:
        timeline = list(live.get("timeline")) if isinstance(live.get("timeline"), list) else []
        last = timeline[-1] if timeline and isinstance(timeline[-1], dict) else {}
        if last.get("text") != item["text"] or last.get("type") != event_type:
            timeline.append(item)
        if len(timeline) > _LIVE_PROGRESS_TIMELINE_MAX:
            timeline = timeline[-_LIVE_PROGRESS_TIMELINE_MAX:]
        live["timeline"] = timeline
    meta["live_progress"] = live
    _flush_progress(progress)


def _record_text_cli_live_output(*, progress: Any, provider: str, text: str) -> None:
    meta = _progress_meta_dict(progress)
    if meta is None or not text:
        return
    lines: list[str] = []
    for raw_line in str(text).splitlines():
        raw = str(raw_line or "").strip()
        if not raw or _looks_like_json_payload_line(raw):
            continue
        line = _compact_live_progress_text(raw)
        lines.append(line)
    if not lines:
        return

    live = meta.get("live_progress") if isinstance(meta.get("live_progress"), dict) else {}
    live["source"] = f"{provider}_exec_text"
    live["provider"] = provider
    live["status"] = "running"
    timeline = list(live.get("timeline")) if isinstance(live.get("timeline"), list) else []
    current = live.get("current") if isinstance(live.get("current"), dict) else {}
    for line in lines:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        item = {"type": "provider_output", "text": line, "ts": timestamp}
        last = timeline[-1] if timeline and isinstance(timeline[-1], dict) else {}
        if last.get("text") != line or last.get("type") != "provider_output":
            timeline.append(item)
        current = item
        live["updated_at"] = timestamp
    if len(timeline) > _LIVE_PROGRESS_TIMELINE_MAX:
        timeline = timeline[-_LIVE_PROGRESS_TIMELINE_MAX:]
    live["timeline"] = timeline
    live["current"] = current
    meta["live_progress"] = live
    _flush_progress(progress)


def _finalize_text_cli_live_progress(*, progress: Any, provider: str, status: str) -> None:
    meta = _progress_meta_dict(progress)
    if meta is None:
        return
    live = meta.get("live_progress")
    if not isinstance(live, dict) or str(live.get("provider") or "").strip() != provider:
        return
    live["status"] = str(status or "done")
    live["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta["live_progress"] = live
    _flush_progress(progress)


def _extract_claude_text_from_message(message: dict[str, Any] | None) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "text":
            continue
        text = str(item.get("text") or "")
        if text:
            chunks.append(text)
    return "".join(chunks).strip()


def _extract_claude_payload_model(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    direct = str(payload.get("model") or "").strip()
    if direct:
        return direct
    message = payload.get("message")
    if isinstance(message, dict):
        model = str(message.get("model") or "").strip()
        if model:
            return model
    event = payload.get("event")
    if isinstance(event, dict):
        message = event.get("message")
        if isinstance(message, dict):
            model = str(message.get("model") or "").strip()
            if model:
                return model
    return None


def _parse_claude_stream_payload(text: str) -> dict[str, Any]:
    result_payloads: list[dict[str, Any]] = []
    assistant_payload: dict[str, Any] = {}
    session_id = ""
    model = ""
    for raw_line in str(text or "").splitlines():
        raw = str(raw_line or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        session_id = str(payload.get("session_id") or session_id).strip()
        model = str(_extract_claude_payload_model(payload) or model).strip()
        payload_type = str(payload.get("type") or "").strip()
        if payload_type == "assistant":
            assistant_payload = payload
        elif payload_type == "result":
            result_payloads.append(payload)
        elif "result" in payload:
            result_payloads.append(payload)
    result_payload = _select_claude_result_payload(result_payloads)
    if result_payload:
        if session_id and not str(result_payload.get("session_id") or "").strip():
            result_payload["session_id"] = session_id
        if model and not str(result_payload.get("model") or "").strip():
            result_payload["model"] = model
        return result_payload

    assistant_text = _extract_claude_text_from_message(assistant_payload.get("message"))
    payload: dict[str, Any] = {}
    if assistant_text:
        payload["result"] = assistant_text
    if session_id:
        payload["session_id"] = session_id
    if model:
        payload["model"] = model
    usage = _extract_usage_from_payload(assistant_payload)
    if usage is not None:
        payload["usage"] = usage
    return payload


def _claude_result_payload_rank(payload: dict[str, Any], index: int) -> tuple[int, int, int, int, int]:
    result_text = str(payload.get("result") or "")
    raw_turns = payload.get("num_turns")
    try:
        num_turns = int(raw_turns)
    except Exception:
        num_turns = -1
    is_error = payload.get("is_error") is True
    return (
        1 if result_text.strip() else 0,
        0 if is_error else 1,
        num_turns,
        len(result_text),
        index,
    )


def _select_claude_result_payload(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    best_payload: dict[str, Any] = {}
    best_rank: tuple[int, int, int, int, int] | None = None
    for index, payload in enumerate(payloads):
        rank = _claude_result_payload_rank(payload, index)
        if best_rank is None or rank > best_rank:
            best_payload = payload
            best_rank = rank
    return best_payload


def _format_claude_tool_progress(*, tool_name: str, input_payload: str) -> str:
    name = str(tool_name or "Tool").strip() or "Tool"
    raw = str(input_payload or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        command = str(parsed.get("command") or "").strip()
        description = str(parsed.get("description") or "").strip()
        if name == "Bash" and command:
            return f"Bash: {command}"
        if description:
            return f"{name}: {description}"
        if command:
            return f"{name}: {command}"
    return ""


def _is_chunkhound_helper_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    helper_path = str(payload.get("helper_path") or "").strip()
    if not helper_path:
        return False
    return any(str(payload.get(key) or "").strip() for key in ("command", "preflight_stage", "execution_stage"))


def _parse_chunkhound_helper_output_texts(payload_text: object) -> list[dict[str, Any]]:
    text = str(payload_text or "").strip()
    if not text:
        return []
    payloads: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        candidate = str(raw_line or "").strip()
        if not candidate or not candidate.startswith("{"):
            continue
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if _is_chunkhound_helper_payload(payload):
            payloads.append(payload)
    if payloads:
        return payloads
    for candidate in (text,):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if _is_chunkhound_helper_payload(payload):
            return [payload]
    return []


def _latest_claude_bash_command(state: dict[str, Any]) -> str | None:
    raw_queue = state.get("bash_tool_commands")
    queue = raw_queue if isinstance(raw_queue, list) else []
    while queue:
        candidate = queue.pop(0)
        if isinstance(candidate, str) and candidate.strip():
            state["bash_tool_commands"] = queue
            return candidate.strip()
    state["bash_tool_commands"] = queue
    return None


def _extract_claude_tool_result_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    message = payload.get("message")
    message = message if isinstance(message, dict) else {}
    content = message.get("content")
    blocks = content if isinstance(content, list) else []
    results: list[dict[str, Any]] = []
    for item in blocks:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() == "tool_result":
            results.append(item)
    return results


def _extract_claude_tool_use_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    message = payload.get("message")
    message = message if isinstance(message, dict) else {}
    content = message.get("content")
    blocks = content if isinstance(content, list) else []
    results: list[dict[str, Any]] = []
    for item in blocks:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() == "tool_use":
            results.append(item)
    return results


def _extract_claude_tool_use_id(payload: dict[str, Any]) -> str:
    tool_use_id = str(payload.get("tool_use_id") or "").strip()
    if tool_use_id:
        return tool_use_id
    for block in _extract_claude_tool_result_blocks(payload):
        tool_use_id = str(block.get("tool_use_id") or "").strip()
        if tool_use_id:
            return tool_use_id
    return ""


def _extract_claude_tool_result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() == "text":
            text = str(item.get("text") or "")
            if text:
                parts.append(text)
    return "\n".join(parts)


def _append_claude_chunkhound_tool_proof(*, state: dict[str, Any], stdout_text: object, tool_use_id: str | None) -> None:
    payloads = _parse_chunkhound_helper_output_texts(stdout_text)
    if not payloads:
        return
    resolved_tool_use_id = str(tool_use_id or "").strip()
    if not resolved_tool_use_id:
        raise ReviewflowError(
            "Claude tool_result contract mismatch: helper payload was present without a documented tool_use_id."
        )
    entries = state.setdefault("chunkhound_tool_proof_entries", [])
    if not isinstance(entries, list):
        entries = []
        state["chunkhound_tool_proof_entries"] = entries
    raw_commands = state.setdefault("bash_tool_commands_by_id", {})
    commands_by_id = raw_commands if isinstance(raw_commands, dict) else {}
    if raw_commands is not commands_by_id:
        state["bash_tool_commands_by_id"] = commands_by_id
    command = str(commands_by_id.get(resolved_tool_use_id) or "").strip()
    if not command:
        raise ReviewflowError(
            "Claude tool_result contract mismatch: helper payload tool_use_id did not match a captured Bash command."
        )
    stdout_excerpt = str(stdout_text or "").strip()
    if len(stdout_excerpt) > 240:
        stdout_excerpt = stdout_excerpt[:240].rstrip() + "..."
    for payload in payloads:
        entries.append(
            {
                "payload": payload,
                "stdout_excerpt": stdout_excerpt,
                "command": command,
                "tool_use_id": resolved_tool_use_id,
            }
        )


def _append_claude_chunkhound_tool_proof_from_output_file(
    *,
    state: dict[str, Any],
    output_file: object,
    tool_use_id: str | None,
) -> bool:
    output_path_text = str(output_file or "").strip()
    if not output_path_text:
        return False
    seen_files = state.setdefault("claude_task_output_files_seen", set())
    if not isinstance(seen_files, set):
        seen_files = set()
        state["claude_task_output_files_seen"] = seen_files
    key = (output_path_text, str(tool_use_id or "").strip())
    if key in seen_files:
        return False
    try:
        output_text = Path(output_path_text).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    seen_files.add(key)
    _append_claude_chunkhound_tool_proof(
        state=state,
        stdout_text=output_text,
        tool_use_id=tool_use_id,
    )
    return True


def _handle_claude_stream_chunk(*, progress: Any, state: dict[str, Any], chunk: str) -> None:
    for raw_line in str(chunk or "").splitlines():
        raw = str(raw_line or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            _record_text_cli_live_output(progress=progress, provider="claude", text=raw)
            continue
        if not isinstance(payload, dict):
            continue
        payload_type = str(payload.get("type") or "").strip()
        if payload_type == "system":
            if (
                str(payload.get("subtype") or "").strip() == "task_notification"
                and str(payload.get("status") or "").strip() == "completed"
            ):
                _append_claude_chunkhound_tool_proof_from_output_file(
                    state=state,
                    output_file=payload.get("output_file"),
                    tool_use_id=str(payload.get("tool_use_id") or "").strip() or None,
                )
            continue
        if payload_type == "assistant":
            for tool_use_block in _extract_claude_tool_use_blocks(payload):
                tool_use_id = str(tool_use_block.get("id") or "").strip()
                tool_name = str(tool_use_block.get("name") or "Tool").strip() or "Tool"
                input_payload = tool_use_block.get("input")
                input_text = json.dumps(input_payload) if isinstance(input_payload, dict) else str(input_payload or "")
                if not tool_use_id:
                    continue
                for key, value in list(state.items()):
                    if not key.startswith("block_") or not key.endswith("_tool_use_id"):
                        continue
                    if str(value or "").strip() != tool_use_id:
                        continue
                    block_key = key[: -len("_tool_use_id")]
                    state[f"{block_key}_name"] = tool_name
                    state[f"{block_key}_input"] = input_text
                    break
                raw_commands = state.setdefault("bash_tool_commands_by_id", {})
                commands_by_id = raw_commands if isinstance(raw_commands, dict) else {}
                if raw_commands is not commands_by_id:
                    state["bash_tool_commands_by_id"] = commands_by_id
                if tool_name == "Bash":
                    try:
                        parsed_input = json.loads(input_text)
                    except Exception:
                        parsed_input = None
                    if isinstance(parsed_input, dict):
                        command_text = str(parsed_input.get("command") or "").strip()
                        if command_text:
                            commands_by_id[tool_use_id] = command_text
                current = _format_claude_tool_progress(tool_name=tool_name, input_payload=input_text)
                if current:
                    _set_text_cli_live_current(progress=progress, provider="claude", text=current)
            continue
        if payload_type == "user":
            tool_result = payload.get("tool_use_result")
            top_level_stdout = tool_result.get("stdout") if isinstance(tool_result, dict) else None
            top_level_helper_payloads = _parse_chunkhound_helper_output_texts(top_level_stdout)
            documented_helper_payloads_seen = False
            for tool_result_block in _extract_claude_tool_result_blocks(payload):
                result_text = _extract_claude_tool_result_text(tool_result_block)
                if not _parse_chunkhound_helper_output_texts(result_text):
                    continue
                documented_helper_payloads_seen = True
                _append_claude_chunkhound_tool_proof(
                    state=state,
                    stdout_text=result_text,
                    tool_use_id=str(tool_result_block.get("tool_use_id") or "").strip() or None,
                )
            if top_level_helper_payloads and not documented_helper_payloads_seen:
                raise ReviewflowError(
                    "Claude tool_result contract mismatch: helper payload was present in tool_use_result stdout "
                    "without a documented message.content tool_result block."
                )
            tool_use_id = _extract_claude_tool_use_id(payload)
            raw_commands = state.setdefault("bash_tool_commands_by_id", {})
            commands_by_id = raw_commands if isinstance(raw_commands, dict) else {}
            if raw_commands is not commands_by_id:
                state["bash_tool_commands_by_id"] = commands_by_id
            tool_name = ""
            tool_input = ""
            if tool_use_id:
                for key, value in state.items():
                    if not key.startswith("block_") or not key.endswith("_tool_use_id"):
                        continue
                    if str(value or "").strip() != tool_use_id:
                        continue
                    block_key = key[: -len("_tool_use_id")]
                    tool_name = str(state.get(f"{block_key}_name") or "").strip()
                    tool_input = str(state.get(f"{block_key}_input") or "")
                    break
            summary = _summarize_claude_tool_result(
                tool_result if isinstance(tool_result, dict) else None,
                tool_name=tool_name,
                tool_input_payload=tool_input,
                bash_command=str(commands_by_id.get(tool_use_id) or "").strip() or None,
            )
            if summary:
                _set_text_cli_live_current(
                    progress=progress,
                    provider="claude",
                    text=f"Tool result: {summary}",
                    add_timeline=True,
                )
            continue
        if payload_type != "stream_event":
            continue
        event = payload.get("event")
        event = event if isinstance(event, dict) else {}
        event_type = str(event.get("type") or "").strip()
        raw_index = event.get("index")
        index = "" if raw_index is None else str(raw_index)
        block_key = f"block_{index}" if index else ""
        if event_type == "content_block_start":
            content_block = event.get("content_block")
            content_block = content_block if isinstance(content_block, dict) else {}
            block_type = str(content_block.get("type") or "").strip()
            if block_key:
                state[f"{block_key}_type"] = block_type
            if block_type == "thinking":
                if block_key:
                    state[f"{block_key}_text"] = ""
            elif block_type == "tool_use":
                tool_name = str(content_block.get("name") or "Tool").strip() or "Tool"
                if block_key:
                    state[f"{block_key}_name"] = tool_name
                    state[f"{block_key}_input"] = ""
                    state[f"{block_key}_tool_use_id"] = str(content_block.get("id") or "").strip()
                _set_text_cli_live_current(
                    progress=progress,
                    provider="claude",
                    text=f"Using {tool_name}",
                    add_timeline=True,
                )
            elif block_type == "text":
                state["content"] = ""
                if block_key:
                    state[f"{block_key}_text"] = ""
            continue

        if event_type == "content_block_stop":
            if block_key and str(state.get(f"{block_key}_type") or "").strip() == "text":
                completed = str(state.get(f"{block_key}_text") or state.get("content") or "")
                summary = _summarize_claude_text_block(completed)
                if summary:
                    _set_text_cli_live_current(
                        progress=progress,
                        provider="claude",
                        text=summary,
                        event_type="assistant_text",
                        add_timeline=True,
                    )
            continue

        if event_type != "content_block_delta":
            continue
        delta = event.get("delta")
        delta = delta if isinstance(delta, dict) else {}
        delta_type = str(delta.get("type") or "").strip()
        if delta_type == "text_delta":
            delta_text = str(delta.get("text") or "")
            if not delta_text:
                continue
            state["content"] = str(state.get("content") or "") + delta_text
            if block_key:
                state[f"{block_key}_text"] = str(state.get(f"{block_key}_text") or "") + delta_text
            _set_text_cli_live_current(progress=progress, provider="claude", text=state["content"])
            continue
        if delta_type == "thinking_delta":
            delta_text = str(delta.get("thinking") or "")
            if not delta_text:
                continue
            if block_key:
                state[f"{block_key}_text"] = str(state.get(f"{block_key}_text") or "") + delta_text
            continue
        if delta_type == "input_json_delta":
            partial_json = str(delta.get("partial_json") or "")
            if not partial_json:
                continue
            if block_key:
                state[f"{block_key}_input"] = str(state.get(f"{block_key}_input") or "") + partial_json
                tool_name = str(state.get(f"{block_key}_name") or "Tool")
                if tool_name == "Bash":
                    raw_commands = state.setdefault("bash_tool_commands_by_id", {})
                    commands_by_id = raw_commands if isinstance(raw_commands, dict) else {}
                    if raw_commands is not commands_by_id:
                        state["bash_tool_commands_by_id"] = commands_by_id
                    try:
                        parsed_input = json.loads(str(state.get(f"{block_key}_input") or ""))
                    except Exception:
                        parsed_input = None
                    if isinstance(parsed_input, dict):
                        command_text = str(parsed_input.get("command") or "").strip()
                        if command_text:
                            state[f"{block_key}_command"] = command_text
                            tool_use_id = str(state.get(f"{block_key}_tool_use_id") or "").strip()
                            if tool_use_id:
                                commands_by_id[tool_use_id] = command_text
                current = _format_claude_tool_progress(
                    tool_name=tool_name,
                    input_payload=str(state.get(f"{block_key}_input") or ""),
                )
                if current:
                    _set_text_cli_live_current(progress=progress, provider="claude", text=current)


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


def _resolve_claude_events_log_path(*, progress: Any, repo_dir: Path) -> Path:
    meta = _progress_meta_dict(progress)
    logs = (meta.get("logs") if isinstance(meta, dict) and isinstance(meta.get("logs"), dict) else {})
    raw_path = str(logs.get("claude_events") or "").strip()
    if raw_path:
        path = Path(raw_path)
        return ((repo_dir.parent / path).resolve() if not path.is_absolute() else path.resolve())
    path = (repo_dir.parent / "work" / "logs" / "claude.events.jsonl").resolve()
    if isinstance(meta, dict):
        meta.setdefault("logs", {})["claude_events"] = str(path)
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


def _coerce_usage_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _normalize_usage_payload(raw: object) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    input_tokens = _coerce_usage_int(raw.get("input_tokens"))
    if input_tokens is None:
        input_tokens = _coerce_usage_int(raw.get("prompt_tokens"))
    if input_tokens is None:
        input_tokens = _coerce_usage_int(raw.get("inputTokenCount"))

    output_tokens = _coerce_usage_int(raw.get("output_tokens"))
    if output_tokens is None:
        output_tokens = _coerce_usage_int(raw.get("completion_tokens"))
    if output_tokens is None:
        output_tokens = _coerce_usage_int(raw.get("outputTokenCount"))
    if output_tokens is None:
        output_tokens = _coerce_usage_int(raw.get("candidatesTokenCount"))

    total_tokens = _coerce_usage_int(raw.get("total_tokens"))
    if total_tokens is None:
        total_tokens = _coerce_usage_int(raw.get("totalTokenCount"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    normalized = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    if all(value is None for value in normalized.values()):
        return None
    return {key: value for key, value in normalized.items() if isinstance(value, int)}


def _merge_usage_totals(
    left: dict[str, int] | None, right: dict[str, int] | None
) -> dict[str, int] | None:
    if left is None:
        return dict(right) if right is not None else None
    if right is None:
        return dict(left)
    merged: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        lhs = left.get(key)
        rhs = right.get(key)
        if lhs is None and rhs is None:
            continue
        if lhs is None:
            merged[key] = int(rhs)
        elif rhs is None:
            merged[key] = int(lhs)
        else:
            merged[key] = int(lhs) + int(rhs)
    if "total_tokens" not in merged and "input_tokens" in merged and "output_tokens" in merged:
        merged["total_tokens"] = merged["input_tokens"] + merged["output_tokens"]
    return merged or None


def _extract_usage_from_payload(payload: dict[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(payload, dict):
        return None
    candidates: list[object] = [payload.get("usage"), payload.get("usageMetadata")]
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend([result.get("usage"), result.get("usageMetadata")])
    candidates.append(payload)
    for candidate in candidates:
        normalized = _normalize_usage_payload(candidate)
        if normalized is not None:
            return normalized
    return None


def _extract_codex_usage_from_event_slice(
    *, events_path: Path | None, start_offset: int | None, end_offset: int | None
) -> dict[str, int] | None:
    if events_path is None or not events_path.is_file():
        return None
    start = max(0, int(start_offset or 0))
    end = _path_size(events_path) if end_offset is None else max(start, int(end_offset))
    try:
        with events_path.open("r", encoding="utf-8") as fh:
            fh.seek(start)
            raw = fh.read(max(0, end - start))
    except OSError:
        return None

    usage_totals: dict[str, int] | None = None
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("type") or "").strip() != "turn.completed":
            continue
        usage = _normalize_usage_payload(payload.get("usage"))
        usage_totals = _merge_usage_totals(usage_totals, usage)
    return usage_totals


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


def _run_logged_text_command(
    *,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    claude_json_events_path: Path | None = None,
    claude_event_callback: Callable[[dict[str, Any]], None] | None = None,
    stream_text_callback: Callable[[str], None] | None = None,
):
    out = active_output()
    if out is not None:
        return out.run_logged_cmd(
            cmd,
            kind="codex",
            cwd=cwd,
            env=env,
            check=True,
            stream_requested=False,
            claude_json_events_path=claude_json_events_path,
            claude_event_callback=claude_event_callback,
            stream_text_callback=stream_text_callback,
        )
    return run_cmd(cmd, cwd=cwd, env=env, check=True, stream=False, stream_label="codex")


def build_claude_exec_cmd(
    *,
    command: str,
    model: str | None,
    prompt: str,
    runtime_policy: dict[str, Any] | None = None,
) -> list[str]:
    cmd = [
        command,
        "--print",
        "--verbose",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
    ]
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
    cmd.extend(["--", prompt])
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
        (
            "ANTHROPIC_API_KEY",
            "GH_CONFIG_DIR",
            "JIRA_CONFIG_FILE",
            "NETRC",
            "CURE_WORK_DIR",
            "CURE_CHUNKHOUND_HELPER",
            "CURE_CHUNKHOUND_DRY_RUN",
            "PYTHONSAFEPATH",
        ),
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
    _ensure_text_cli_live_progress(progress=progress, provider="claude", label="Claude CLI started.")
    claude_events_log_path = _resolve_claude_events_log_path(progress=progress, repo_dir=repo_dir)
    stream_state: dict[str, Any] = {"content": ""}
    policy = runtime_policy if isinstance(runtime_policy, dict) else {}
    staged_paths = policy.get("staged_paths") if isinstance(policy.get("staged_paths"), dict) else {}
    staged_helper_path = str(
        staged_paths.get("chunkhound_helper")
        or env.get(_CURE_CHUNKHOUND_HELPER_ENV)
        or ""
    ).strip()
    try:
        result = _run_logged_text_command(
            cmd=cmd,
            cwd=repo_dir,
            env=env,
            claude_json_events_path=claude_events_log_path,
            stream_text_callback=lambda chunk: _handle_claude_stream_chunk(
                progress=progress,
                state=stream_state,
                chunk=chunk,
            ),
        )
    except Exception:
        _finalize_text_cli_live_progress(progress=progress, provider="claude", status="error")
        raise
    _finalize_text_cli_live_progress(progress=progress, provider="claude", status="done")
    payload = _parse_claude_stream_payload(result.stdout)
    streamed_text = str(stream_state.get("content") or "").strip()
    text = str(payload.get("result") or "").strip()
    if not text:
        assistant_text = _extract_claude_text_from_message(payload.get("message"))
        text = str(streamed_text or assistant_text or result.stdout or "").strip()
    if not text:
        raise ReviewflowError("Claude did not return any printable review output.")
    output_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
    usage = _extract_usage_from_payload(payload)
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
    return LlmRunResult(
        resume=resume,
        adapter_meta={
            "transport": "cli-claude",
            "provider": "claude",
            "model": str(payload.get("model") or "").strip() or None,
            "command": safe_cmd_for_meta(cmd),
            "usage": usage,
            "chunkhound_tool_proof_entries": list(stream_state.get("chunkhound_tool_proof_entries") or []),
            "chunkhound_helper_path": staged_helper_path or None,
        },
    )


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
    usage = _extract_usage_from_payload(payload)
    return LlmRunResult(
        resume=None,
        adapter_meta={
            "transport": "http-responses",
            "status_code": status_code,
            "url": request_meta["url"],
            "response_id": str(payload.get("id") or "").strip() or None,
            "usage": usage,
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
                "usage": _extract_codex_usage_from_event_slice(
                    events_path=result.events_log_path,
                    start_offset=result.events_start_offset,
                    end_offset=result.events_end_offset,
                ),
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
        _raise_removed_gemini_support(context="Gemini CLI execution is no longer available.")
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
import os
import select
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_DIR = Path({json.dumps(str(repo_root))})
CHUNKHOUND_CWD = Path({json.dumps(str(helper_cwd))})
CHUNKHOUND_CONFIG = Path({json.dumps(str(helper_cfg))})
CHUNKHOUND_DB = Path({json.dumps(str(helper_db))})
HELPER_PATH = Path(__file__).resolve()
CHUNKHOUND_BIN = shutil.which("chunkhound") or "chunkhound"
_STDERR_TAIL_MAX = 16000
_HEARTBEAT_INTERVAL_SECONDS = 10.0
_PREFLIGHT_STAGE_TIMEOUTS = {{
    "spawn": 3.0,
    "initialize": 10.0,
    "notifications/initialized": 5.0,
    "tools/list": 10.0,
    "daemon_metadata": 5.0,
}}
_TOOL_CALL_TIMEOUTS = {{
    "search": 15.0,
    "code_research": 1200.0,
}}
_TRANSPORT_MODES = ("json_line", "mcp_framed")
DAEMON_METADATA_PROBE = "\\n".join(
    [
        "import json",
        "import sys",
        "from pathlib import Path",
        "payload = dict(ok=False, daemon_lock_path='', daemon_log_path='', daemon_socket_path='', daemon_pid=None, daemon_runtime_dir='', daemon_registry_entry_path='', chunkhound_runtime_python=sys.executable, chunkhound_module_path='', daemon_metadata_error='')",
        "try:",
        "    import chunkhound",
        "    from chunkhound.daemon.discovery import DaemonDiscovery",
        "    repo_dir = Path(sys.argv[1]).resolve()",
        "    discovery = DaemonDiscovery(repo_dir)",
        "    payload['ok'] = True",
        "    payload['daemon_lock_path'] = str(discovery.get_lock_path())",
        "    payload['daemon_log_path'] = str(discovery.get_lock_path().with_name('daemon.log'))",
        "    payload['daemon_runtime_dir'] = str(discovery.get_runtime_dir())",
        "    payload['daemon_registry_entry_path'] = str(discovery.get_registry_entry_path())",
        "    payload['chunkhound_module_path'] = str(Path(chunkhound.__file__).resolve())",
        "    lock = discovery.read_lock() or dict()",
        "    payload['daemon_socket_path'] = str(lock.get('socket_path') or '')",
        "    payload['daemon_pid'] = lock.get('pid')",
        "except Exception as exc:",
        "    payload['daemon_metadata_error'] = str(exc)",
        "print(json.dumps(payload, sort_keys=True))",
    ]
)


def _emit(payload: dict[str, Any], *, exit_code: int) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\\n")
    sys.stdout.flush()
    return exit_code


def _read_lock(path_text: str) -> dict[str, Any]:
    raw = str(path_text or "").strip()
    if not raw:
        return {{}}
    lock_path = Path(raw)
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {{}}
    except Exception:
        return {{}}


def _trim_tail_text(text: str, *, max_chars: int = 4000) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _emit_stage(
    stage: str,
    status: str,
    *,
    detail: str | None = None,
    enabled: bool = True,
) -> None:
    if not enabled:
        return
    message = f"preflight stage={{stage}} status={{status}}"
    detail_text = " ".join(str(detail or "").split())
    if detail_text:
        detail_text = _trim_tail_text(detail_text, max_chars=240)
        message += f" detail={{detail_text}}"
    sys.stderr.write(message + "\\n")
    sys.stderr.flush()


def _dry_run_enabled() -> bool:
    return str(os.environ.get("CURE_CHUNKHOUND_DRY_RUN") or "").strip().lower() in {"1", "true", "yes", "on"}


def _dry_run_stage_trace(*, command: str) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = [
        {{"stage": "initialize", "status": "ok", "elapsed_seconds": 0.0}},
        {{"stage": "notifications/initialized", "status": "ok", "elapsed_seconds": 0.0}},
        {{"stage": "tools/list", "status": "ok", "elapsed_seconds": 0.0}},
    ]
    if command != "preflight":
        trace.append({{"stage": "tools/call", "status": "ok", "elapsed_seconds": 0.0}})
    return trace


def _dry_run_payload(args: argparse.Namespace) -> dict[str, Any]:
    command = str(args.command or "").strip()
    helper_path = str(HELPER_PATH)
    if command == "preflight":
        return {{
            "ok": True,
            "command": "preflight",
            "helper_path": helper_path,
            "available_tools": ["search", "code_research"],
            "preflight_stage": "tools/list",
            "preflight_stage_status": "ok",
            "stage_trace": _dry_run_stage_trace(command="preflight"),
            "elapsed_seconds": 0.0,
            "helper_exit_code": 0,
            "mcp_transport": "dry_run",
            "dry_run": True,
        }}
    if command == "search":
        return {{
            "ok": True,
            "command": "search",
            "tool_name": "search",
            "query": getattr(args, "query", None),
            "path": getattr(args, "path", None),
            "helper_path": helper_path,
            "result": {{
                "results": [],
                "pagination": {{
                    "offset": int(getattr(args, "offset", 0) or 0),
                    "page_size": int(getattr(args, "page_size", 10) or 10),
                    "total_results": 0,
                }},
            }},
            "execution_stage": "tools/call",
            "execution_stage_status": "ok",
            "stage_trace": _dry_run_stage_trace(command=command),
            "mcp_transport": "dry_run",
            "dry_run": True,
        }}
    return {{
        "ok": True,
        "command": "research",
        "tool_name": "code_research",
        "query": getattr(args, "query", None),
        "path": getattr(args, "path", None),
        "helper_path": helper_path,
        "result": {{
            "summary": "dry-run ChunkHound research stub; no real ChunkHound call was made.",
        }},
        "execution_stage": "tools/call",
        "execution_stage_status": "ok",
        "stage_trace": _dry_run_stage_trace(command=command),
        "mcp_transport": "dry_run",
        "dry_run": True,
    }}


def _base_cmd() -> list[str]:
    return [CHUNKHOUND_BIN, "mcp", "--config", str(CHUNKHOUND_CONFIG), str(REPO_DIR)]


def _chunkhound_runtime_cmd() -> list[str] | None:
    if CHUNKHOUND_BIN == "chunkhound":
        return None
    launcher = Path(CHUNKHOUND_BIN)
    try:
        first_line = launcher.read_text(encoding="utf-8").splitlines()[0].strip()
    except Exception:
        return None
    if not first_line.startswith("#!"):
        return None
    shebang = first_line[2:].strip()
    if not shebang:
        return None
    try:
        cmd = shlex.split(shebang)
    except ValueError:
        return None
    return cmd or None


def _daemon_metadata_payload(*, timeout_seconds: float) -> dict[str, Any]:
    payload: dict[str, Any] = {{
        "chunkhound_path": str(CHUNKHOUND_BIN),
        "chunkhound_runtime_python": "",
        "chunkhound_module_path": "",
        "daemon_lock_path": "",
        "daemon_socket_path": "",
        "daemon_log_path": "",
        "daemon_pid": None,
        "daemon_runtime_dir": "",
        "daemon_registry_entry_path": "",
        "daemon_metadata_error": "",
    }}
    runtime_cmd = _chunkhound_runtime_cmd()
    if runtime_cmd is None:
        payload["daemon_metadata_error"] = "unable to resolve chunkhound runtime interpreter"
        return payload
    env = os.environ.copy()
    env["PYTHONSAFEPATH"] = "1"
    try:
        result = subprocess.run(
            runtime_cmd + ["-c", DAEMON_METADATA_PROBE, str(REPO_DIR)],
            cwd=str(CHUNKHOUND_CWD),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=float(timeout_seconds),
        )
    except subprocess.TimeoutExpired:
        payload["daemon_metadata_error"] = f"chunkhound runtime probe timed out after {{float(timeout_seconds):.1f}}s"
        return payload
    except Exception as exc:
        payload["daemon_metadata_error"] = str(exc)
        return payload
    stdout_text = str(result.stdout or "").strip()
    if not stdout_text:
        stderr_text = str(result.stderr or "").strip()
        payload["daemon_metadata_error"] = stderr_text or "chunkhound runtime probe returned no output"
        return payload
    try:
        parsed = json.loads(stdout_text)
    except Exception:
        payload["daemon_metadata_error"] = "chunkhound runtime probe returned malformed JSON"
        return payload
    if not isinstance(parsed, dict):
        payload["daemon_metadata_error"] = "chunkhound runtime probe returned a non-object payload"
        return payload
    for key in payload:
        if key in parsed:
            payload[key] = parsed.get(key)
    lock_payload = _read_lock(str(payload.get("daemon_lock_path") or ""))
    if not str(payload.get("daemon_socket_path") or "").strip():
        payload["daemon_socket_path"] = str(lock_payload.get("socket_path") or "")
    if payload.get("daemon_pid") is None:
        payload["daemon_pid"] = lock_payload.get("pid")
    if not str(payload.get("daemon_log_path") or "").strip() and str(payload.get("daemon_lock_path") or "").strip():
        payload["daemon_log_path"] = str(Path(str(payload["daemon_lock_path"])).with_name("daemon.log"))
    return payload


class PreflightStageError(RuntimeError):
    def __init__(
        self,
        stage: str,
        detail: str,
        *,
        timeout: bool = False,
        stderr_tail: str = "",
    ) -> None:
        super().__init__(detail)
        self.stage = str(stage or "").strip() or "unknown"
        self.timeout = bool(timeout)
        self.stderr_tail = _trim_tail_text(stderr_tail)


class JsonRpcSession:
    def __init__(self, *, transport_mode: str = "json_line") -> None:
        self._next_id = 1
        self._transport_mode = str(transport_mode or "").strip() or "json_line"
        if self._transport_mode not in _TRANSPORT_MODES:
            raise ValueError(f"unsupported transport mode: {{self._transport_mode}}")
        env = os.environ.copy()
        env["PYTHONSAFEPATH"] = "1"
        self.proc = subprocess.Popen(
            _base_cmd(),
            cwd=str(CHUNKHOUND_CWD),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            env=env,
        )
        if self.proc.stdin is None or self.proc.stdout is None or self.proc.stderr is None:
            raise RuntimeError("chunkhound mcp stdio pipes are unavailable")
        self._stdout_buffer = bytearray()
        self._stderr_buffer = bytearray()
        self._stdout_open = True
        self._stderr_open = True

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

    def _stderr_tail_text(self) -> str:
        if not self._stderr_buffer:
            return ""
        return _trim_tail_text(self._stderr_buffer.decode("utf-8", errors="replace"))

    def _append_stderr(self, data: bytes) -> None:
        if not data:
            return
        self._stderr_buffer.extend(data)
        if len(self._stderr_buffer) > _STDERR_TAIL_MAX:
            del self._stderr_buffer[:-_STDERR_TAIL_MAX]

    def _stage_error(self, stage: str, detail: str, *, timeout: bool = False) -> PreflightStageError:
        return PreflightStageError(stage, detail, timeout=timeout, stderr_tail=self._stderr_tail_text())

    def _drain_ready_io(self, *, timeout_seconds: float) -> bool:
        readable: list[object]
        readable, _, _ = select.select(
            [stream for stream, is_open in ((self.proc.stdout, self._stdout_open), (self.proc.stderr, self._stderr_open)) if is_open],
            [],
            [],
            max(0.0, float(timeout_seconds)),
        )
        saw_data = False
        for stream in readable:
            try:
                chunk = os.read(stream.fileno(), 65536)
            except OSError:
                chunk = b""
            if stream is self.proc.stdout:
                if chunk:
                    self._stdout_buffer.extend(chunk)
                    saw_data = True
                else:
                    self._stdout_open = False
            else:
                if chunk:
                    self._append_stderr(chunk)
                    saw_data = True
                else:
                    self._stderr_open = False
        return saw_data

    def _try_extract_framed_message(self) -> dict[str, Any] | None:
        if not self._stdout_buffer:
            return None
        header_end = self._stdout_buffer.find(b"\\r\\n\\r\\n")
        delimiter_len = 4
        if header_end < 0:
            header_end = self._stdout_buffer.find(b"\\n\\n")
            delimiter_len = 2
        if header_end < 0:
            return None
        headers_blob = bytes(self._stdout_buffer[:header_end]).decode("utf-8", errors="replace")
        headers: dict[str, str] = {{}}
        for raw_line in headers_blob.splitlines():
            key, sep, value = raw_line.partition(":")
            if not sep:
                raise RuntimeError("invalid MCP header line")
            headers[key.strip().lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except Exception as exc:
            raise RuntimeError("invalid MCP content-length header") from exc
        body_start = header_end + delimiter_len
        body_end = body_start + length
        if len(self._stdout_buffer) < body_end:
            return None
        body = bytes(self._stdout_buffer[body_start:body_end])
        del self._stdout_buffer[:body_end]
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected MCP payload type")
        return payload

    def _try_extract_json_line_message(self) -> dict[str, Any] | None:
        if not self._stdout_buffer:
            return None
        newline_idx = self._stdout_buffer.find(b"\\n")
        if newline_idx < 0:
            return None
        raw_line = bytes(self._stdout_buffer[: newline_idx + 1])
        del self._stdout_buffer[: newline_idx + 1]
        line = raw_line.strip()
        if not line:
            return None
        payload = json.loads(line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected JSON-RPC payload type")
        return payload

    def _try_extract_message(self) -> dict[str, Any] | None:
        while self._stdout_buffer[:1] in (b"\\r", b"\\n", b" ", b"\\t"):
            del self._stdout_buffer[:1]
        if not self._stdout_buffer:
            return None
        if self._stdout_buffer.startswith(b"Content-Length:"):
            return self._try_extract_framed_message()
        if self._stdout_buffer[:1] in (b"{{", b"["):
            return self._try_extract_json_line_message()
        if b"\\r\\n\\r\\n" in self._stdout_buffer or b"\\n\\n" in self._stdout_buffer:
            return self._try_extract_framed_message()
        newline_idx = self._stdout_buffer.find(b"\\n")
        if newline_idx < 0:
            return None
        preview = bytes(self._stdout_buffer[: newline_idx + 1]).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"unexpected chunkhound mcp stdout: {{_trim_tail_text(preview, max_chars=240)}}")

    def _closed_stream_detail(self, stage: str) -> str:
        detail = self._stderr_tail_text()
        exit_code = self.proc.poll()
        if exit_code is not None:
            if detail:
                return f"chunkhound mcp exited during {{stage}} with status {{exit_code}}: {{detail}}"
            return f"chunkhound mcp exited during {{stage}} with status {{exit_code}}"
        if detail:
            return f"chunkhound mcp closed stdout during {{stage}}: {{detail}}"
        return f"chunkhound mcp closed its stdio stream during {{stage}}"

    def _remaining_timeout(self, *, stage: str, timeout_seconds: float, deadline: float) -> float:
        remaining = float(deadline) - time.monotonic()
        if remaining <= 0:
            raise self._stage_error(
                stage,
                f"timed out after {{float(timeout_seconds):.1f}}s waiting for stage {{stage}}",
                timeout=True,
            )
        return remaining

    def _read_message(
        self,
        *,
        stage: str,
        timeout_seconds: float,
        deadline: float,
        heartbeat_enabled: bool = False,
    ) -> dict[str, Any]:
        last_heartbeat_at = time.monotonic()
        while True:
            message = self._try_extract_message()
            if message is not None:
                return message
            if not self._stdout_open:
                raise self._stage_error(stage, self._closed_stream_detail(stage))
            if heartbeat_enabled:
                now = time.monotonic()
                if now - last_heartbeat_at >= _HEARTBEAT_INTERVAL_SECONDS:
                    elapsed = max(0.0, float(timeout_seconds) - max(0.0, float(deadline) - now))
                    try:
                        sys.stdout.write(f"cure-chunkhound: tools/call waiting ({{elapsed:.1f}}s elapsed)\\n")
                        sys.stdout.flush()
                    except Exception:
                        pass
                    last_heartbeat_at = now
            remaining = self._remaining_timeout(
                stage=stage,
                timeout_seconds=timeout_seconds,
                deadline=deadline,
            )
            self._drain_ready_io(timeout_seconds=min(0.2, remaining))

    def _write_message(self, payload: dict[str, Any], *, stage: str) -> None:
        raw = json.dumps(payload).encode("utf-8")
        if self._transport_mode == "json_line":
            message = raw + b"\\n"
        else:
            message = f"Content-Length: {{len(raw)}}\\r\\n\\r\\n".encode("utf-8") + raw
        try:
            self.proc.stdin.write(message)
            self.proc.stdin.flush()
        except Exception as exc:
            raise self._stage_error(stage, f"failed to write MCP request during {{stage}}: {{exc}}")

    def ensure_started(self, *, stage: str, timeout_seconds: float, deadline: float | None = None) -> None:
        active_deadline = (
            float(deadline)
            if deadline is not None
            else (time.monotonic() + max(0.0, float(timeout_seconds)))
        )
        if self.proc.poll() is not None:
            raise self._stage_error(stage, self._closed_stream_detail(stage))
        remaining = self._remaining_timeout(
            stage=stage,
            timeout_seconds=timeout_seconds,
            deadline=active_deadline,
        )
        self._drain_ready_io(timeout_seconds=min(0.05, remaining))
        if self.proc.poll() is not None:
            raise self._stage_error(stage, self._closed_stream_detail(stage))

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        stage: str,
        timeout_seconds: float,
        heartbeat_enabled: bool = False,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        self.ensure_started(stage=stage, timeout_seconds=timeout_seconds, deadline=deadline)
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {{"jsonrpc": "2.0", "id": request_id, "method": method}}
        if params is not None:
            payload["params"] = params
        self._write_message(payload, stage=stage)
        while True:
            message = self._read_message(
                stage=stage,
                timeout_seconds=timeout_seconds,
                deadline=deadline,
                heartbeat_enabled=heartbeat_enabled,
            )
            if message.get("id") == request_id:
                return message

    def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        stage: str,
        timeout_seconds: float,
    ) -> None:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        self.ensure_started(stage=stage, timeout_seconds=timeout_seconds, deadline=deadline)
        payload: dict[str, Any] = {{"jsonrpc": "2.0", "method": method}}
        if params is not None:
            payload["params"] = params
        self._write_message(payload, stage=stage)


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


def _stage_trace_entry(
    *,
    stage: str,
    status: str,
    started_at: float,
    timeout_seconds: float | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {{
        "stage": stage,
        "status": status,
        "elapsed_seconds": round(max(0.0, time.monotonic() - started_at), 3),
    }}
    if timeout_seconds is not None:
        entry["timeout_seconds"] = float(timeout_seconds)
    detail_text = _trim_tail_text(detail or "")
    if detail_text:
        entry["detail"] = detail_text
    return entry


def _build_preflight_payload(
    *,
    ok: bool,
    error: str = "",
    available_tools: list[str] | None = None,
    missing_tools: list[str] | None = None,
    preflight_stage: str,
    preflight_stage_status: str,
    stage_trace: list[dict[str, Any]],
    started_at: float,
    daemon_meta: dict[str, Any] | None = None,
    stderr_tail: str = "",
) -> dict[str, Any]:
    daemon_meta = daemon_meta or {{}}
    payload = {{
        "ok": bool(ok),
        "command": "preflight",
        "available_tools": sorted(str(tool).strip() for tool in (available_tools or []) if str(tool).strip()),
        "helper_path": str(HELPER_PATH),
        "chunkhound_path": str(daemon_meta.get("chunkhound_path") or ""),
        "chunkhound_runtime_python": str(daemon_meta.get("chunkhound_runtime_python") or ""),
        "chunkhound_module_path": str(daemon_meta.get("chunkhound_module_path") or ""),
        "daemon_lock_path": str(daemon_meta.get("daemon_lock_path") or ""),
        "daemon_socket_path": str(daemon_meta.get("daemon_socket_path") or ""),
        "daemon_log_path": str(daemon_meta.get("daemon_log_path") or ""),
        "daemon_pid": daemon_meta.get("daemon_pid"),
        "daemon_runtime_dir": str(daemon_meta.get("daemon_runtime_dir") or ""),
        "daemon_registry_entry_path": str(daemon_meta.get("daemon_registry_entry_path") or ""),
        "chunkhound_command": _base_cmd(),
        "preflight_stage": str(preflight_stage or "").strip() or "unknown",
        "preflight_stage_status": str(preflight_stage_status or "").strip() or "unknown",
        "stage_trace": list(stage_trace),
        "elapsed_seconds": round(max(0.0, time.monotonic() - started_at), 3),
    }}
    error_text = _trim_tail_text(error)
    if error_text:
        payload["error"] = error_text
    missing = sorted(str(name).strip() for name in (missing_tools or []) if str(name).strip())
    if missing:
        payload["missing_tools"] = missing
    stderr_text = _trim_tail_text(stderr_tail)
    if stderr_text:
        payload["stderr_tail"] = stderr_text
    daemon_metadata_error = str(daemon_meta.get("daemon_metadata_error") or "").strip()
    if daemon_metadata_error:
        payload["daemon_metadata_error"] = daemon_metadata_error
    return payload


def _tool_name_for_command(command: str) -> str:
    return "code_research" if str(command or "").strip() == "research" else "search"


def _tool_timeout_seconds(tool_name: str) -> float:
    raw_timeout = _TOOL_CALL_TIMEOUTS.get(str(tool_name or "").strip(), _TOOL_CALL_TIMEOUTS["search"])
    return float(raw_timeout)


def _copy_stage_trace(trace: object) -> list[dict[str, Any]]:
    if not isinstance(trace, list):
        return []
    return [dict(item) for item in trace if isinstance(item, dict)]


def _tool_payload_base(
    *,
    args: argparse.Namespace,
    preflight: dict[str, Any],
    transport_mode: str,
    tool_name: str,
    stage_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {{
        "command": args.command,
        "tool_name": tool_name,
        "query": getattr(args, "query", None),
        "path": getattr(args, "path", None),
        "helper_path": str(HELPER_PATH),
        "chunkhound_path": str(preflight.get("chunkhound_path") or ""),
        "chunkhound_runtime_python": str(preflight.get("chunkhound_runtime_python") or ""),
        "chunkhound_module_path": str(preflight.get("chunkhound_module_path") or ""),
        "daemon_lock_path": preflight.get("daemon_lock_path"),
        "daemon_socket_path": preflight.get("daemon_socket_path"),
        "daemon_log_path": preflight.get("daemon_log_path"),
        "daemon_pid": preflight.get("daemon_pid"),
        "daemon_runtime_dir": preflight.get("daemon_runtime_dir"),
        "daemon_registry_entry_path": preflight.get("daemon_registry_entry_path"),
        "mcp_transport": transport_mode,
        "preflight_stage": str(preflight.get("preflight_stage") or ""),
        "preflight_stage_status": str(preflight.get("preflight_stage_status") or ""),
        "stage_trace": stage_trace,
    }}
    preflight_elapsed = preflight.get("elapsed_seconds")
    if isinstance(preflight_elapsed, (int, float)):
        payload["preflight_elapsed_seconds"] = round(float(preflight_elapsed), 3)
    stderr_tail = _trim_tail_text(preflight.get("stderr_tail") or "")
    if stderr_tail:
        payload["stderr_tail"] = stderr_tail
    daemon_metadata_error = str(preflight.get("daemon_metadata_error") or "").strip()
    if daemon_metadata_error:
        payload["daemon_metadata_error"] = daemon_metadata_error
    return payload


def _run_preflight(
    session: JsonRpcSession,
    args: argparse.Namespace,
    *,
    emit_stage_lines: bool = True,
) -> dict[str, Any]:
    _ = args
    started_at = time.monotonic()
    stage_trace: list[dict[str, Any]] = []

    def _run_stage(
        stage: str,
        timeout_seconds: float,
        func: Any,
    ) -> tuple[bool, Any]:
        stage_started = time.monotonic()
        _emit_stage(stage, "running", enabled=emit_stage_lines)
        try:
            result = func()
        except PreflightStageError as exc:
            status = "timeout" if exc.timeout else "error"
            detail = str(exc)
            _emit_stage(stage, status, detail=detail, enabled=emit_stage_lines)
            stage_trace.append(
                _stage_trace_entry(
                    stage=stage,
                    status=status,
                    started_at=stage_started,
                    timeout_seconds=timeout_seconds,
                    detail=detail,
                )
            )
            daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
            return (
                False,
                _build_preflight_payload(
                    ok=False,
                    error=detail,
                    preflight_stage=stage,
                    preflight_stage_status=status,
                    stage_trace=stage_trace,
                    started_at=started_at,
                    daemon_meta=daemon_meta,
                    stderr_tail=exc.stderr_tail,
                ),
            )
        except Exception as exc:
            detail = str(exc)
            _emit_stage(stage, "error", detail=detail, enabled=emit_stage_lines)
            stage_trace.append(
                _stage_trace_entry(
                    stage=stage,
                    status="error",
                    started_at=stage_started,
                    timeout_seconds=timeout_seconds,
                    detail=detail,
                )
            )
            daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
            return (
                False,
                _build_preflight_payload(
                    ok=False,
                    error=detail,
                    preflight_stage=stage,
                    preflight_stage_status="error",
                    stage_trace=stage_trace,
                    started_at=started_at,
                    daemon_meta=daemon_meta,
                    stderr_tail=session._stderr_tail_text(),
                ),
            )
        _emit_stage(stage, "ok", enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage=stage,
                status="ok",
                started_at=stage_started,
                timeout_seconds=timeout_seconds,
            )
        )
        return True, result

    ok, _ = _run_stage(
        "spawn",
        _PREFLIGHT_STAGE_TIMEOUTS["spawn"],
        lambda: session.ensure_started(stage="spawn", timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["spawn"]),
    )
    if not ok:
        return _

    ok, init_response = _run_stage(
        "initialize",
        _PREFLIGHT_STAGE_TIMEOUTS["initialize"],
        lambda: session.request(
            "initialize",
            {{
                "protocolVersion": "2025-03-26",
                "capabilities": {{}},
                "clientInfo": {{"name": "cure-chunkhound-helper", "version": "1"}},
            }},
            stage="initialize",
            timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["initialize"],
        ),
    )
    if not ok:
        return init_response
    if "error" in init_response:
        detail = json.dumps(init_response["error"], sort_keys=True)
        _emit_stage("initialize", "error", detail=detail, enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="initialize",
                status="error",
                started_at=started_at,
                timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["initialize"],
                detail=detail,
            )
        )
        daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
        return _build_preflight_payload(
            ok=False,
            error=detail,
            preflight_stage="initialize",
            preflight_stage_status="error",
            stage_trace=stage_trace,
            started_at=started_at,
            daemon_meta=daemon_meta,
            stderr_tail=session._stderr_tail_text(),
        )

    ok, notify_result = _run_stage(
        "notifications/initialized",
        _PREFLIGHT_STAGE_TIMEOUTS["notifications/initialized"],
        lambda: session.notify(
            "notifications/initialized",
            {{}},
            stage="notifications/initialized",
            timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["notifications/initialized"],
        ),
    )
    if not ok:
        return notify_result

    ok, tools_response = _run_stage(
        "tools/list",
        _PREFLIGHT_STAGE_TIMEOUTS["tools/list"],
        lambda: session.request(
            "tools/list",
            {{}},
            stage="tools/list",
            timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["tools/list"],
        ),
    )
    if not ok:
        return tools_response
    if "error" in tools_response:
        detail = json.dumps(tools_response["error"], sort_keys=True)
        _emit_stage("tools/list", "error", detail=detail, enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="tools/list",
                status="error",
                started_at=started_at,
                timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["tools/list"],
                detail=detail,
            )
        )
        daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
        return _build_preflight_payload(
            ok=False,
            error=detail,
            preflight_stage="tools/list",
            preflight_stage_status="error",
            stage_trace=stage_trace,
            started_at=started_at,
            daemon_meta=daemon_meta,
            stderr_tail=session._stderr_tail_text(),
        )

    tools_payload = tools_response.get("result") if isinstance(tools_response.get("result"), dict) else {{}}
    tools = tools_payload.get("tools") if isinstance(tools_payload, dict) else []
    available = sorted(
        str(tool.get("name") or "").strip()
        for tool in tools
        if isinstance(tool, dict) and str(tool.get("name") or "").strip()
    )
    missing_tools = [name for name in ("search", "code_research") if name not in available]
    stage_started = time.monotonic()
    _emit_stage("tool_validation", "running", enabled=emit_stage_lines)
    if missing_tools:
        detail = "required ChunkHound tools are unavailable: " + ", ".join(missing_tools)
        _emit_stage("tool_validation", "error", detail=detail, enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="tool_validation",
                status="error",
                started_at=stage_started,
                detail=detail,
            )
        )
        daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
        return _build_preflight_payload(
            ok=False,
            error=detail,
            available_tools=available,
            missing_tools=missing_tools,
            preflight_stage="tool_validation",
            preflight_stage_status="error",
            stage_trace=stage_trace,
            started_at=started_at,
            daemon_meta=daemon_meta,
            stderr_tail=session._stderr_tail_text(),
        )
    _emit_stage("tool_validation", "ok", enabled=emit_stage_lines)
    stage_trace.append(_stage_trace_entry(stage="tool_validation", status="ok", started_at=stage_started))

    stage_started = time.monotonic()
    _emit_stage("daemon_metadata", "running", enabled=emit_stage_lines)
    daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
    daemon_metadata_error = str(daemon_meta.get("daemon_metadata_error") or "").strip()
    if daemon_metadata_error:
        _emit_stage(
            "daemon_metadata",
            "error",
            detail=daemon_metadata_error,
            enabled=emit_stage_lines,
        )
        stage_trace.append(
            _stage_trace_entry(
                stage="daemon_metadata",
                status="error",
                started_at=stage_started,
                timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"],
                detail=daemon_metadata_error,
            )
        )
    else:
        _emit_stage("daemon_metadata", "ok", enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="daemon_metadata",
                status="ok",
                started_at=stage_started,
                timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"],
            )
        )

    _emit_stage("complete", "ok", enabled=emit_stage_lines)
    return _build_preflight_payload(
        ok=True,
        available_tools=available,
        preflight_stage="complete",
        preflight_stage_status="ok",
        stage_trace=stage_trace,
        started_at=started_at,
        daemon_meta=daemon_meta,
        stderr_tail=session._stderr_tail_text(),
    )


def _should_retry_with_alternate_transport(payload: dict[str, Any]) -> bool:
    if bool(payload.get("ok")):
        return False
    stage = str(payload.get("preflight_stage") or "").strip()
    status = str(payload.get("preflight_stage_status") or "").strip()
    return stage in {"initialize", "notifications/initialized", "tools/list"} and status in {"error", "timeout"}


def _run_preflight_once(args: argparse.Namespace, *, transport_mode: str) -> dict[str, Any]:
    session = JsonRpcSession(transport_mode=transport_mode)
    try:
        payload = _run_preflight(session, args)
    finally:
        session.close()
    payload["mcp_transport"] = transport_mode
    return payload


def _run_preflight_with_fallback(args: argparse.Namespace) -> dict[str, Any]:
    last_payload: dict[str, Any] | None = None
    for idx, transport_mode in enumerate(_TRANSPORT_MODES):
        payload = _run_preflight_once(args, transport_mode=transport_mode)
        if payload.get("ok"):
            return payload
        last_payload = payload
        if idx + 1 >= len(_TRANSPORT_MODES) or not _should_retry_with_alternate_transport(payload):
            return payload
    return last_payload or {{"ok": False, "command": "preflight", "error": "no transport modes available"}}


def _run_tool_once(args: argparse.Namespace, *, transport_mode: str) -> dict[str, Any]:
    session = JsonRpcSession(transport_mode=transport_mode)
    try:
        preflight = _run_preflight(session, args, emit_stage_lines=False)
        tool_name = _tool_name_for_command(args.command)
        if not preflight.get("ok"):
            return {{
                **preflight,
                "mcp_transport": transport_mode,
                "command": args.command,
                "tool_name": tool_name,
                "query": getattr(args, "query", None),
                "path": getattr(args, "path", None),
            }}
        tool_name, payload = _tool_payload(args)
        tool_timeout_seconds = _tool_timeout_seconds(tool_name)
        stage_trace = _copy_stage_trace(preflight.get("stage_trace"))
        stage_started = time.monotonic()
        base_payload = _tool_payload_base(
            args=args,
            preflight=preflight,
            transport_mode=transport_mode,
            tool_name=tool_name,
            stage_trace=stage_trace,
        )
        try:
            response = session.request(
                "tools/call",
                {{"name": tool_name, "arguments": payload}},
                stage="tools/call",
                timeout_seconds=tool_timeout_seconds,
                heartbeat_enabled=True,
            )
            result = _extract_result_content(response)
        except PreflightStageError as exc:
            stage_status = "timeout" if exc.timeout else "error"
            detail = str(exc)
            stage_trace.append(
                _stage_trace_entry(
                    stage="tools/call",
                    status=stage_status,
                    started_at=stage_started,
                    timeout_seconds=tool_timeout_seconds,
                    detail=detail,
                )
            )
            failure_payload = {{
                **base_payload,
                "ok": False,
                "error": detail,
                "execution_stage": "tools/call",
                "execution_stage_status": stage_status,
                "execution_timeout_seconds": tool_timeout_seconds,
            }}
            stderr_tail = _trim_tail_text(exc.stderr_tail)
            if stderr_tail:
                failure_payload["stderr_tail"] = stderr_tail
            return failure_payload
        except Exception as exc:
            detail = str(exc)
            stage_trace.append(
                _stage_trace_entry(
                    stage="tools/call",
                    status="error",
                    started_at=stage_started,
                    timeout_seconds=tool_timeout_seconds,
                    detail=detail,
                )
            )
            failure_payload = {{
                **base_payload,
                "ok": False,
                "error": detail,
                "execution_stage": "tools/call",
                "execution_stage_status": "error",
                "execution_timeout_seconds": tool_timeout_seconds,
            }}
            stderr_tail = _trim_tail_text(session._stderr_tail_text())
            if stderr_tail:
                failure_payload["stderr_tail"] = stderr_tail
            return failure_payload
        stage_trace.append(
            _stage_trace_entry(
                stage="tools/call",
                status="ok",
                started_at=stage_started,
                timeout_seconds=tool_timeout_seconds,
            )
        )
        return {{
            **base_payload,
            "ok": True,
            "result": result,
            "execution_stage": "tools/call",
            "execution_stage_status": "ok",
            "execution_timeout_seconds": tool_timeout_seconds,
        }}
    finally:
        session.close()


def _run_tool(args: argparse.Namespace) -> dict[str, Any]:
    last_payload: dict[str, Any] | None = None
    for idx, transport_mode in enumerate(_TRANSPORT_MODES):
        payload = _run_tool_once(args, transport_mode=transport_mode)
        if payload.get("ok"):
            return payload
        last_payload = payload
        if idx + 1 >= len(_TRANSPORT_MODES) or not _should_retry_with_alternate_transport(payload):
            return payload
    return last_payload or {{
        "ok": False,
        "command": args.command,
        "tool_name": "code_research" if args.command == "research" else "search",
        "query": getattr(args, "query", None),
        "path": getattr(args, "path", None),
        "error": "no transport modes available",
    }}


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
    if _dry_run_enabled():
        return _emit(_dry_run_payload(args), exit_code=0)
    if args.command == "preflight":
        try:
            payload = _run_preflight_with_fallback(args)
        except Exception as exc:
            daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
            return _emit({{
                "ok": False,
                "command": "preflight",
                "error": str(exc),
                "helper_path": str(HELPER_PATH),
                "chunkhound_path": str(daemon_meta.get("chunkhound_path") or ""),
                "chunkhound_runtime_python": str(daemon_meta.get("chunkhound_runtime_python") or ""),
                "chunkhound_module_path": str(daemon_meta.get("chunkhound_module_path") or ""),
                "daemon_lock_path": str(daemon_meta.get("daemon_lock_path") or ""),
                "daemon_socket_path": str(daemon_meta.get("daemon_socket_path") or ""),
                "daemon_log_path": str(daemon_meta.get("daemon_log_path") or ""),
                "daemon_pid": daemon_meta.get("daemon_pid"),
                "daemon_runtime_dir": str(daemon_meta.get("daemon_runtime_dir") or ""),
                "daemon_registry_entry_path": str(daemon_meta.get("daemon_registry_entry_path") or ""),
                "daemon_metadata_error": str(daemon_meta.get("daemon_metadata_error") or ""),
            }}, exit_code=1)
        return _emit(payload, exit_code=0 if payload.get("ok") else 1)
    try:
        payload = _run_tool(args)
        return _emit(payload, exit_code=0 if payload.get("ok") else 1)
    except Exception as exc:
        daemon_meta = _daemon_metadata_payload(timeout_seconds=_PREFLIGHT_STAGE_TIMEOUTS["daemon_metadata"])
        return _emit({{
            "ok": False,
            "command": args.command,
            "tool_name": "code_research" if args.command == "research" else "search",
            "query": getattr(args, "query", None),
            "path": getattr(args, "path", None),
            "error": str(exc),
            "helper_path": str(HELPER_PATH),
            "chunkhound_path": str(daemon_meta.get("chunkhound_path") or ""),
            "chunkhound_runtime_python": str(daemon_meta.get("chunkhound_runtime_python") or ""),
            "chunkhound_module_path": str(daemon_meta.get("chunkhound_module_path") or ""),
            "daemon_lock_path": str(daemon_meta.get("daemon_lock_path") or ""),
            "daemon_socket_path": str(daemon_meta.get("daemon_socket_path") or ""),
            "daemon_log_path": str(daemon_meta.get("daemon_log_path") or ""),
            "daemon_pid": daemon_meta.get("daemon_pid"),
            "daemon_runtime_dir": str(daemon_meta.get("daemon_runtime_dir") or ""),
            "daemon_registry_entry_path": str(daemon_meta.get("daemon_registry_entry_path") or ""),
            "daemon_metadata_error": str(daemon_meta.get("daemon_metadata_error") or ""),
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
    if provider == "gemini":
        _raise_removed_gemini_support(context="Gemini agent runtime preparation is no longer available.")
    profile, profile_source, _, runtime_meta = resolve_agent_runtime_profile(
        cli_value=getattr(args, "agent_runtime_profile", None),
        config_path=reviewflow_config_path,
        config_enabled=config_enabled,
    )
    env = build_curated_subprocess_env(extra_env=base_env)
    env = augment_cli_provider_session_env(env=env, provider=provider)
    env.update(_string_dict(resolved.get("env")))
    env, staged_paths = _stage_review_auth_support(work_dir=work_dir, repo_dir=repo_dir, env=env)
    chunkhound_dry_run = bool(getattr(args, "dry_run_chunkhound", False))
    if chunkhound_dry_run:
        env[_CURE_CHUNKHOUND_DRY_RUN_ENV] = "1"
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
            "chunkhound_dry_run": chunkhound_dry_run,
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
            "chunkhound_dry_run": chunkhound_dry_run,
            "env_keys": sorted(env.keys()),
            "add_dirs": [str(path) for path in add_dirs],
            "staged_paths": dict(staged_paths),
        }
        return runtime

    command = _require_provider_command(str(resolved.get("command") or provider), provider=provider)
    runtime["command"] = command
    if provider == "codex":
        if enable_mcp:
            env["PYTHONSAFEPATH"] = "1"
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
        if profile == "permissive":
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
        if enable_mcp:
            env["PYTHONSAFEPATH"] = "1"
            chunkhound_helper = write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=chunkhound_config_path,
                chunkhound_db_path=chunkhound_db_path,
                chunkhound_cwd=chunkhound_cwd,
            )
            env[_CURE_CHUNKHOUND_HELPER_ENV] = str(chunkhound_helper)
            runtime["staged_paths"]["chunkhound_helper"] = str(chunkhound_helper)
        settings_path = _write_json_file(
            claude_dir / "settings.json",
            {
                "permissions": {
                    "allow": ["Bash"]
                }
            },
        )
        runtime["staged_paths"]["claude_settings"] = str(settings_path)
        provider_args: list[str] = ["--setting-sources", "user", "--settings", str(settings_path)]
        for add_dir in add_dirs:
            provider_args.extend(["--add-dir", str(add_dir)])
        if profile == "permissive":
            runtime["dangerously_skip_permissions"] = True
        else:
            raise ReviewflowError(f"Unsupported claude agent runtime profile: {profile!r}")
        if runtime["permission_mode"]:
            provider_args.extend(["--permission-mode", str(runtime["permission_mode"])])
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
        "chunkhound_dry_run": chunkhound_dry_run,
        "chunkhound_access_mode": (
            _CURE_CHUNKHOUND_ACCESS_MODE
            if provider in {"codex", "claude"} and bool(runtime["staged_paths"].get("chunkhound_helper"))
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
    for key in ("GH_CONFIG_DIR", "JIRA_CONFIG_FILE", "NETRC", "CURE_WORK_DIR", "CURE_CHUNKHOUND_DRY_RUN"):
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
