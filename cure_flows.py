from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from chunkhound_summary import parse_chunkhound_index_summary
from cure_citations import CITATION_CONTRACT_KEYS
from cure_errors import ReviewflowError
from cure_output import ChunkhoundLiveProgressReporter, _eprint, active_output, log
from cure_runtime import (
    ReviewIntelligenceConfig,
    build_review_intelligence_guidance,
    fingerprint_chunkhound_reviewflow_config,
    load_chunkhound_runtime_config,
    load_reviewflow_chunkhound_config,
)
from cure_sessions import PullRequestRef
from meta import json_fingerprint, write_json, write_redacted_json
from paths import (
    ReviewflowPaths,
    base_dir,
    default_reviewflow_config_path,
    repo_id_for_gh,
    seed_dir,
)
from run import ReviewflowSubprocessError, merged_env


def _reviewflow():
    import cure as rf

    return rf


def _run_cmd(cmd: list[str], **kwargs: Any):
    return _reviewflow().run_cmd(cmd, **kwargs)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


PR_BASELINE_MAX_AHEAD_COMMITS = 250
PR_BASELINE_MAX_BEHIND_COMMITS = 250
PR_BASELINE_MAX_CHANGED_FILES = 1500
PR_BASELINE_MAX_CHANGED_LINES = 100000
GITHUB_COMPARE_FILES_HARD_LIMIT = 300
DEFAULT_BASE_CACHE_TTL_HOURS = 24
CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS = 30

ChunkHoundToolRequirement = Literal["required", "guidance", "conditional"]


@dataclass(frozen=True)
class ChunkHoundPromptContract:
    search_requirement: ChunkHoundToolRequirement
    code_research_requirement: ChunkHoundToolRequirement
    availability_proof: str = "successful_execution"
    resource_discovery_rule: str = "neutral_expected_empty"


_BUILTIN_CHUNKHOUND_PROMPT_CONTRACTS: dict[str, ChunkHoundPromptContract] = {
    "default.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="required",
    ),
    "mrereview_gh_local.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="required",
    ),
    "mrereview_gh_local_big.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="required",
    ),
    "mrereview_gh_local_big_followup.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="required",
    ),
    "mrereview_gh_local_big_plan.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="required",
    ),
    "mrereview_gh_local_followup.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="guidance",
    ),
    "mrereview_gh_local_big_step.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="guidance",
    ),
    "mrereview_gh_local_big_synth.md": ChunkHoundPromptContract(
        search_requirement="conditional",
        code_research_requirement="conditional",
    ),
    "mrereview_gh_local_big_resume_plan.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="required",
    ),
    "mrereview_gh_local_big_resume_step.md": ChunkHoundPromptContract(
        search_requirement="required",
        code_research_requirement="guidance",
    ),
    "mrereview_gh_local_big_resume_synth.md": ChunkHoundPromptContract(
        search_requirement="conditional",
        code_research_requirement="conditional",
    ),
}


@contextlib.contextmanager
def phase(name: str, *, progress: Any | None = None, quiet: bool):
    started = time.perf_counter()
    if progress is not None:
        progress.phase_started(name)
    log(f"START {name}", quiet=quiet)
    ok = False
    try:
        yield
        ok = True
    finally:
        duration = time.perf_counter() - started
        if progress is not None:
            progress.phase_finished(name, duration_seconds=duration, ok=ok)
        if ok:
            log(f"DONE  {name} ({duration:.1f}s)", quiet=quiet)
        else:
            log(f"FAIL  {name} ({duration:.1f}s)", quiet=quiet)


@contextlib.contextmanager
def file_lock(lock_path: Path, *, quiet: bool):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as fh:
        log(f"LOCK  {lock_path}", quiet=quiet)
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            log(f"UNLOCK {lock_path}", quiet=quiet)


def load_embedding_api_key_from_config(*, source_config_path: Path | None = None) -> str | None:
    if source_config_path is None:
        return None
    try:
        raw = json.loads(source_config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None

    embedding = raw.get("embedding")
    if not isinstance(embedding, dict):
        return None
    api_key = embedding.get("api_key")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    return None


def _has_embedding_config(
    *,
    resolved_config: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    source_env = env if env is not None else os.environ
    for key in ("CHUNKHOUND_EMBEDDING__API_KEY", "VOYAGE_API_KEY", "OPENAI_API_KEY"):
        if str(source_env.get(key) or "").strip():
            return True
    if not isinstance(resolved_config, dict):
        return False
    embedding = resolved_config.get("embedding")
    if not isinstance(embedding, dict):
        return False
    return any(str(value).strip() for value in embedding.values() if value is not None)


def _persist_discovered_embedding_config(
    *,
    base_config_path: Path,
    discovered_config_path: Path,
) -> bool:
    try:
        discovered_raw = json.loads(discovered_config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewflowError(
            f"Failed to read discovered ChunkHound config at {discovered_config_path}: {exc}"
        ) from exc

    discovered_embedding = (
        discovered_raw.get("embedding") if isinstance(discovered_raw, dict) else None
    )
    if not isinstance(discovered_embedding, dict) or not any(
        str(value).strip() for value in discovered_embedding.values() if value is not None
    ):
        return False
    try:
        base_text = base_config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        base_raw: dict[str, Any] = {}
    except OSError as exc:
        raise ReviewflowError(f"Failed to read ChunkHound base config at {base_config_path}: {exc}") from exc
    else:
        if not base_text.strip():
            base_raw = {}
        else:
            try:
                parsed = json.loads(base_text)
            except json.JSONDecodeError as exc:
                raise ReviewflowError(
                    f"Failed to parse ChunkHound base config at {base_config_path}: {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise ReviewflowError(
                    f"ChunkHound base config at {base_config_path} must contain a JSON object."
                )
            base_raw = parsed

    if base_raw.get("embedding") == discovered_embedding:
        return False

    updated = dict(base_raw)
    updated["embedding"] = discovered_embedding
    base_config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(base_config_path, updated)
    return True


def chunkhound_env(*, source_config_path: Path | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    if os.environ.get("CHUNKHOUND_EMBEDDING__API_KEY"):
        return env
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if voyage_key:
        env["CHUNKHOUND_EMBEDDING__API_KEY"] = voyage_key
        return env
    inferred = load_embedding_api_key_from_config(source_config_path=source_config_path)
    if inferred:
        env["CHUNKHOUND_EMBEDDING__API_KEY"] = inferred
    return env


def _stream_is_tty(stream: Any) -> bool:
    try:
        return bool(stream is not None and stream.isatty())
    except Exception:
        return False


@dataclass(frozen=True)
class _InteractiveChunkhoundIndexResult:
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


def _missing_embedding_config_error(*, base_config_path: Path) -> ReviewflowError:
    return ReviewflowError(
        "\n".join(
            [
                f"ChunkHound embedding config is missing from {base_config_path}.",
                "Add an `embedding` block, set `CHUNKHOUND_EMBEDDING__API_KEY` / `VOYAGE_API_KEY` / `OPENAI_API_KEY`, or run `cure setup` in a TTY before retrying.",
            ]
        )
    )


def _run_chunkhound_embedding_setup(
    *,
    index_cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    seed: Path,
    base_config_path: Path,
) -> _InteractiveChunkhoundIndexResult:
    started = time.perf_counter()
    subprocess.run(
        index_cmd,
        cwd=str(cwd),
        env=env,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    persisted = _persist_discovered_embedding_config(
        base_config_path=base_config_path,
        discovered_config_path=seed / ".chunkhound.json",
    )
    if not persisted and not _has_embedding_config(resolved_config=None, env=os.environ):
        raise _missing_embedding_config_error(base_config_path=base_config_path)
    return _InteractiveChunkhoundIndexResult(duration_seconds=time.perf_counter() - started)

def compute_pr_stats(*, repo_dir: Path, base_ref: str, head_ref: str = "HEAD") -> dict[str, Any]:
    """Compute local diff stats using git (no GH API beyond checkout)."""
    name_only = _run_cmd(
        ["git", "-C", str(repo_dir), "diff", "--name-only", f"{base_ref}...{head_ref}"]
    ).stdout
    changed_files = len([line for line in name_only.splitlines() if line.strip()])

    numstat = _run_cmd(
        ["git", "-C", str(repo_dir), "diff", "--numstat", f"{base_ref}...{head_ref}"]
    ).stdout
    additions = 0
    deletions = 0
    binary_files = 0
    for raw in numstat.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add, delete = parts[0], parts[1]
        if add == "-" or delete == "-":
            binary_files += 1
            continue
        try:
            additions += int(add)
            deletions += int(delete)
        except ValueError:
            continue

    changed_lines = additions + deletions
    return {
        "detector": "git",
        "base_ref": base_ref,
        "head_ref": head_ref,
        "changed_files": changed_files,
        "additions": additions,
        "deletions": deletions,
        "changed_lines": changed_lines,
        "binary_files": binary_files,
    }

def resolve_prompt_profile(
    *,
    requested: str,
    pr_stats: dict[str, Any] | None,
    big_if_files: int,
    big_if_lines: int,
) -> tuple[str, str]:
    """Return (resolved_profile, reason)."""
    if requested in {"normal", "big", "default"}:
        return (requested, f"requested:{requested}")

    if requested != "auto":
        return ("normal", f"unknown:{requested} -> normal")

    if not pr_stats:
        return ("big", "auto->big: stats unavailable")

    changed_files = int(pr_stats.get("changed_files") or 0)
    changed_lines = int(pr_stats.get("changed_lines") or 0)

    if changed_files >= big_if_files:
        return ("big", f"auto->big: changed_files={changed_files}>={big_if_files}")
    if changed_lines >= big_if_lines:
        return ("big", f"auto->big: changed_lines={changed_lines}>={big_if_lines}")

    return (
        "normal",
        f"auto->normal: changed_files={changed_files}<{big_if_files} and changed_lines={changed_lines}<{big_if_lines}",
    )

def prompt_template_name_for_profile(profile: str) -> str:
    if profile == "normal":
        return "mrereview_gh_local.md"
    if profile == "big":
        return "mrereview_gh_local_big.md"
    if profile == "default":
        return "default.md"
    raise ReviewflowError(f"Unknown prompt profile: {profile}")

def followup_prompt_template_name_for_profile(profile: str) -> str:
    if profile == "big":
        return "mrereview_gh_local_big_followup.md"
    return "mrereview_gh_local_followup.md"


def chunkhound_prompt_contracts() -> dict[str, ChunkHoundPromptContract]:
    return dict(_BUILTIN_CHUNKHOUND_PROMPT_CONTRACTS)


def chunkhound_prompt_contract_for_template(name: str) -> ChunkHoundPromptContract | None:
    return _BUILTIN_CHUNKHOUND_PROMPT_CONTRACTS.get(str(name).strip())


_CHUNKHOUND_PROOF_SUCCESS_STATUSES = {"completed", "ok", "passed", "success", "succeeded"}
_CHUNKHOUND_PROOF_FAILURE_STATUSES = {
    "cancelled",
    "canceled",
    "error",
    "failed",
    "failure",
    "timed_out",
    "timeout",
}
_CHUNKHOUND_PROOF_REQUIRED_TOOLS = {"search", "code_research"}
_CHUNKHOUND_PROOF_DISCOVERY_TOOLS = {
    "list_mcp_resources",
    "list_mcp_resource_templates",
}
_CHUNKHOUND_NATIVE_PROOF_SOURCES = {"chunkhound", "codex"}
_CHUNKHOUND_HELPER_ENV_PATTERN = re.compile(r"(?<![\w.-])\$\{?CURE_CHUNKHOUND_HELPER\}?(?![\w.-])")


def _first_nonempty_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_chunkhound_tool_name(raw: object) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    if text.startswith("chunkhound."):
        text = text.split(".", 1)[1]
    return text


def _chunkhound_tool_targets_expected_server(*, item: dict[str, Any], raw_tool_name: str) -> bool:
    raw = str(raw_tool_name or "").strip().lower()
    server = _first_nonempty_string(
        item.get("server"),
        item.get("server_name"),
        item.get("mcp_server"),
    ).lower()
    if raw.startswith("chunkhound."):
        return True
    if server and server not in _CHUNKHOUND_NATIVE_PROOF_SOURCES:
        return False
    return True


def _extract_tool_name(item: dict[str, Any]) -> str:
    tool = item.get("tool")
    tool = tool if isinstance(tool, dict) else {}
    call = item.get("call")
    call = call if isinstance(call, dict) else {}
    return _first_nonempty_string(
        item.get("tool_name"),
        item.get("name"),
        item.get("tool"),
        tool.get("name"),
        call.get("tool_name"),
        call.get("name"),
    )


def _extract_tool_status(event_type: str, item: dict[str, Any]) -> bool | None:
    result = item.get("result")
    result = result if isinstance(result, dict) else {}
    outcome = item.get("outcome")
    outcome = outcome if isinstance(outcome, dict) else {}
    for value in (
        item.get("success"),
        item.get("ok"),
        result.get("success"),
        result.get("ok"),
        outcome.get("success"),
        outcome.get("ok"),
    ):
        if isinstance(value, bool):
            return value
    for raw_status in (
        item.get("status"),
        result.get("status"),
        outcome.get("status"),
    ):
        status = str(raw_status or "").strip().lower()
        if not status:
            continue
        if status in _CHUNKHOUND_PROOF_SUCCESS_STATUSES:
            return True
        if status in _CHUNKHOUND_PROOF_FAILURE_STATUSES:
            return False
    normalized_event_type = str(event_type or "").strip().lower()
    if normalized_event_type == "item.completed":
        return True
    if normalized_event_type in {"item.failed", "item.error"}:
        return False
    return None


def _iter_codex_tool_call_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("type") or "").strip()
        item = payload.get("item")
        item = item if isinstance(item, dict) else {}
        if str(item.get("type") or "").strip() == "mcp_tool_call":
            calls.append((event_type, item))
            continue
        if str(payload.get("type") or "").strip() == "mcp_tool_call":
            calls.append((event_type, payload))
    return calls


def _iter_codex_command_execution_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    commands: list[tuple[str, dict[str, Any]]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("type") or "").strip()
        item = payload.get("item")
        item = item if isinstance(item, dict) else {}
        if str(item.get("type") or "").strip() == "command_execution":
            commands.append((event_type, item))
            continue
        if str(payload.get("type") or "").strip() == "command_execution":
            commands.append((event_type, payload))
    return commands


def _command_execution_succeeded(event_type: str, item: dict[str, Any]) -> bool:
    if _extract_tool_status(event_type, item) is False:
        return False
    exit_code = item.get("exit_code")
    if isinstance(exit_code, int):
        return exit_code == 0
    return _extract_tool_status(event_type, item) is True


def _command_matches_chunkhound_helper_env(command: object) -> re.Match[str] | None:
    return _CHUNKHOUND_HELPER_ENV_PATTERN.search(str(command or ""))


def _command_uses_staged_chunkhound_helper(*, command: object, helper_path: object) -> bool:
    text = str(command or "")
    if not text:
        return False
    if _command_matches_chunkhound_helper_env(text) is not None:
        return True
    helper = str(helper_path or "").strip()
    if not helper:
        return False
    helper_patterns = (
        re.compile(rf"(?<![\w./-]){re.escape(helper)}(?![\w./-])"),
        re.compile(rf"['\"]{re.escape(helper)}['\"]"),
    )
    return any(pattern.search(text) is not None for pattern in helper_patterns)


def _command_invokes_staged_chunkhound_helper_tool(
    *,
    command: object,
    helper_path: object,
    tool_name: str,
) -> bool:
    text = " ".join(str(command or "").split())
    if not text:
        return False
    normalized_tool = _normalize_chunkhound_tool_name(tool_name)
    if normalized_tool == "search":
        helper_subcommand = "search"
    elif normalized_tool == "code_research":
        helper_subcommand = "research"
    else:
        return False

    env_helper = r'(?:"\$\{?CURE_CHUNKHOUND_HELPER\}?"|\'\$\{?CURE_CHUNKHOUND_HELPER\}?\'|\$\{?CURE_CHUNKHOUND_HELPER\}?)'
    patterns = [
        re.compile(rf"(?<![\w./-]){env_helper}\s+{re.escape(helper_subcommand)}(?![\w./-])"),
    ]

    helper = str(helper_path or "").strip()
    if helper:
        path_token = re.escape(helper)
        patterns.append(
            re.compile(rf"(?<![\w./-])(?:{path_token}|\"{path_token}\"|'{path_token}')\s+{re.escape(helper_subcommand)}(?![\w./-])")
        )

    return any(pattern.search(text) is not None for pattern in patterns)


def _chunkhound_helper_command_excerpt(command: object) -> str | None:
    text = " ".join(str(command or "").split())
    if not text:
        return None
    match = _command_matches_chunkhound_helper_env(text)
    if match is None:
        excerpt = text[:180]
        if len(excerpt) < len(text):
            excerpt = excerpt.rstrip() + "..."
        return excerpt

    start = max(0, match.start() - 48)
    end = min(len(text), match.end() + 132)
    excerpt = text[start:end]
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt.rstrip() + "..."
    return excerpt


def _parse_chunkhound_helper_output(payload_text: object) -> dict[str, Any] | None:
    text = str(payload_text or "").strip()
    if not text:
        return None
    # Codex command_execution events can aggregate helper stderr progress lines
    # with the final JSON payload. Treat the recovered JSON object as the proof
    # artifact so older/noisy helper runs remain valid.
    candidates = [text]
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if 0 <= first_brace < last_brace:
        candidates.append(text[first_brace : last_brace + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _parse_chunkhound_helper_json_text(payload_text: object) -> object | None:
    text = str(payload_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _chunkhound_helper_search_payload_succeeded(payload: object) -> bool:
    return isinstance(payload, dict) and "results" in payload and isinstance(payload.get("results"), list)


def _chunkhound_helper_research_payload_succeeded(payload: object) -> bool:
    if isinstance(payload, str):
        return bool(payload.strip())
    if isinstance(payload, list):
        return any(_chunkhound_helper_research_payload_succeeded(item) for item in payload)
    if not isinstance(payload, dict):
        return False
    for key in ("text", "markdown", "summary", "answer", "report", "analysis", "response"):
        if key in payload and _chunkhound_helper_research_payload_succeeded(payload.get(key)):
            return True
    return False


def _chunkhound_helper_content_succeeded(*, content: object, command_name: str) -> bool:
    if not isinstance(content, list):
        return False
    if command_name == "search":
        for item in content:
            if isinstance(item, str) and _chunkhound_helper_search_payload_succeeded(
                _parse_chunkhound_helper_json_text(item)
            ):
                return True
            if isinstance(item, dict) and _chunkhound_helper_search_payload_succeeded(
                _parse_chunkhound_helper_json_text(item.get("text"))
            ):
                return True
        return False
    return any(
        _chunkhound_helper_research_payload_succeeded(
            item.get("text") if isinstance(item, dict) else item
        )
        for item in content
    )


def _chunkhound_helper_result_succeeded(*, result: object, command_name: str) -> bool:
    if isinstance(result, dict):
        if result.get("isError") is True or result.get("error") or result.get("ok") is False:
            return False
        if _chunkhound_helper_content_succeeded(content=result.get("content"), command_name=command_name):
            return True
        structured = result.get("structured_content")
        nested = result.get("result")
        text = result.get("text")
        if command_name == "search":
            return any(
                (
                    _chunkhound_helper_search_payload_succeeded(structured),
                    _chunkhound_helper_search_payload_succeeded(nested),
                    _chunkhound_helper_search_payload_succeeded(_parse_chunkhound_helper_json_text(text)),
                    _chunkhound_helper_search_payload_succeeded(result),
                )
            )
        return any(
            (
                _chunkhound_helper_research_payload_succeeded(structured),
                _chunkhound_helper_research_payload_succeeded(nested),
                _chunkhound_helper_research_payload_succeeded(text),
                _chunkhound_helper_research_payload_succeeded(result),
            )
        )
    if command_name == "search":
        return _chunkhound_helper_search_payload_succeeded(result) or _chunkhound_helper_search_payload_succeeded(
            _parse_chunkhound_helper_json_text(result)
        )
    if isinstance(result, list):
        return any(_chunkhound_helper_research_payload_succeeded(item) for item in result)
    if isinstance(result, str):
        return bool(result.strip())
    return False


def _chunkhound_helper_declared_tool_name(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    helper_path = str(payload.get("helper_path") or "").strip()
    if not helper_path:
        return ""
    command_name = str(payload.get("command") or "").strip().lower()
    tool_name = _normalize_chunkhound_tool_name(payload.get("tool_name"))
    if command_name == "search" and tool_name in {"", "search"}:
        return "search"
    if command_name == "research" and tool_name in {"", "code_research"}:
        return "code_research"
    return ""


def _chunkhound_helper_tool_name(payload: object) -> str:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return ""
    tool_name = _chunkhound_helper_declared_tool_name(payload)
    if not tool_name:
        return ""
    command_name = str(payload.get("command") or "").strip().lower()
    if not _chunkhound_helper_result_succeeded(
        result=payload.get("result"),
        command_name=command_name,
    ):
        return ""
    return tool_name


def _chunkhound_helper_failure_detail(
    *,
    payload: dict[str, Any],
    item_id: str | None,
    command: object,
) -> dict[str, Any]:
    stage = _first_nonempty_string(
        payload.get("execution_stage"),
        payload.get("preflight_stage"),
    ) or "unknown"
    stage_status = _first_nonempty_string(
        payload.get("execution_stage_status"),
        payload.get("preflight_stage_status"),
    ) or ("error" if payload.get("ok") is False else "unknown")
    timeout_value = payload.get("execution_timeout_seconds")
    timeout_seconds = float(timeout_value) if isinstance(timeout_value, (int, float)) else None
    detail = _first_nonempty_string(
        payload.get("error"),
        payload.get("stderr_tail"),
        payload.get("daemon_metadata_error"),
    )
    return {
        "tool_name": _chunkhound_helper_declared_tool_name(payload),
        "evidence_source": "cli_helper_command_execution",
        "item_id": item_id,
        "server": None,
        "command_excerpt": _chunkhound_helper_command_excerpt(command),
        "stage": stage,
        "stage_status": stage_status,
        "timeout_seconds": timeout_seconds,
        "detail": detail or None,
    }


def _read_codex_events_slice(*, path: Path, start_offset: int | None, end_offset: int | None) -> str:
    with path.open("rb") as fh:
        if isinstance(start_offset, int) and start_offset > 0:
            fh.seek(start_offset)
        if isinstance(start_offset, int) and isinstance(end_offset, int) and end_offset >= start_offset:
            payload = fh.read(end_offset - start_offset)
        else:
            payload = fh.read()
    return payload.decode("utf-8", errors="replace")


def _chunkhound_helper_detail_for_report(
    *,
    payload: dict[str, Any],
    item_id: str | None,
    command_excerpt: str | None,
    detail_override: str | None = None,
) -> dict[str, Any]:
    detail = _chunkhound_helper_failure_detail(
        payload=payload,
        item_id=item_id,
        command=command_excerpt,
    )
    detail["command_excerpt"] = command_excerpt
    if detail_override:
        detail["detail"] = detail_override
    return detail


def validate_chunkhound_tool_proof(
    *,
    provider: str,
    review_stage: str,
    prompt_template_name: str,
    adapter_meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    contract = chunkhound_prompt_contract_for_template(prompt_template_name)
    if contract is None:
        return None
    normalized_provider = str(provider or "").strip().lower()

    required_tools: list[str] = []
    if contract.search_requirement == "required":
        required_tools.append("search")
    if contract.code_research_requirement == "required":
        required_tools.append("code_research")

    meta = adapter_meta if isinstance(adapter_meta, dict) else {}
    raw_events_path = str(meta.get("codex_events_path") or "").strip()
    raw_start = meta.get("codex_events_start_offset")
    raw_end = meta.get("codex_events_end_offset")
    start_offset = int(raw_start) if isinstance(raw_start, int) else None
    end_offset = int(raw_end) if isinstance(raw_end, int) else None

    report: dict[str, Any] = {
        "provider": normalized_provider or "unknown",
        "review_stage": str(review_stage or "").strip(),
        "prompt_template_name": str(prompt_template_name or "").strip(),
        "required_tools": required_tools,
        "observed_successful_calls": [],
        "observed_successful_call_details": [],
        "observed_failed_call_details": [],
        "observed_evidence_sources": [],
        "ignored_discovery_calls": [],
        "valid": False,
        "failure_reason": None,
        "codex_events_path": raw_events_path or None,
        "codex_events_start_offset": start_offset,
        "codex_events_end_offset": end_offset,
    }

    observed_successful_calls: list[str] = []
    observed_successful_call_details: list[dict[str, Any]] = []
    observed_failed_call_details: list[dict[str, Any]] = []
    ignored_discovery_calls: list[str] = []
    observed_evidence_sources: set[str] = set()
    latest_failed_helper_calls: dict[str, dict[str, Any]] = {}
    if normalized_provider == "codex":
        if not raw_events_path:
            report["failure_reason"] = "missing Codex events path"
            return report

        events_path = Path(raw_events_path).resolve()
        if not events_path.is_file():
            report["failure_reason"] = f"Codex events log not found: {events_path}"
            return report

        try:
            events_text = _read_codex_events_slice(
                path=events_path,
                start_offset=start_offset,
                end_offset=end_offset,
            )
        except OSError as e:
            report["failure_reason"] = f"failed to read Codex events log: {e}"
            return report

        for event_type, item in _iter_codex_tool_call_events(events_text):
            raw_tool_name = _extract_tool_name(item)
            normalized_tool_name = _normalize_chunkhound_tool_name(raw_tool_name)
            if not normalized_tool_name:
                continue
            if not _chunkhound_tool_targets_expected_server(item=item, raw_tool_name=raw_tool_name):
                continue
            if normalized_tool_name in _CHUNKHOUND_PROOF_DISCOVERY_TOOLS or normalized_tool_name.startswith(
                "list_mcp_"
            ):
                if normalized_tool_name not in ignored_discovery_calls:
                    ignored_discovery_calls.append(normalized_tool_name)
                continue
            if normalized_tool_name not in _CHUNKHOUND_PROOF_REQUIRED_TOOLS:
                continue
            if _extract_tool_status(event_type, item) is True:
                if normalized_tool_name not in observed_successful_calls:
                    observed_successful_calls.append(normalized_tool_name)
                detail = {
                    "tool_name": normalized_tool_name,
                    "evidence_source": "mcp_tool_call",
                    "item_id": _first_nonempty_string(item.get("id")) or None,
                    "server": _first_nonempty_string(
                        item.get("server"),
                        item.get("server_name"),
                        item.get("mcp_server"),
                    )
                    or None,
                    "command_excerpt": None,
                }
                if detail not in observed_successful_call_details:
                    observed_successful_call_details.append(detail)
                observed_evidence_sources.add("mcp_tool_call")

        for event_type, item in _iter_codex_command_execution_events(events_text):
            command = _first_nonempty_string(item.get("command"))
            payload = _parse_chunkhound_helper_output(item.get("aggregated_output"))
            if payload is None:
                continue
            if not _command_uses_staged_chunkhound_helper(
                command=command,
                helper_path=payload.get("helper_path"),
            ):
                continue
            tool_name = _chunkhound_helper_tool_name(payload)
            if tool_name not in _CHUNKHOUND_PROOF_REQUIRED_TOOLS:
                declared_tool = _chunkhound_helper_declared_tool_name(payload)
                if declared_tool not in _CHUNKHOUND_PROOF_REQUIRED_TOOLS:
                    continue
                failure_detail = _chunkhound_helper_failure_detail(
                    payload=payload,
                    item_id=_first_nonempty_string(item.get("id")) or None,
                    command=command,
                )
                if failure_detail not in observed_failed_call_details:
                    observed_failed_call_details.append(failure_detail)
                latest_failed_helper_calls[declared_tool] = failure_detail
                continue
            if not _command_execution_succeeded(event_type, item):
                failure_detail = _chunkhound_helper_failure_detail(
                    payload=payload,
                    item_id=_first_nonempty_string(item.get("id")) or None,
                    command=command,
                )
                if failure_detail not in observed_failed_call_details:
                    observed_failed_call_details.append(failure_detail)
                latest_failed_helper_calls[tool_name] = failure_detail
                continue
            if tool_name not in observed_successful_calls:
                observed_successful_calls.append(tool_name)
            detail = {
                "tool_name": tool_name,
                "evidence_source": "cli_helper_command_execution",
                "item_id": _first_nonempty_string(item.get("id")) or None,
                "server": None,
                "command_excerpt": _chunkhound_helper_command_excerpt(command),
            }
            if detail not in observed_successful_call_details:
                observed_successful_call_details.append(detail)
            observed_evidence_sources.add("cli_helper_command_execution")
    elif normalized_provider == "claude":
        helper_path = str(meta.get("chunkhound_helper_path") or "").strip()
        if not helper_path:
            report["failure_reason"] = "missing staged helper path for Claude ChunkHound tool proof"
            return report
        entries = meta.get("chunkhound_tool_proof_entries")
        if not isinstance(entries, list):
            entries = []
        command_excerpt = f"claude tool_use_result via {helper_path}"
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            payload = entry.get("payload")
            if not isinstance(payload, dict):
                continue
            item_id = _first_nonempty_string(entry.get("item_id")) or f"claude-tool-use-{idx}"
            command = _first_nonempty_string(entry.get("command"))
            declared_tool = _chunkhound_helper_declared_tool_name(payload)
            expected_tool = declared_tool or _normalize_chunkhound_tool_name(payload.get("tool_name"))
            payload_helper_path = str(payload.get("helper_path") or "").strip()
            if not _command_invokes_staged_chunkhound_helper_tool(
                command=command,
                helper_path=helper_path,
                tool_name=expected_tool,
            ):
                failure_detail = _chunkhound_helper_detail_for_report(
                    payload=payload,
                    item_id=item_id,
                    command_excerpt=command_excerpt,
                    detail_override="Claude Bash command did not invoke staged helper for the claimed tool",
                )
                if failure_detail not in observed_failed_call_details:
                    observed_failed_call_details.append(failure_detail)
                if declared_tool:
                    latest_failed_helper_calls[declared_tool] = failure_detail
                continue
            if payload_helper_path != helper_path:
                failure_detail = _chunkhound_helper_detail_for_report(
                    payload=payload,
                    item_id=item_id,
                    command_excerpt=command_excerpt,
                    detail_override=(
                        f"staged helper path mismatch: expected {helper_path}, observed {payload_helper_path or '<missing>'}"
                    ),
                )
                if failure_detail not in observed_failed_call_details:
                    observed_failed_call_details.append(failure_detail)
                if declared_tool:
                    latest_failed_helper_calls[declared_tool] = failure_detail
                continue
            tool_name = _chunkhound_helper_tool_name(payload)
            if tool_name not in _CHUNKHOUND_PROOF_REQUIRED_TOOLS:
                declared_tool = _chunkhound_helper_declared_tool_name(payload)
                if declared_tool not in _CHUNKHOUND_PROOF_REQUIRED_TOOLS:
                    continue
                failure_detail = _chunkhound_helper_detail_for_report(
                    payload=payload,
                    item_id=item_id,
                    command_excerpt=command_excerpt,
                )
                if failure_detail not in observed_failed_call_details:
                    observed_failed_call_details.append(failure_detail)
                latest_failed_helper_calls[declared_tool] = failure_detail
                continue
            if tool_name not in observed_successful_calls:
                observed_successful_calls.append(tool_name)
            detail = {
                "tool_name": tool_name,
                "evidence_source": "cli_helper_command_execution",
                "item_id": item_id,
                "server": None,
                "command_excerpt": command_excerpt,
            }
            if detail not in observed_successful_call_details:
                observed_successful_call_details.append(detail)
            observed_evidence_sources.add("cli_helper_command_execution")
    else:
        return None

    report["observed_successful_calls"] = observed_successful_calls
    report["observed_successful_call_details"] = observed_successful_call_details
    report["observed_failed_call_details"] = observed_failed_call_details
    report["observed_evidence_sources"] = sorted(observed_evidence_sources)
    report["ignored_discovery_calls"] = ignored_discovery_calls
    missing_tools = [tool for tool in required_tools if tool not in observed_successful_calls]
    if missing_tools:
        failure_reason = "missing successful ChunkHound execution(s): " + ", ".join(missing_tools)
        diagnostics: list[str] = []
        for tool in missing_tools:
            detail = latest_failed_helper_calls.get(tool)
            if not isinstance(detail, dict):
                continue
            stage = str(detail.get("stage") or "unknown").strip() or "unknown"
            stage_status = str(detail.get("stage_status") or "unknown").strip() or "unknown"
            timeout_seconds = detail.get("timeout_seconds")
            timeout_suffix = (
                f" after {float(timeout_seconds):.1f}s"
                if isinstance(timeout_seconds, (int, float))
                else ""
            )
            detail_text = str(detail.get("detail") or "").strip()
            diagnostic = f"{tool} failed during {stage} ({stage_status}){timeout_suffix}"
            if detail_text:
                diagnostic += f": {detail_text}"
            diagnostics.append(diagnostic)
        if diagnostics:
            failure_reason += "; helper diagnostics: " + "; ".join(diagnostics)
        report["failure_reason"] = failure_reason
        return report

    report["valid"] = True
    return report


def validate_and_record_chunkhound_tool_proof(
    *,
    meta: dict[str, Any],
    work_dir: Path,
    provider: str,
    review_stage: str,
    prompt_template_name: str,
    adapter_meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    run_report = validate_chunkhound_tool_proof(
        provider=provider,
        review_stage=review_stage,
        prompt_template_name=prompt_template_name,
        adapter_meta=adapter_meta,
    )
    if run_report is None:
        return None

    report_path = (work_dir / "chunkhound_tool_validation.json").resolve()
    existing_runs: list[dict[str, Any]] = []
    if report_path.is_file():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        runs = payload.get("runs")
        if isinstance(runs, list):
            existing_runs = [item for item in runs if isinstance(item, dict)]
    runs = [*existing_runs, run_report]
    latest_evidence_sources = sorted(
        {
            str(source).strip()
            for source in run_report.get("observed_evidence_sources") or []
            if str(source).strip()
        }
    )
    evidence_sources = sorted(
        {
            str(source).strip()
            for item in runs
            for source in (item.get("observed_evidence_sources") or [])
            if str(source).strip()
        }
    )
    report_payload = {
        "schema_version": 2,
        "updated_at": _utc_now_iso(),
        "provider": str(run_report.get("provider") or provider or "").strip() or "unknown",
        "valid": bool(run_report.get("valid")),
        "latest_evidence_sources": latest_evidence_sources,
        "evidence_sources": evidence_sources,
        "runs": runs,
    }
    write_json(report_path, report_payload)

    chunkhound_meta = meta.get("chunkhound")
    if not isinstance(chunkhound_meta, dict):
        chunkhound_meta = {}
        meta["chunkhound"] = chunkhound_meta
    chunkhound_meta["tool_validation"] = {
        "provider": str(report_payload["provider"]),
        "path": str(report_path),
        "valid": bool(report_payload["valid"]),
        "run_count": len(runs),
        "latest_review_stage": run_report["review_stage"],
        "latest_run_valid": bool(run_report["valid"]),
        "evidence_sources": evidence_sources,
        "latest_evidence_sources": latest_evidence_sources,
        "failure_reason": run_report.get("failure_reason"),
    }
    return run_report


def _normalize_plan_abort_reason_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _resolve_chunkhound_tool_validation_report_path(
    *, meta: dict[str, Any] | None, work_dir: Path
) -> Path:
    chunkhound_meta = meta.get("chunkhound") if isinstance(meta, dict) else None
    tool_validation = chunkhound_meta.get("tool_validation") if isinstance(chunkhound_meta, dict) else None
    raw_path = str(tool_validation.get("path") or "").strip() if isinstance(tool_validation, dict) else ""
    if raw_path:
        return Path(raw_path).resolve()
    return (work_dir / "chunkhound_tool_validation.json").resolve()


def _load_latest_chunkhound_tool_validation_run(
    *, report_path: Path, review_stage: str, require_valid: bool = False
) -> tuple[dict[str, Any] | None, int | None]:
    if not report_path.is_file():
        return None, None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return None, None
    for idx in range(len(runs) - 1, -1, -1):
        item = runs[idx]
        if not isinstance(item, dict):
            continue
        if str(item.get("review_stage") or "").strip() != review_stage:
            continue
        if require_valid and (item.get("valid") is not True):
            continue
        return item, idx
    return None, None


def detect_multipass_plan_abort_contradiction(
    *,
    meta: dict[str, Any] | None,
    work_dir: Path,
    plan: dict[str, Any] | None,
    plan_tool_report: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    plan_payload = plan if isinstance(plan, dict) else {}
    if not bool(plan_payload.get("abort")):
        return None

    abort_reason = str(plan_payload.get("abort_reason") or "").strip()
    normalized_reason = _normalize_plan_abort_reason_text(abort_reason)
    if not normalized_reason:
        return None

    report_path = _resolve_chunkhound_tool_validation_report_path(meta=meta, work_dir=work_dir)
    persisted_run, persisted_run_index = _load_latest_chunkhound_tool_validation_run(
        report_path=report_path,
        review_stage="multipass_plan",
        require_valid=True,
    )
    live_report = plan_tool_report if isinstance(plan_tool_report, dict) else None
    if (
        isinstance(live_report, dict)
        and str(live_report.get("review_stage") or "").strip() == "multipass_plan"
        and bool(live_report.get("valid"))
    ):
        proof_run = live_report
        proof_source = "live_plan_report"
    else:
        proof_run = persisted_run
        proof_source = "persisted_plan_report" if persisted_run is not None else None
    if not isinstance(proof_run, dict) or not bool(proof_run.get("valid")):
        return None

    validated_tools = [
        str(tool).strip()
        for tool in (proof_run.get("observed_successful_calls") or [])
        if str(tool).strip()
    ]
    validated_tool_set = set(validated_tools)
    if not validated_tool_set:
        return None

    failure_terms = (
        r"\bfailed\b",
        r"\bfailure\b",
        r"\bunavailable\b",
        r"\bmissing\b",
        r"\bnever completed\b",
        r"\bdid not complete\b",
        r"\bdidn't complete\b",
        r"\bnot complete\b",
        r"\bnot completed\b",
        r"\bunable to\b",
        r"\bcould not\b",
        r"\bcouldn't\b",
        r"\bnot available\b",
        r"\btimed out\b",
        r"\btimeout\b",
        r"\bno completed\b",
    )
    gate_terms = (
        r"\bgate\b",
        r"\bmandatory review-intelligence\b",
        r"\brequired review-intelligence\b",
        r"\brequired intelligence\b",
        r"\bmandatory helper gate\b",
        r"\bno plan steps\b",
        r"\bno steps could be emitted\b",
    )
    helper_terms = (r"\bhelper\b", r"\bchunkhound\b")
    search_terms = (r"\bsearch\b",)
    code_research_terms = (r"\bcode[_\s-]*research\b", r"\bresearch\b")

    matched_signals: list[str] = []

    def _contains_any(patterns: tuple[str, ...], *, signal: str) -> bool:
        matched = any(re.search(pattern, normalized_reason) for pattern in patterns)
        if matched and signal not in matched_signals:
            matched_signals.append(signal)
        return matched

    has_failure = _contains_any(failure_terms, signal="failure_term")
    has_gate = _contains_any(gate_terms, signal="gate_term")
    has_helper = _contains_any(helper_terms, signal="helper_term")
    has_search = _contains_any(search_terms, signal="search_term")
    has_code_research = _contains_any(code_research_terms, signal="code_research_term")

    matched_categories: list[str] = []
    if has_helper and (has_failure or has_gate):
        matched_categories.append("helper_failure")
    if "search" in validated_tool_set and has_search and (has_failure or has_gate or has_helper):
        matched_categories.append("missing_search")
    if "code_research" in validated_tool_set and has_code_research and (has_failure or has_gate or has_helper):
        matched_categories.append("missing_code_research")
    if (has_helper or has_search or has_code_research) and has_gate and (has_failure or has_helper):
        matched_categories.append("helper_gate_failure")
    if not matched_categories:
        return None

    evidence_sources = [
        str(source).strip()
        for source in (proof_run.get("observed_evidence_sources") or [])
        if str(source).strip()
    ]
    return {
        "detected_at": _utc_now_iso(),
        "review_stage": "multipass_plan",
        "status": "planner_runtime_inconsistency",
        "abort_reason": abort_reason,
        "matched_categories": matched_categories,
        "matched_signals": matched_signals,
        "validated_tools": validated_tools,
        "evidence_sources": evidence_sources,
        "tool_validation_report_path": str(report_path),
        "tool_validation_run_index": persisted_run_index,
        "tool_validation_source": proof_source,
    }


def review_intelligence_prompt_vars(
    cfg: ReviewIntelligenceConfig,
    *,
    capability_summary: dict[str, Any] | None = None,
) -> dict[str, str]:
    return {
        "REVIEW_INTELLIGENCE_GUIDANCE": build_review_intelligence_guidance(
            cfg,
            capability_summary=capability_summary,
        )
    }

def render_prompt(
    template_text: str,
    *,
    base_ref_for_review: str,
    pr_url: str,
    pr_number: int,
    gh_host: str,
    gh_owner: str,
    gh_repo_name: str,
    gh_repo: str,
    agent_desc: str,
    head_ref: str = "HEAD",
    extra_vars: dict[str, str] | None = None,
) -> str:
    # Back-compat: existing reviewflow placeholders.
    text = template_text.replace("<base>", base_ref_for_review)

    # Legacy-ish placeholders (mrereview_gh*).
    text = text.replace("$PR_URL", pr_url).replace("${PR_URL}", pr_url)
    text = text.replace("$PR_NUMBER", str(pr_number)).replace("${PR_NUMBER}", str(pr_number))
    text = text.replace("$GH_HOST", gh_host).replace("${GH_HOST}", gh_host)
    text = text.replace("$GH_OWNER", gh_owner).replace("${GH_OWNER}", gh_owner)
    text = text.replace("$GH_REPO_NAME", gh_repo_name).replace(
        "${GH_REPO_NAME}", gh_repo_name
    )
    text = text.replace("$GH_REPO", gh_repo).replace("${GH_REPO}", gh_repo)
    text = text.replace("$BASE_REF", base_ref_for_review).replace(
        "${BASE_REF}", base_ref_for_review
    )
    text = text.replace("$HEAD_REF", head_ref).replace("${HEAD_REF}", head_ref)
    # Citation-contract substitution runs BEFORE the extra_vars loop so the
    # hardcoded contract is written into the template first; a colliding
    # ``extra_vars`` key then finds no remaining placeholder to overwrite and
    # becomes a no-op — the contract always wins.
    for contract_key, contract_value in CITATION_CONTRACT_KEYS.items():
        text = text.replace(f"${contract_key}", contract_value).replace(
            f"${{{contract_key}}}", contract_value
        )
    review_intelligence_guidance: str | None = None
    if extra_vars:
        for k, v in extra_vars.items():
            key = str(k).strip()
            if not key:
                continue
            if key == "REVIEW_INTELLIGENCE_GUIDANCE":
                review_intelligence_guidance = str(v)
                continue
            text = text.replace(f"${key}", str(v)).replace(f"${{{key}}}", str(v))
    if review_intelligence_guidance is not None:
        text = text.replace("$REVIEW_INTELLIGENCE_GUIDANCE", review_intelligence_guidance).replace(
            "${REVIEW_INTELLIGENCE_GUIDANCE}", review_intelligence_guidance
        )
    # Replace AGENT_DESC last to avoid mutating its contents if it contains `$FOO`.
    text = text.replace("$AGENT_DESC", agent_desc).replace("${AGENT_DESC}", agent_desc)
    return text

def build_abort_review_markdown(*, reason: str, include_steps_taken: bool = False) -> str:
    lines: list[str] = []
    if include_steps_taken:
        lines.extend(["### Steps taken", "- Multipass plan aborted", ""])
    lines.extend(
        [
            f"**Summary**: ABORT: {reason}",
            "",
            "## Business / Product Assessment",
            "**Verdict**: REJECT",
            "",
            "### Strengths",
            "- None.",
            "",
            "### In Scope Issues",
            f"- ABORT: {reason}",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "## Technical Assessment",
            "**Verdict**: REJECT",
            "",
            "### Strengths",
            "- None.",
            "",
            "### In Scope Issues",
            f"- ABORT: {reason}",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "### Reusability",
            "- None.",
        ]
    )
    if include_steps_taken:
        lines.extend(["####", ""])
    else:
        lines.append("")
    return "\n".join(lines)

def multipass_prompt_template_names() -> dict[str, str]:
    return {
        "plan": "mrereview_gh_local_big_plan.md",
        "step": "mrereview_gh_local_big_step.md",
        "synth": "mrereview_gh_local_big_synth.md",
    }

def _extract_first_fenced_block(text: str, *, lang: str) -> str | None:
    """Extract the first fenced code block for a given language (e.g. ```json ... ```)."""
    fence = f"```{lang}"
    start = text.find(fence)
    if start < 0:
        return None
    start = text.find("\n", start)
    if start < 0:
        return None
    start += 1
    end = text.find("```", start)
    if end < 0:
        return None
    return text[start:end].strip()

def parse_multipass_plan_json(text: str) -> dict[str, Any]:
    raw = _extract_first_fenced_block(text, lang="json")
    if not raw:
        raise ReviewflowError("Multipass plan JSON missing (expected a ```json fenced block).")
    try:
        data = json.loads(raw)
    except Exception as e:
        raise ReviewflowError(f"Multipass plan JSON invalid: {e}") from e
    if not isinstance(data, dict):
        raise ReviewflowError("Multipass plan JSON must be an object.")
    abort = data.get("abort")
    if not isinstance(abort, bool):
        raise ReviewflowError("Multipass plan JSON must include boolean field: abort")
    abort_reason = data.get("abort_reason")
    if abort_reason is not None and not isinstance(abort_reason, str):
        raise ReviewflowError("Multipass plan JSON abort_reason must be null or string.")
    ticket_keys = data.get("ticket_keys")
    jira_keys = data.get("jira_keys")
    if ticket_keys is not None:
        if not isinstance(ticket_keys, list) or not all(isinstance(item, str) for item in ticket_keys):
            raise ReviewflowError("Multipass plan JSON ticket_keys must be an array of strings.")
        if jira_keys is None:
            data["jira_keys"] = list(ticket_keys)
    elif jira_keys is not None and (
        not isinstance(jira_keys, list) or not all(isinstance(item, str) for item in jira_keys)
    ):
        raise ReviewflowError("Multipass plan JSON jira_keys must be an array of strings.")
    steps = data.get("steps")
    if abort:
        if steps not in (None, [], ()):
            raise ReviewflowError("Multipass plan JSON must not include steps when abort=true.")
        return data
    if not isinstance(steps, list) or not steps:
        raise ReviewflowError("Multipass plan JSON must include a non-empty steps array.")
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ReviewflowError(f"Multipass plan step #{idx} must be an object.")
        if not isinstance(step.get("title"), str) or not str(step.get("title")).strip():
            raise ReviewflowError(f"Multipass plan step #{idx} missing title.")
        if not isinstance(step.get("focus"), str) or not str(step.get("focus")).strip():
            raise ReviewflowError(f"Multipass plan step #{idx} missing focus.")
    return data

def require_gh_auth(host: str) -> None:
    try:
        _run_cmd(["gh", "auth", "status", "--hostname", host], check=True)
    except ReviewflowSubprocessError as e:
        _raise_gh_auth_error(host=host, error=e)

def _gh_error_text(error: ReviewflowSubprocessError) -> str:
    return (error.stderr or error.stdout or str(error)).strip()

def _looks_like_gh_auth_error(error: ReviewflowSubprocessError) -> bool:
    text = _gh_error_text(error).lower()
    needles = (
        "gh auth login",
        "not logged into any github hosts",
        "not authenticated",
        "populate the gh_token",
        "please run:  gh auth login",
        "please run gh auth login",
    )
    return any(needle in text for needle in needles)

def _raise_gh_auth_error(*, host: str, error: ReviewflowSubprocessError) -> None:
    msg = _gh_error_text(error) or str(error)
    raise ReviewflowError(
        f"`gh` is not authenticated for {host}.\n"
        f"- Try: gh auth login -h {host}\n"
        f"- Details: {msg}"
    ) from error


def _handle_missing_gh(*, host: str, action: str, allow_public_fallback: bool) -> None:
    if allow_public_fallback and _supports_public_github_fallback(host):
        return
    raise ReviewflowError(
        f"`gh` is required for {action} on {host}. Install GitHub CLI or use github.com with public fallback."
    )


def _supports_public_github_fallback(host: str) -> bool:
    return host == "github.com"

def _public_github_repo_clone_url(*, host: str, owner: str, repo: str) -> str:
    if not _supports_public_github_fallback(host):
        raise ReviewflowError(
            f"Unauthenticated public clone fallback is only supported for github.com, got: {host}"
        )
    return f"https://github.com/{owner}/{repo}.git"

def _github_public_api_json(*, path: str) -> dict[str, Any]:
    normalized = path if path.startswith("/") else f"/{path}"
    req = urllib.request.Request(
        f"https://api.github.com{normalized}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "cure/0.1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ReviewflowError(
            f"Public GitHub API request failed ({getattr(e, 'code', '?')}): {normalized}\n{body}"
        ) from e
    except urllib.error.URLError as e:
        raise ReviewflowError(f"Public GitHub API request failed: {normalized}\n{e}") from e
    try:
        payload = json.loads(body)
    except Exception as e:
        raise ReviewflowError(f"Public GitHub API returned invalid JSON for {normalized}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"Public GitHub API returned unexpected payload for {normalized}")
    return payload

def gh_api_json(*, host: str, path: str, allow_public_fallback: bool = False) -> dict[str, Any]:
    cmd = ["gh", "api", "--hostname", host, path]
    try:
        result = _run_cmd(cmd)
    except ReviewflowSubprocessError as e:
        if _looks_like_gh_auth_error(e):
            if allow_public_fallback and _supports_public_github_fallback(host):
                _eprint(f"`gh` is not authenticated for {host}; falling back to the public GitHub API.")
                return _github_public_api_json(path=path)
            _raise_gh_auth_error(host=host, error=e)
        raise
    try:
        payload = json.loads(result.stdout)
    except Exception as e:
        raise ReviewflowError(f"`gh api` returned invalid JSON for {path}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"`gh api` returned unexpected payload for {path}")
    return payload


def _compat_gh_api_json(**kwargs: Any) -> dict[str, Any]:
    target = getattr(_reviewflow(), "gh_api_json", None)
    if target is None or target is gh_api_json:
        return gh_api_json(**kwargs)
    return target(**kwargs)

def write_pr_context_file(
    *,
    work_dir: Path,
    pr: PullRequestRef,
    pr_meta: dict[str, Any],
) -> Path:
    path = work_dir / "pr_context.json"
    base = pr_meta.get("base") if isinstance(pr_meta.get("base"), dict) else {}
    head = pr_meta.get("head") if isinstance(pr_meta.get("head"), dict) else {}
    user = pr_meta.get("user") if isinstance(pr_meta.get("user"), dict) else {}
    write_json(
        path,
        {
            "source": "cure.resolve_pr_meta",
            "pr": {
                "host": pr.host,
                "owner": pr.owner,
                "repo": pr.repo,
                "number": pr.number,
                "url": str(pr_meta.get("html_url") or f"https://{pr.host}/{pr.owner}/{pr.repo}/pull/{pr.number}"),
                "title": str(pr_meta.get("title") or ""),
                "body": str(pr_meta.get("body") or ""),
                "state": str(pr_meta.get("state") or ""),
                "draft": bool(pr_meta.get("draft", False)),
                "author": str(user.get("login") or ""),
                "base_ref": str(base.get("ref") or ""),
                "head_ref": str(head.get("ref") or ""),
                "head_sha": str(head.get("sha") or ""),
            },
        },
    )
    return path

def clone_seed_repo(*, host: str, owner: str, repo: str, seed: Path) -> None:
    cmd = ["gh", "repo", "clone", repo_id_for_gh(host, owner, repo), str(seed)]
    try:
        _run_cmd(cmd)
        return
    except ReviewflowSubprocessError as e:
        if _looks_like_gh_auth_error(e):
            if _supports_public_github_fallback(host):
                _eprint(f"`gh` is not authenticated for {host}; falling back to public git clone.")
                _run_cmd(
                    [
                        "git",
                        "clone",
                        _public_github_repo_clone_url(host=host, owner=owner, repo=repo),
                        str(seed),
                    ]
                )
                return
            _raise_gh_auth_error(host=host, error=e)
        raise

def checkout_pr_in_repo(*, repo_dir: Path, pr: PullRequestRef) -> None:
    cmd = [
        "gh",
        "pr",
        "checkout",
        str(pr.number),
        "-R",
        pr.gh_repo,
        "--force",
    ]
    try:
        _run_cmd(cmd, cwd=repo_dir)
        return
    except ReviewflowSubprocessError as e:
        if _looks_like_gh_auth_error(e):
            if _supports_public_github_fallback(pr.host):
                branch = f"cure_pr__{pr.number}"
                _eprint(f"`gh` is not authenticated for {pr.host}; falling back to public git fetch for PR #{pr.number}.")
                _run_cmd(
                    [
                        "git",
                        "-C",
                        str(repo_dir),
                        "fetch",
                        "origin",
                        f"refs/pull/{pr.number}/head:{branch}",
                    ]
                )
                _run_cmd(["git", "-C", str(repo_dir), "checkout", "-B", branch, branch])
                return
            _raise_gh_auth_error(host=pr.host, error=e)
        raise

def materialize_chunkhound_env_config(
    *,
    resolved_config: dict[str, Any],
    output_config_path: Path,
    database_provider: str,
    database_path: Path,
) -> None:
    """Write a standalone ChunkHound config file for a reviewflow "environment".

    This improves reproducibility by pinning DB location/provider in a session-local config file
    rather than relying on CLI overrides (which can override/replace config lists like indexing.exclude).
    """
    cfg = dict(resolved_config)

    emb = cfg.get("embedding")
    if isinstance(emb, dict) and "api_key" in emb:
        # Avoid materializing secrets to disk, even if present in the source config.
        emb = dict(emb)
        emb.pop("api_key", None)
        cfg["embedding"] = emb

    db = cfg.get("database")
    if not isinstance(db, dict):
        db = {}
    db = dict(db)
    db["provider"] = str(database_provider)
    db["path"] = str(database_path)
    cfg["database"] = db

    write_json(output_config_path, cfg)


def _sync_seed_checkout(
    *,
    paths: ReviewflowPaths,
    host: str,
    owner: str,
    repo: str,
    base_ref: str,
    quiet: bool,
) -> tuple[Path, str]:
    seed = seed_dir(paths, host, owner, repo)
    seed.parent.mkdir(parents=True, exist_ok=True)
    with phase(f"cache_seed_sync {owner}/{repo}@{base_ref}", progress=None, quiet=quiet):
        if not seed.exists():
            clone_seed_repo(host=host, owner=owner, repo=repo, seed=seed)
        else:
            _run_cmd(["git", "-C", str(seed), "rev-parse", "--is-inside-work-tree"])
            _run_cmd(["git", "-C", str(seed), "fetch", "--prune", "origin"])

        _run_cmd(["git", "-C", str(seed), "fetch", "origin", base_ref])
        _run_cmd(["git", "-C", str(seed), "checkout", "-B", base_ref, f"origin/{base_ref}"])
        base_sha = _run_cmd(["git", "-C", str(seed), "rev-parse", "HEAD"]).stdout.strip()
    return seed, base_sha

def ensure_review_config(paths: ReviewflowPaths, *, config_path: Path | None = None) -> None:
    _ = paths
    load_reviewflow_chunkhound_config(
        config_path=(config_path or default_reviewflow_config_path()),
        require=True,
    )

def cache_prime(
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    progress: Any | None = None,
    host: str,
    owner: str,
    repo: str,
    base_ref: str,
    force: bool,
    reason: str | None = None,
    hot_start_seed: dict[str, Any] | None = None,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    base_root = base_dir(paths, host, owner, repo, base_ref)
    base_root.mkdir(parents=True, exist_ok=True)
    with file_lock(base_root / ".cache_prime.lock", quiet=quiet):
        return _cache_prime_locked(
            paths=paths,
            config_path=config_path,
            progress=progress,
            host=host,
            owner=owner,
            repo=repo,
            base_ref=base_ref,
            force=force,
            reason=reason,
            hot_start_seed=hot_start_seed,
            quiet=quiet,
            no_stream=no_stream,
        )


def _cache_prime_locked(
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    progress: Any | None = None,
    host: str,
    owner: str,
    repo: str,
    base_ref: str,
    force: bool,
    reason: str | None = None,
    hot_start_seed: dict[str, Any] | None = None,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    effective_config_path = config_path or default_reviewflow_config_path()
    ensure_review_config(paths, config_path=effective_config_path)
    chunkhound_cfg, chunkhound_meta, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
        config_path=effective_config_path,
        require=True,
    )

    stream = (not quiet) and (not no_stream)
    base_root = base_dir(paths, host, owner, repo, base_ref)

    seed, base_sha = _sync_seed_checkout(
        paths=paths,
        host=host,
        owner=owner,
        repo=repo,
        base_ref=base_ref,
        quiet=quiet,
    )

    db_dir = base_root / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / ".chunkhound.db"
    ch_cfg_path = base_root / "chunkhound.json"
    materialize_chunkhound_env_config(
        resolved_config=resolved_chunkhound_cfg,
        output_config_path=ch_cfg_path,
        database_provider="duckdb",
        database_path=db_path,
    )
    if isinstance(hot_start_seed, dict):
        source_db_raw = str(hot_start_seed.get("db_path") or "").strip()
        if source_db_raw:
            copy_duckdb_files(Path(source_db_raw).resolve(strict=False), db_path)

    cfg_fp = fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
    env_cfg_fp = json_fingerprint(ch_cfg_path)
    meta_path = base_root / "meta.json"
    current_chunkhound_version = _run_cmd(["chunkhound", "--version"]).stdout.strip()

    build_reason = " ".join(str(reason or "").strip().split())
    need_reindex = force
    rebuild_database = False
    detected_reason = "refresh requested" if force else ""
    if not need_reindex and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("config_fingerprint") != cfg_fp:
                need_reindex = True
                detected_reason = "config changed"
            else:
                cached_chunkhound_version = str(meta.get("chunkhound_version") or "").strip()
                if cached_chunkhound_version != current_chunkhound_version:
                    need_reindex = True
                    rebuild_database = True
                    detected_reason = "ChunkHound version changed"
        except Exception:
            need_reindex = True
            detected_reason = "cache metadata unreadable"
    elif not meta_path.is_file():
        detected_reason = "cache miss"

    if not build_reason:
        build_reason = detected_reason

    env = merged_env(chunkhound_env(source_config_path=chunkhound_cfg.base_config_path))
    embedding_missing = not _has_embedding_config(
        resolved_config=resolved_chunkhound_cfg,
        env=env,
    )
    index_cmd = [
        "chunkhound",
        "index",
        str(seed),
        "--config",
        str(ch_cfg_path),
    ]
    if need_reindex and db_path.exists():
        index_cmd.append("--force-reindex")

    with phase(
        f"cache_chunkhound_index {owner}/{repo}@{base_ref}", progress=None, quiet=quiet
    ):
        index_reporter = ChunkhoundLiveProgressReporter(
            progress=progress,
            scope="base_cache",
            reason=build_reason,
        )
        index_reporter.start()
        out = active_output()
        index_ok = False
        try:
            index_reporter.mark_running()
            if embedding_missing and _stream_is_tty(sys.stdin) and _stream_is_tty(sys.stderr):
                if rebuild_database and db_path.exists():
                    if db_path.is_dir():
                        shutil.rmtree(db_path, ignore_errors=True)
                    else:
                        db_path.unlink(missing_ok=True)
                index_result = _run_chunkhound_embedding_setup(
                    index_cmd=index_cmd,
                    cwd=base_root,
                    env=env,
                    seed=seed,
                    base_config_path=chunkhound_cfg.base_config_path,
                )
            elif embedding_missing:
                raise _missing_embedding_config_error(base_config_path=chunkhound_cfg.base_config_path)
            elif out is not None:
                if rebuild_database and db_path.exists():
                    if db_path.is_dir():
                        shutil.rmtree(db_path, ignore_errors=True)
                    else:
                        db_path.unlink(missing_ok=True)
                index_result = out.run_logged_cmd(
                    index_cmd,
                    kind="chunkhound",
                    cwd=base_root,
                    env=env,
                    check=True,
                    stream_requested=stream,
                    stream_text_callback=index_reporter.consume_text,
                )
            else:
                if rebuild_database and db_path.exists():
                    if db_path.is_dir():
                        shutil.rmtree(db_path, ignore_errors=True)
                    else:
                        db_path.unlink(missing_ok=True)
                index_result = _run_cmd(
                    index_cmd,
                    cwd=base_root,
                    env=env,
                    check=True,
                    stream=stream,
                    stream_label="chunkhound",
                )
                index_reporter.consume_text(index_result.stdout)
                index_reporter.consume_text(index_result.stderr)
            index_ok = True
        finally:
            index_reporter.finish(status="done" if index_ok else "error")
    db_size_bytes = path_size_bytes(db_path)

    meta = {
        "host": host,
        "owner": owner,
        "repo": repo,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "indexed_at": _utc_now_iso(),
        "db_path": str(db_path),
        "db_size_bytes": db_size_bytes,
        "chunkhound_config_path": str(ch_cfg_path),
        "config_fingerprint": cfg_fp,
        "env_config_fingerprint": env_cfg_fp,
        "chunkhound": chunkhound_meta.get("chunkhound"),
        "chunkhound_version": current_chunkhound_version,
        "index_cmd": index_cmd,
        "index_duration_seconds": index_result.duration_seconds,
    }
    if build_reason:
        meta["cache_build_reason"] = build_reason
    if isinstance(hot_start_seed, dict):
        meta["hot_start"] = {
            "source_kind": str(hot_start_seed.get("source_kind") or "operator_workspace_config"),
            "workspace_path": str(hot_start_seed.get("workspace_path") or ""),
            "config_path": str(hot_start_seed.get("config_path") or ""),
            "db_path": str(hot_start_seed.get("db_path") or ""),
            "target_match_state": str(hot_start_seed.get("target_match_state") or "unknown"),
            "runtime_match_state": str(hot_start_seed.get("runtime_match_state") or "unknown"),
        }
    index_summary = parse_chunkhound_index_summary(
        "\n".join(part for part in (index_result.stdout, index_result.stderr) if part),
        scope="base_cache",
    )
    if index_summary is not None:
        meta["index_summary"] = index_summary
    write_redacted_json(meta_path, meta)
    return meta


def _compat_cache_prime(**kwargs: Any) -> dict[str, Any]:
    target = getattr(_reviewflow(), "cache_prime", None)
    if target is None or target is cache_prime:
        return cache_prime(**kwargs)
    return target(**kwargs)


def _compat_ensure_base_cache(**kwargs: Any) -> dict[str, Any]:
    target = getattr(_reviewflow(), "ensure_base_cache", None)
    if target is None or target is ensure_base_cache:
        return ensure_base_cache(**kwargs)
    return target(**kwargs)


def _deep_copy_json_value(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _canonical_repo_identity(*, host: str, owner: str, repo: str) -> str:
    return f"{host.strip().lower()}/{owner.strip().lower()}/{repo.strip().lower()}"


def _parse_git_remote_repo_identity(remote_url: str) -> tuple[str, str, str] | None:
    text = str(remote_url or "").strip()
    if not text:
        return None

    parsed = urllib.parse.urlparse(text)
    host = ""
    path = ""
    if parsed.scheme and parsed.netloc:
        host = str(parsed.hostname or parsed.netloc or "").strip().lower()
        path = str(parsed.path or "")
    else:
        match = re.match(r"^(?:[^@/]+@)?(?P<host>[^:]+):(?P<path>.+)$", text)
        if match is None:
            return None
        host = str(match.group("host") or "").strip().lower()
        path = str(match.group("path") or "")

    path = path.strip().lstrip("/").rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2 or not host:
        return None
    owner, repo = parts
    return host, owner.lower(), repo.lower()


def _normalize_chunkhound_seed_match_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = _deep_copy_json_value(config)
    database = normalized.get("database")
    if isinstance(database, dict):
        database = dict(database)
        database.pop("path", None)
        if database:
            normalized["database"] = database
        else:
            normalized.pop("database", None)
    return normalized


def _runtime_chunkhound_seed_match_config(*, resolved_runtime_config: dict[str, Any]) -> dict[str, Any]:
    effective = _deep_copy_json_value(resolved_runtime_config)
    database = effective.get("database")
    database = dict(database) if isinstance(database, dict) else {}
    database["provider"] = "duckdb"
    database["path"] = "<session-local>"
    effective["database"] = database
    return effective


def _duckdb_storage_exists(db_path: Path) -> bool:
    if db_path.is_file():
        return True
    if db_path.is_dir():
        return any(child.is_file() for child in db_path.rglob("*"))
    return False


def _select_repo_local_chunkhound_config_path(repo_root: Path) -> tuple[Path | None, str | None, str | None]:
    for file_name in ("chunkhound.json", ".chunkhound.json"):
        candidate_path = (repo_root / file_name).resolve(strict=False)
        if candidate_path.is_file():
            return candidate_path, file_name, None

    parent_root = repo_root.parent.resolve(strict=False)
    if parent_root != repo_root:
        for file_name in ("chunkhound.json", ".chunkhound.json"):
            candidate_path = (parent_root / file_name).resolve(strict=False)
            if candidate_path.is_file():
                return candidate_path, file_name, "config_not_at_repo_root"

    return None, None, "missing_repo_root_config"


def _operator_chunkhound_seed_validation_message(reason: str) -> str:
    messages = {
        "workspace_not_directory": "Workspace path must point to an existing directory.",
        "missing_candidate_config": "ChunkHound config file is missing.",
        "config_not_at_workspace_root": "ChunkHound config must live at the provided workspace root.",
        "invalid_candidate_config": "ChunkHound config must be valid JSON.",
        "missing_candidate_database": "ChunkHound config is missing the database block.",
        "database_provider_mismatch": "ChunkHound config must use the DuckDB provider.",
        "missing_candidate_db_path": "ChunkHound config is missing the DuckDB path.",
        "candidate_db_outside_repo_root": "ChunkHound DuckDB path must stay inside the provided workspace.",
        "candidate_db_missing": "ChunkHound DuckDB files are missing.",
        "config_mismatch": "ChunkHound config is incompatible with CURe's active runtime settings.",
        "origin_remote_unavailable": "Workspace git origin could not be resolved for repo identity validation.",
        "origin_remote_unrecognized": "Workspace git origin format is not recognized for repo identity validation.",
        "repo_remote_mismatch": "Workspace git origin does not match the PR repository.",
    }
    return messages.get(reason, "ChunkHound seed source validation failed.")


def validate_operator_chunkhound_seed_source(
    *,
    workspace_path: Path,
    config_path: Path,
    pr: PullRequestRef,
    resolved_runtime_config: dict[str, Any],
) -> dict[str, Any]:
    workspace_root = Path(workspace_path).expanduser().resolve(strict=False)
    candidate_config_path = Path(config_path).expanduser()
    if not candidate_config_path.is_absolute():
        candidate_config_path = workspace_root / candidate_config_path
    candidate_config_path = candidate_config_path.resolve(strict=False)
    result: dict[str, Any] = {
        "candidate_state": "rejected",
        "reason": None,
        "message": None,
        "source_kind": "operator_workspace_config",
        "workspace_path": str(workspace_root),
        "config_path": str(candidate_config_path),
        "db_path": None,
        "target_match_state": "unknown",
        "runtime_match_state": "unknown",
    }

    if not workspace_root.is_dir():
        result["reason"] = "workspace_not_directory"
        result["message"] = _operator_chunkhound_seed_validation_message("workspace_not_directory")
        return result

    if candidate_config_path.parent != workspace_root or candidate_config_path.name not in {
        "chunkhound.json",
        ".chunkhound.json",
    }:
        result["reason"] = "config_not_at_workspace_root"
        result["message"] = _operator_chunkhound_seed_validation_message("config_not_at_workspace_root")
        return result
    if not candidate_config_path.is_file():
        result["reason"] = "missing_candidate_config"
        result["message"] = _operator_chunkhound_seed_validation_message("missing_candidate_config")
        return result

    try:
        candidate_config = json.loads(candidate_config_path.read_text(encoding="utf-8"))
    except Exception:
        result["reason"] = "invalid_candidate_config"
        result["message"] = _operator_chunkhound_seed_validation_message("invalid_candidate_config")
        return result
    if not isinstance(candidate_config, dict):
        result["reason"] = "invalid_candidate_config"
        result["message"] = _operator_chunkhound_seed_validation_message("invalid_candidate_config")
        return result

    database = candidate_config.get("database")
    if not isinstance(database, dict):
        result["reason"] = "missing_candidate_database"
        result["message"] = _operator_chunkhound_seed_validation_message("missing_candidate_database")
        return result

    provider = str(database.get("provider") or "").strip().lower()
    if provider != "duckdb":
        result["reason"] = "database_provider_mismatch"
        result["message"] = _operator_chunkhound_seed_validation_message("database_provider_mismatch")
        return result

    candidate_db_raw = str(database.get("path") or "").strip()
    if not candidate_db_raw:
        result["reason"] = "missing_candidate_db_path"
        result["message"] = _operator_chunkhound_seed_validation_message("missing_candidate_db_path")
        return result

    candidate_db_path = Path(candidate_db_raw).expanduser()
    if not candidate_db_path.is_absolute():
        candidate_db_path = candidate_config_path.parent / candidate_db_path
    candidate_db_path = candidate_db_path.resolve(strict=False)
    result["db_path"] = str(candidate_db_path)

    if not _is_relative_to(candidate_db_path, workspace_root):
        result["reason"] = "candidate_db_outside_repo_root"
        result["message"] = _operator_chunkhound_seed_validation_message("candidate_db_outside_repo_root")
        return result
    if not _duckdb_storage_exists(candidate_db_path):
        result["reason"] = "candidate_db_missing"
        result["message"] = _operator_chunkhound_seed_validation_message("candidate_db_missing")
        return result

    runtime_effective = _runtime_chunkhound_seed_match_config(
        resolved_runtime_config=resolved_runtime_config
    )
    if _normalize_chunkhound_seed_match_config(candidate_config) != _normalize_chunkhound_seed_match_config(
        runtime_effective
    ):
        result["reason"] = "config_mismatch"
        result["message"] = _operator_chunkhound_seed_validation_message("config_mismatch")
        result["runtime_match_state"] = "incompatible"
        return result
    result["runtime_match_state"] = "compatible"

    try:
        remote_url = _run_cmd(
            ["git", "-C", str(workspace_root), "remote", "get-url", "origin"],
            check=True,
        ).stdout.strip()
    except Exception:
        result["reason"] = "origin_remote_unavailable"
        result["message"] = _operator_chunkhound_seed_validation_message("origin_remote_unavailable")
        return result

    remote_identity = _parse_git_remote_repo_identity(remote_url)
    if remote_identity is None:
        result["reason"] = "origin_remote_unrecognized"
        result["message"] = _operator_chunkhound_seed_validation_message("origin_remote_unrecognized")
        return result

    resolved_repo_identity = _canonical_repo_identity(
        host=remote_identity[0],
        owner=remote_identity[1],
        repo=remote_identity[2],
    )
    expected_repo_identity = _canonical_repo_identity(host=pr.host, owner=pr.owner, repo=pr.repo)
    if resolved_repo_identity != expected_repo_identity:
        result["reason"] = "repo_remote_mismatch"
        result["message"] = _operator_chunkhound_seed_validation_message("repo_remote_mismatch")
        result["target_match_state"] = "mismatch"
        return result

    result["candidate_state"] = "accepted"
    result["target_match_state"] = "match"
    return result


def discover_repo_local_chunkhound_config(
    *,
    invocation_cwd: Path | None = None,
    pr: PullRequestRef | None = None,
    resolved_runtime_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_repo_identity = (
        _canonical_repo_identity(host=pr.host, owner=pr.owner, repo=pr.repo)
        if pr is not None
        else None
    )
    result: dict[str, Any] = {
        "candidate_state": "absent",
        "reason": None,
        "repo_root": None,
        "config_path": None,
        "config_file_name": None,
        "db_provider": None,
        "db_path": None,
        "repo_identity": None,
        "expected_repo_identity": expected_repo_identity,
        "target_match_state": "not_requested" if pr is None else "unknown",
        "runtime_match_state": "not_requested" if resolved_runtime_config is None else "unknown",
    }

    cwd_path = Path(invocation_cwd or Path.cwd()).resolve(strict=False)
    try:
        repo_root = Path(
            _run_cmd(
                ["git", "-C", str(cwd_path), "rev-parse", "--show-toplevel"],
                check=True,
            ).stdout.strip()
        ).resolve(strict=False)
    except Exception:
        result["reason"] = "cwd_not_git_worktree"
        return result

    result["repo_root"] = str(repo_root)
    candidate_config_path, config_file_name, selection_reason = _select_repo_local_chunkhound_config_path(
        repo_root
    )
    if candidate_config_path is None:
        result["reason"] = selection_reason
        return result

    result["config_path"] = str(candidate_config_path)
    result["config_file_name"] = config_file_name
    if selection_reason == "config_not_at_repo_root":
        result["candidate_state"] = "incompatible"
        result["reason"] = selection_reason
        return result

    try:
        candidate_config = json.loads(candidate_config_path.read_text(encoding="utf-8"))
    except Exception:
        result["candidate_state"] = "incompatible"
        result["reason"] = "invalid_candidate_config"
        return result
    if not isinstance(candidate_config, dict):
        result["candidate_state"] = "incompatible"
        result["reason"] = "invalid_candidate_config"
        return result

    database = candidate_config.get("database")
    if not isinstance(database, dict):
        result["candidate_state"] = "incompatible"
        result["reason"] = "missing_candidate_database"
        return result

    provider = str(database.get("provider") or "").strip().lower()
    result["db_provider"] = provider or None
    if provider != "duckdb":
        result["candidate_state"] = "incompatible"
        result["reason"] = "database_provider_mismatch"
        return result

    candidate_db_raw = str(database.get("path") or "").strip()
    if not candidate_db_raw:
        result["candidate_state"] = "incompatible"
        result["reason"] = "missing_candidate_db_path"
        return result

    candidate_db_path = Path(candidate_db_raw).expanduser()
    if not candidate_db_path.is_absolute():
        candidate_db_path = candidate_config_path.parent / candidate_db_path
    candidate_db_path = candidate_db_path.resolve(strict=False)
    result["db_path"] = str(candidate_db_path)

    if not _is_relative_to(candidate_db_path, repo_root):
        result["candidate_state"] = "incompatible"
        result["reason"] = "candidate_db_outside_repo_root"
        return result
    if not _duckdb_storage_exists(candidate_db_path):
        result["candidate_state"] = "incompatible"
        result["reason"] = "candidate_db_missing"
        return result

    if resolved_runtime_config is not None:
        runtime_effective = _runtime_chunkhound_seed_match_config(
            resolved_runtime_config=resolved_runtime_config
        )
        if _normalize_chunkhound_seed_match_config(
            candidate_config
        ) != _normalize_chunkhound_seed_match_config(runtime_effective):
            result["candidate_state"] = "incompatible"
            result["reason"] = "config_mismatch"
            result["runtime_match_state"] = "incompatible"
            return result
        result["runtime_match_state"] = "compatible"

    if pr is not None:
        try:
            remote_url = _run_cmd(
                ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
                check=True,
            ).stdout.strip()
        except Exception:
            result["candidate_state"] = "ambiguous"
            result["reason"] = "origin_remote_unavailable"
            return result

        remote_identity = _parse_git_remote_repo_identity(remote_url)
        if remote_identity is None:
            result["candidate_state"] = "ambiguous"
            result["reason"] = "origin_remote_unrecognized"
            return result

        resolved_repo_identity = _canonical_repo_identity(
            host=remote_identity[0],
            owner=remote_identity[1],
            repo=remote_identity[2],
        )
        result["repo_identity"] = resolved_repo_identity
        if resolved_repo_identity != expected_repo_identity:
            result["candidate_state"] = "incompatible"
            result["reason"] = "repo_remote_mismatch"
            result["target_match_state"] = "mismatch"
            return result
        result["target_match_state"] = "match"

    result["candidate_state"] = "candidate"
    return result


def discover_exact_repo_local_chunkhound_seed_candidate(
    *,
    pr: PullRequestRef,
    resolved_runtime_config: dict[str, Any],
    invocation_cwd: Path | None = None,
) -> dict[str, Any]:
    discovery = discover_repo_local_chunkhound_config(
        invocation_cwd=invocation_cwd,
        pr=pr,
        resolved_runtime_config=resolved_runtime_config,
    )
    candidate: dict[str, Any] = {
        "repo_root": discovery.get("repo_root"),
        "config_path": discovery.get("config_path"),
        "db_path": discovery.get("db_path"),
        "acceptance_state": "absent",
        "rejection_reason": None,
    }

    state = str(discovery.get("candidate_state") or "absent")
    reason = str(discovery.get("reason") or "").strip() or None
    if state == "candidate":
        candidate["acceptance_state"] = "accepted"
        return candidate

    if reason in {"missing_repo_root_config", "config_not_at_repo_root"}:
        candidate["config_path"] = None
        candidate["db_path"] = None
        candidate["acceptance_state"] = "absent"
        candidate["rejection_reason"] = "missing_repo_local_config"
        return candidate

    if state == "absent":
        candidate["acceptance_state"] = "absent"
        candidate["rejection_reason"] = reason
        return candidate

    candidate["acceptance_state"] = "rejected"
    candidate["rejection_reason"] = reason
    return candidate


def resolve_pr_review_chunkhound_seed_source(
    *,
    pr: PullRequestRef,
    base_cache_meta: dict[str, Any] | None,
    resolved_runtime_config: dict[str, Any],
    invocation_cwd: Path | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    base_cache = base_cache_meta if isinstance(base_cache_meta, dict) else {}
    base_db_raw = str((base_cache or {}).get("db_path") or "").strip()
    base_cfg_raw = str((base_cache or {}).get("chunkhound_config_path") or "").strip()
    base_db_path = Path(base_db_raw).resolve(strict=False) if base_db_raw else None
    base_cfg_path = Path(base_cfg_raw).resolve(strict=False) if base_cfg_raw else None

    candidate = discover_exact_repo_local_chunkhound_seed_candidate(
        pr=pr,
        resolved_runtime_config=resolved_runtime_config,
        invocation_cwd=invocation_cwd,
    )

    seed_source: dict[str, Any] = {
        "source_kind": "shared_base_cache",
        "repo_root": candidate.get("repo_root"),
        "db_path": str(base_db_path) if base_db_path is not None else None,
        "config_path": str(base_cfg_path) if base_cfg_path is not None else None,
        "acceptance_state": candidate.get("acceptance_state"),
        "rejection_reason": candidate.get("rejection_reason"),
        "candidate_db_path": candidate.get("db_path"),
        "candidate_config_path": candidate.get("config_path"),
    }

    if candidate.get("acceptance_state") == "accepted":
        candidate_db_path = Path(str(candidate.get("db_path") or "")).resolve(strict=False)
        candidate_cfg_path = Path(str(candidate.get("config_path") or "")).resolve(strict=False)
        seed_source["source_kind"] = "repo_local_duckdb"
        seed_source["db_path"] = str(candidate_db_path)
        seed_source["config_path"] = str(candidate_cfg_path)
        return candidate_db_path, seed_source

    return base_db_path, seed_source


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _zero_divergence_payload(*, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "files_truncated": False,
        "ahead_by": 0,
        "behind_by": 0,
        "changed_files": 0,
        "additions": 0,
        "deletions": 0,
        "changed_lines": 0,
    }


def _unavailable_divergence_payload(*, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "files_truncated": None,
        "ahead_by": None,
        "behind_by": None,
        "changed_files": None,
        "additions": None,
        "deletions": None,
        "changed_lines": None,
    }


def resolve_pr_review_baseline_selection(
    *,
    pr: PullRequestRef,
    pr_meta: dict[str, Any],
) -> dict[str, Any]:
    base = pr_meta.get("base") if isinstance(pr_meta.get("base"), dict) else {}
    base_ref = str(base.get("ref") or "").strip()
    base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else {}
    repo_default_ref = str(base_repo.get("default_branch") or "").strip()
    selection: dict[str, Any] = {
        "base_ref": base_ref,
        "repo_default_ref": repo_default_ref or None,
        "selected_baseline_ref": base_ref,
        "selection_reason": "default_ref_unavailable",
        "divergence": _unavailable_divergence_payload(source="default_ref_unavailable"),
    }
    if not base_ref:
        raise ReviewflowError("Failed to resolve baseRefName via PR metadata.")
    if not repo_default_ref:
        return selection
    if repo_default_ref == base_ref:
        selection["repo_default_ref"] = repo_default_ref
        selection["selected_baseline_ref"] = repo_default_ref
        selection["selection_reason"] = "target_is_default"
        selection["divergence"] = _zero_divergence_payload(source="target_is_default")
        return selection

    compare_path = "repos/{owner}/{repo}/compare/{default_ref}...{target_ref}".format(
        owner=pr.owner,
        repo=pr.repo,
        default_ref=urllib.parse.quote(repo_default_ref, safe=""),
        target_ref=urllib.parse.quote(base_ref, safe=""),
    )
    compare = _compat_gh_api_json(
        host=pr.host,
        path=compare_path,
        allow_public_fallback=True,
    )
    files = compare.get("files")
    if not isinstance(files, list):
        raise ReviewflowError(
            "GitHub compare payload is missing the `files` list needed for baseline selection."
        )

    additions = 0
    deletions = 0
    changed_files = 0
    for item in files:
        if not isinstance(item, dict):
            continue
        changed_files += 1
        additions += _coerce_int(item.get("additions"))
        deletions += _coerce_int(item.get("deletions"))
    changed_lines = additions + deletions
    files_truncated = len(files) >= GITHUB_COMPARE_FILES_HARD_LIMIT
    divergence = {
        "source": ("github_compare_truncated_files" if files_truncated else "github_compare"),
        "files_truncated": files_truncated,
        "ahead_by": _coerce_int(compare.get("ahead_by")),
        "behind_by": _coerce_int(compare.get("behind_by")),
        "changed_files": changed_files,
        "additions": additions,
        "deletions": deletions,
        "changed_lines": changed_lines,
    }
    selection["repo_default_ref"] = repo_default_ref
    selection["divergence"] = divergence

    within_threshold = (
        divergence["ahead_by"] <= PR_BASELINE_MAX_AHEAD_COMMITS
        and divergence["behind_by"] <= PR_BASELINE_MAX_BEHIND_COMMITS
        and (not files_truncated)
        and divergence["changed_files"] <= PR_BASELINE_MAX_CHANGED_FILES
        and divergence["changed_lines"] <= PR_BASELINE_MAX_CHANGED_LINES
    )
    if within_threshold:
        selection["selected_baseline_ref"] = repo_default_ref
        selection["selection_reason"] = "default_within_threshold"
    else:
        selection["selected_baseline_ref"] = base_ref
        selection["selection_reason"] = "target_diverged"
    return selection


def resolve_session_baseline_selection(*, meta: dict[str, Any]) -> dict[str, Any]:
    baseline = meta.get("baseline_selection") if isinstance(meta.get("baseline_selection"), dict) else {}
    base_ref = str((baseline or {}).get("base_ref") or meta.get("base_ref") or "").strip()
    repo_default_ref = str((baseline or {}).get("repo_default_ref") or "").strip() or None
    selected_baseline_ref = str((baseline or {}).get("selected_baseline_ref") or base_ref).strip() or base_ref
    selection_reason = str((baseline or {}).get("selection_reason") or "").strip()
    if not selection_reason:
        if repo_default_ref and repo_default_ref == selected_baseline_ref == base_ref:
            selection_reason = "target_is_default"
        elif repo_default_ref and repo_default_ref == selected_baseline_ref:
            selection_reason = "default_within_threshold"
        elif repo_default_ref:
            selection_reason = "target_diverged"
        else:
            selection_reason = "default_ref_unavailable"
    divergence = (baseline or {}).get("divergence")
    if not isinstance(divergence, dict):
        if selection_reason == "target_is_default":
            divergence = _zero_divergence_payload(source="legacy_target_is_default")
        elif selection_reason == "default_ref_unavailable":
            divergence = _unavailable_divergence_payload(source="legacy_default_ref_unavailable")
        else:
            divergence = _unavailable_divergence_payload(source="legacy_missing")
    return {
        "base_ref": base_ref,
        "repo_default_ref": repo_default_ref,
        "selected_baseline_ref": selected_baseline_ref,
        "selection_reason": selection_reason,
        "divergence": divergence,
    }


def restore_session_chunkhound_db_from_baseline(
    *,
    meta: dict[str, Any],
    paths: ReviewflowPaths,
    config_path: Path | None,
    pr: PullRequestRef,
    chunkhound_db_path: Path,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any] | None:
    base_cache = meta.get("base_cache") if isinstance(meta.get("base_cache"), dict) else {}
    baseline = resolve_session_baseline_selection(meta=meta)
    selected_baseline_ref = str(baseline.get("selected_baseline_ref") or "").strip()
    refresh_base_cache = False
    try:
        current_chunkhound_version = _run_cmd(["chunkhound", "--version"]).stdout.strip()
    except Exception:
        current_chunkhound_version = ""
    cached_chunkhound_version = str((base_cache or {}).get("chunkhound_version") or "").strip()
    if (
        current_chunkhound_version
        and cached_chunkhound_version
        and cached_chunkhound_version != current_chunkhound_version
    ):
        refresh_base_cache = True
        if selected_baseline_ref:
            log(
                "Session base cache ChunkHound version changed: "
                f"{pr.owner}/{pr.repo}@{selected_baseline_ref} "
                f"({cached_chunkhound_version} -> {current_chunkhound_version})",
                quiet=quiet,
            )

    if chunkhound_db_path.exists():
        if not refresh_base_cache:
            return None
        if chunkhound_db_path.is_dir():
            shutil.rmtree(chunkhound_db_path, ignore_errors=True)
        else:
            chunkhound_db_path.unlink(missing_ok=True)

    base_db_raw = str((base_cache or {}).get("db_path") or "").strip()
    base_db_path = Path(base_db_raw).resolve() if base_db_raw else None
    if refresh_base_cache or not (base_db_path and base_db_path.exists()):
        if not selected_baseline_ref:
            return None
        base_cache = _compat_ensure_base_cache(
            paths=paths,
            config_path=config_path,
            pr=pr,
            base_ref=selected_baseline_ref,
            ttl_hours=DEFAULT_BASE_CACHE_TTL_HOURS,
            refresh=False,
            quiet=quiet,
            no_stream=no_stream,
        )
        meta["base_cache"] = base_cache
        base_db_raw = str((base_cache or {}).get("db_path") or "").strip()
        base_db_path = Path(base_db_raw).resolve() if base_db_raw else None

    if not (base_db_path and base_db_path.exists()):
        return None

    if chunkhound_db_path.exists():
        if chunkhound_db_path.is_dir():
            shutil.rmtree(chunkhound_db_path, ignore_errors=True)
        else:
            chunkhound_db_path.unlink(missing_ok=True)
    chunkhound_db_path.parent.mkdir(parents=True, exist_ok=True)
    copy_duckdb_files(base_db_path, chunkhound_db_path)
    return base_cache if isinstance(base_cache, dict) else None

def cache_status(*, paths: ReviewflowPaths, host: str, owner: str, repo: str, base_ref: str) -> int:
    base_root = base_dir(paths, host, owner, repo, base_ref)
    meta_path = base_root / "meta.json"
    if not meta_path.is_file():
        _eprint(f"No cache meta found: {meta_path}")
        return 2

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    print(json.dumps(meta, indent=2, sort_keys=True))
    return 0

def ttl_expired(indexed_at_iso: str, ttl_hours: int) -> bool:
    try:
        indexed_at = datetime.fromisoformat(indexed_at_iso)
    except Exception:
        return True
    age = datetime.now(timezone.utc) - indexed_at
    return age.total_seconds() > (ttl_hours * 3600)

def ensure_base_cache(
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    progress: Any | None = None,
    pr: PullRequestRef,
    base_ref: str,
    ttl_hours: int,
    refresh: bool,
    hot_start_seed: dict[str, Any] | None = None,
    operator_hot_start_resolver: Callable[[], dict[str, Any] | None] | None = None,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    effective_config_path = config_path or default_reviewflow_config_path()
    base_root = base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
    meta_path = base_root / "meta.json"
    if refresh:
        log(f"Base cache refresh: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return _compat_cache_prime(
            paths=paths,
            config_path=effective_config_path,
            progress=progress,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            reason="refresh requested",
            hot_start_seed=hot_start_seed,
            quiet=quiet,
            no_stream=no_stream,
        )

    if not meta_path.is_file():
        resolved_hot_start_seed = hot_start_seed
        if resolved_hot_start_seed is None and operator_hot_start_resolver is not None:
            resolved_hot_start_seed = operator_hot_start_resolver()
        log(f"Base cache miss: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return _compat_cache_prime(
            paths=paths,
            config_path=effective_config_path,
            progress=progress,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            reason="cache miss",
            hot_start_seed=resolved_hot_start_seed,
            quiet=quiet,
            no_stream=no_stream,
        )

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    try:
        _, chunkhound_meta, _ = load_chunkhound_runtime_config(
            config_path=effective_config_path,
            require=True,
        )
        cfg_fp = fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
    except Exception as e:
        cfg_fp = None
        log(
            f"Base cache config fingerprint failed: {effective_config_path} ({e})",
            quiet=quiet,
        )

    if cfg_fp and meta.get("config_fingerprint") != cfg_fp:
        log(f"Base cache config changed: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return _compat_cache_prime(
            paths=paths,
            config_path=effective_config_path,
            progress=progress,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            reason="config changed",
            quiet=quiet,
            no_stream=no_stream,
        )

    try:
        current_chunkhound_version = _run_cmd(["chunkhound", "--version"]).stdout.strip()
    except Exception:
        current_chunkhound_version = ""
    cached_chunkhound_version = str(meta.get("chunkhound_version") or "").strip()
    if current_chunkhound_version and cached_chunkhound_version != current_chunkhound_version:
        source_db_raw = str(meta.get("db_path") or "").strip()
        source_db_path = Path(source_db_raw).resolve(strict=False) if source_db_raw else None
        with file_lock(base_root / ".cache_prime.lock", quiet=quiet):
            compatibility = _run_base_cache_compatibility_canary(
                paths=paths,
                config_path=effective_config_path,
                pr=pr,
                base_ref=base_ref,
                base_root=base_root,
                source_db_path=(
                    source_db_path
                    if source_db_path is not None
                    else (base_root / "db" / ".chunkhound.db")
                ),
                cached_chunkhound_version=cached_chunkhound_version,
                current_chunkhound_version=current_chunkhound_version,
                quiet=quiet,
            )

            if compatibility.get("decision") == "reuse":
                promoted_db_path = base_root / "db" / ".chunkhound.db"
                promoted_meta = dict(meta)
                promoted_meta["indexed_at"] = _utc_now_iso()
                promoted_meta["db_path"] = str(promoted_db_path)
                promoted_meta["db_size_bytes"] = path_size_bytes(promoted_db_path)
                promoted_meta["chunkhound_version"] = current_chunkhound_version
                promoted_meta["compatibility"] = compatibility
                promoted_meta["cache_origin"] = "compatibility_canary_promoted_reuse"
                write_redacted_json(meta_path, promoted_meta)
                log(
                    "Base cache compatibility canary accepted reuse: "
                    f"{pr.owner}/{pr.repo}@{base_ref}",
                    quiet=quiet,
                )
                return promoted_meta

            log(
                "Base cache compatibility canary rejected reuse: "
                f"{pr.owner}/{pr.repo}@{base_ref}",
                quiet=quiet,
            )
            rebuilt_meta = _cache_prime_locked(
                paths=paths,
                config_path=effective_config_path,
                progress=progress,
                host=pr.host,
                owner=pr.owner,
                repo=pr.repo,
                base_ref=base_ref,
                force=False,
                reason=_version_drift_compatibility_reason(
                    cached_chunkhound_version=cached_chunkhound_version,
                    current_chunkhound_version=current_chunkhound_version,
                ),
                quiet=quiet,
                no_stream=no_stream,
            )
            rebuilt_meta = dict(rebuilt_meta)
            rebuilt_meta["compatibility"] = compatibility
            rebuilt_meta["cache_origin"] = "fresh_rebuild"
            write_redacted_json(meta_path, rebuilt_meta)
            return rebuilt_meta

    if ttl_expired(str(meta.get("indexed_at") or ""), ttl_hours):
        log(f"Base cache expired: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return _compat_cache_prime(
            paths=paths,
            config_path=effective_config_path,
            progress=progress,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            reason="cache expired",
            quiet=quiet,
            no_stream=no_stream,
        )

    log(
        f"Base cache hit: {pr.owner}/{pr.repo}@{base_ref} (indexed_at={meta.get('indexed_at')})",
        quiet=quiet,
    )
    return meta

def path_size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return 0

def same_device(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_dev == b.stat().st_dev
    except Exception:
        return False

def copy_duckdb_files(src_db_path: Path, dst_db_path: Path) -> None:
    # ChunkHound's duckdb backend uses a "db path" that is a directory, e.g. `.chunkhound.db/`,
    # containing `chunks.db` (+ `.wal`) and potentially other files.
    if src_db_path.is_dir():
        if dst_db_path.exists():
            shutil.rmtree(dst_db_path)
        dst_db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_db_path, dst_db_path, copy_function=shutil.copy2)
        return

    dst_db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_db_path, dst_db_path)


def _version_drift_compatibility_reason(
    *,
    cached_chunkhound_version: str,
    current_chunkhound_version: str,
) -> str:
    if cached_chunkhound_version and current_chunkhound_version:
        return (
            "ChunkHound compatibility canary rejected reuse "
            f"({cached_chunkhound_version} -> {current_chunkhound_version})"
        )
    return "ChunkHound compatibility canary rejected reuse"


def _build_base_cache_compatibility_record(
    *,
    cached_chunkhound_version: str,
    current_chunkhound_version: str,
    decision: str,
    result: str,
    reason: str,
    timeout_seconds: int,
    probe_cmd: list[str] | None = None,
    probe_duration_seconds: float | None = None,
    index_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "checked_at": _utc_now_iso(),
        "cached_chunkhound_version": cached_chunkhound_version,
        "current_chunkhound_version": current_chunkhound_version,
        "decision": decision,
        "result": result,
        "reason": " ".join(str(reason or "").strip().split()),
        "probe_timeout_seconds": int(timeout_seconds),
    }
    if probe_cmd:
        record["probe_cmd"] = list(probe_cmd)
    if probe_duration_seconds is not None:
        record["probe_duration_seconds"] = float(probe_duration_seconds)
    if isinstance(index_summary, dict):
        record["index_summary"] = dict(index_summary)
    return record


def _run_base_cache_compatibility_canary(
    *,
    paths: ReviewflowPaths,
    config_path: Path,
    pr: PullRequestRef,
    base_ref: str,
    base_root: Path,
    source_db_path: Path,
    cached_chunkhound_version: str,
    current_chunkhound_version: str,
    quiet: bool,
) -> dict[str, Any]:
    if not source_db_path.exists():
        return _build_base_cache_compatibility_record(
            cached_chunkhound_version=cached_chunkhound_version,
            current_chunkhound_version=current_chunkhound_version,
            decision="rebuild",
            result="missing_source_db",
            reason=f"cached DB missing at {source_db_path}",
            timeout_seconds=CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS,
        )

    effective_config_path = config_path or default_reviewflow_config_path()
    chunkhound_cfg, _, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
        config_path=effective_config_path,
        require=True,
    )

    seed, _ = _sync_seed_checkout(
        paths=paths,
        host=pr.host,
        owner=pr.owner,
        repo=pr.repo,
        base_ref=base_ref,
        quiet=quiet,
    )
    if not seed.exists():
        return _build_base_cache_compatibility_record(
            cached_chunkhound_version=cached_chunkhound_version,
            current_chunkhound_version=current_chunkhound_version,
            decision="rebuild",
            result="missing_seed_repo",
            reason=f"seed repo missing at {seed}",
            timeout_seconds=CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS,
        )

    canary_root = base_root / ".compat_canary"
    shutil.rmtree(canary_root, ignore_errors=True)
    canary_root.mkdir(parents=True, exist_ok=True)
    canary_db_path = canary_root / ".chunkhound.db"
    canary_cfg_path = canary_root / "chunkhound.json"
    materialize_chunkhound_env_config(
        resolved_config=resolved_chunkhound_cfg,
        output_config_path=canary_cfg_path,
        database_provider="duckdb",
        database_path=canary_db_path,
    )

    try:
        copy_duckdb_files(source_db_path, canary_db_path)
    except Exception as exc:
        shutil.rmtree(canary_root, ignore_errors=True)
        return _build_base_cache_compatibility_record(
            cached_chunkhound_version=cached_chunkhound_version,
            current_chunkhound_version=current_chunkhound_version,
            decision="rebuild",
            result="copy_failed",
            reason=f"canary copy failed: {exc}",
            timeout_seconds=CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS,
        )

    env = merged_env(chunkhound_env(source_config_path=chunkhound_cfg.base_config_path))
    probe_cmd = [
        "chunkhound",
        "index",
        str(seed),
        "--config",
        str(canary_cfg_path),
    ]
    log(
        "Base cache compatibility canary: "
        f"{pr.owner}/{pr.repo}@{base_ref} "
        f"({cached_chunkhound_version or 'unknown'} -> {current_chunkhound_version or 'unknown'})",
        quiet=quiet,
    )

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            probe_cmd,
            cwd=str(canary_root),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - started
        shutil.rmtree(canary_root, ignore_errors=True)
        return _build_base_cache_compatibility_record(
            cached_chunkhound_version=cached_chunkhound_version,
            current_chunkhound_version=current_chunkhound_version,
            decision="rebuild",
            result="timeout",
            reason="compatibility canary timed out",
            timeout_seconds=CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS,
            probe_cmd=probe_cmd,
            probe_duration_seconds=duration,
        )

    duration = time.perf_counter() - started
    combined_output = "\n".join(
        part for part in (completed.stdout or "", completed.stderr or "") if part
    )
    index_summary = parse_chunkhound_index_summary(combined_output, scope="base_cache")
    if completed.returncode != 0:
        reason = (
            f"compatibility canary exited with code {completed.returncode}"
            if completed.returncode
            else "compatibility canary failed"
        )
        shutil.rmtree(canary_root, ignore_errors=True)
        return _build_base_cache_compatibility_record(
            cached_chunkhound_version=cached_chunkhound_version,
            current_chunkhound_version=current_chunkhound_version,
            decision="rebuild",
            result="probe_failed",
            reason=reason,
            timeout_seconds=CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS,
            probe_cmd=probe_cmd,
            probe_duration_seconds=duration,
            index_summary=index_summary,
        )

    canonical_db_path = base_root / "db" / ".chunkhound.db"
    canonical_db_path.parent.mkdir(parents=True, exist_ok=True)
    if canonical_db_path.exists():
        if canonical_db_path.is_dir():
            shutil.rmtree(canonical_db_path, ignore_errors=True)
        else:
            canonical_db_path.unlink(missing_ok=True)
    shutil.move(str(canary_db_path), str(canonical_db_path))
    shutil.rmtree(canary_root, ignore_errors=True)
    return _build_base_cache_compatibility_record(
        cached_chunkhound_version=cached_chunkhound_version,
        current_chunkhound_version=current_chunkhound_version,
        decision="reuse",
        result="compatible",
        reason="compatibility canary accepted cached DB reuse",
        timeout_seconds=CHUNKHOUND_COMPATIBILITY_CANARY_TIMEOUT_SECONDS,
        probe_cmd=probe_cmd,
        probe_duration_seconds=duration,
        index_summary=index_summary,
    )

def ensure_clean_git_worktree(*, repo_dir: Path) -> None:
    """Ensure the repo has no local changes that would block branch switches."""
    status = _run_cmd(["git", "-C", str(repo_dir), "status", "--porcelain"]).stdout.strip()
    if not status:
        return
    # Only ever do this inside the sandbox/cache repos that reviewflow owns.
    _run_cmd(["git", "-C", str(repo_dir), "reset", "--hard"])
    _run_cmd(["git", "-C", str(repo_dir), "clean", "-fd"])

__all__ = [
    'build_abort_review_markdown',
    'cache_prime',
    'cache_status',
    'checkout_pr_in_repo',
    'ChunkHoundPromptContract',
    'clone_seed_repo',
    'chunkhound_prompt_contract_for_template',
    'chunkhound_prompt_contracts',
    'compute_pr_stats',
    'copy_duckdb_files',
    'DEFAULT_BASE_CACHE_TTL_HOURS',
    'detect_multipass_plan_abort_contradiction',
    'discover_exact_repo_local_chunkhound_seed_candidate',
    'discover_repo_local_chunkhound_config',
    'ensure_base_cache',
    'ensure_clean_git_worktree',
    'ensure_review_config',
    'file_lock',
    'followup_prompt_template_name_for_profile',
    'gh_api_json',
    'load_embedding_api_key_from_config',
    'materialize_chunkhound_env_config',
    'multipass_prompt_template_names',
    'parse_multipass_plan_json',
    'path_size_bytes',
    'phase',
    'prompt_template_name_for_profile',
    'render_prompt',
    'require_gh_auth',
    'resolve_prompt_profile',
    'resolve_pr_review_baseline_selection',
    'resolve_pr_review_chunkhound_seed_source',
    'resolve_session_baseline_selection',
    'restore_session_chunkhound_db_from_baseline',
    'review_intelligence_prompt_vars',
    'chunkhound_env',
    'same_device',
    'validate_operator_chunkhound_seed_source',
    'validate_and_record_chunkhound_tool_proof',
    'validate_chunkhound_tool_proof',
    'write_pr_context_file',
]
