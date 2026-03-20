from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from chunkhound_summary import parse_chunkhound_index_summary
from cure_branding import PRIMARY_CLI_COMMAND
from cure_errors import ReviewflowError
from cure_output import _eprint, active_output, log
from cure_runtime import (
    ReviewIntelligenceConfig,
    ReviewflowChunkHoundConfig,
    build_review_intelligence_guidance,
    fingerprint_chunkhound_reviewflow_config,
    load_chunkhound_runtime_config,
    load_review_intelligence_config,
    load_reviewflow_chunkhound_config,
)
from cure_sessions import PullRequestRef
from meta import json_fingerprint, write_json, write_redacted_json
from paths import (
    ReviewflowPaths,
    base_dir,
    default_reviewflow_config_path,
    repo_id_for_gh,
    safe_ref_slug,
    seed_dir,
)
from run import ReviewflowSubprocessError, merged_env, run_cmd


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

ChunkHoundToolRequirement = Literal["required", "guidance", "conditional"]


@dataclass(frozen=True)
class ChunkHoundPromptContract:
    search_requirement: ChunkHoundToolRequirement
    code_research_requirement: ChunkHoundToolRequirement
    availability_proof: str = "real_tool_call"
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
    if server and server != "chunkhound":
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


def _read_codex_events_slice(*, path: Path, start_offset: int | None, end_offset: int | None) -> str:
    with path.open("rb") as fh:
        if isinstance(start_offset, int) and start_offset > 0:
            fh.seek(start_offset)
        if isinstance(start_offset, int) and isinstance(end_offset, int) and end_offset >= start_offset:
            payload = fh.read(end_offset - start_offset)
        else:
            payload = fh.read()
    return payload.decode("utf-8", errors="replace")


def validate_codex_chunkhound_tool_proof(
    *,
    provider: str,
    review_stage: str,
    prompt_template_name: str,
    adapter_meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if str(provider or "").strip().lower() != "codex":
        return None
    contract = chunkhound_prompt_contract_for_template(prompt_template_name)
    if contract is None:
        return None

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
        "provider": "codex",
        "review_stage": str(review_stage or "").strip(),
        "prompt_template_name": str(prompt_template_name or "").strip(),
        "required_tools": required_tools,
        "observed_successful_calls": [],
        "ignored_discovery_calls": [],
        "valid": False,
        "failure_reason": None,
        "codex_events_path": raw_events_path or None,
        "codex_events_start_offset": start_offset,
        "codex_events_end_offset": end_offset,
    }

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

    observed_successful_calls: list[str] = []
    ignored_discovery_calls: list[str] = []
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
        if _extract_tool_status(event_type, item) is True and normalized_tool_name not in observed_successful_calls:
            observed_successful_calls.append(normalized_tool_name)

    report["observed_successful_calls"] = observed_successful_calls
    report["ignored_discovery_calls"] = ignored_discovery_calls
    missing_tools = [tool for tool in required_tools if tool not in observed_successful_calls]
    if missing_tools:
        report["failure_reason"] = "missing successful ChunkHound tool call(s): " + ", ".join(
            missing_tools
        )
        return report

    report["valid"] = True
    return report


def validate_and_record_codex_chunkhound_tool_proof(
    *,
    meta: dict[str, Any],
    work_dir: Path,
    provider: str,
    review_stage: str,
    prompt_template_name: str,
    adapter_meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    run_report = validate_codex_chunkhound_tool_proof(
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
    report_payload = {
        "schema_version": 1,
        "updated_at": _utc_now_iso(),
        "provider": "codex",
        "valid": bool(run_report.get("valid")),
        "runs": runs,
    }
    write_json(report_path, report_payload)

    chunkhound_meta = meta.get("chunkhound")
    if not isinstance(chunkhound_meta, dict):
        chunkhound_meta = {}
        meta["chunkhound"] = chunkhound_meta
    chunkhound_meta["tool_validation"] = {
        "provider": "codex",
        "path": str(report_path),
        "valid": bool(report_payload["valid"]),
        "run_count": len(runs),
        "latest_review_stage": run_report["review_stage"],
        "latest_run_valid": bool(run_report["valid"]),
        "failure_reason": run_report.get("failure_reason"),
    }
    return run_report



def review_intelligence_prompt_vars(cfg: ReviewIntelligenceConfig) -> dict[str, str]:
    return {"REVIEW_INTELLIGENCE_GUIDANCE": build_review_intelligence_guidance(cfg)}

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
    host: str,
    owner: str,
    repo: str,
    base_ref: str,
    force: bool,
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
    base_root.mkdir(parents=True, exist_ok=True)
    with file_lock(base_root / ".cache_prime.lock", quiet=quiet):
        seed = seed_dir(paths, host, owner, repo)
        seed.parent.mkdir(parents=True, exist_ok=True)
        with phase(f"cache_seed_sync {owner}/{repo}@{base_ref}", progress=None, quiet=quiet):
            if not seed.exists():
                clone_seed_repo(host=host, owner=owner, repo=repo, seed=seed)
            else:
                # Validate it's a git repo before fetching.
                _run_cmd(["git", "-C", str(seed), "rev-parse", "--is-inside-work-tree"])
                _run_cmd(["git", "-C", str(seed), "fetch", "--prune", "origin"])

            # Reset seed to latest base ref.
            _run_cmd(["git", "-C", str(seed), "fetch", "origin", base_ref])
            _run_cmd(
                ["git", "-C", str(seed), "checkout", "-B", base_ref, f"origin/{base_ref}"]
            )
            base_sha = _run_cmd(["git", "-C", str(seed), "rev-parse", "HEAD"]).stdout.strip()

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

        cfg_fp = fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
        env_cfg_fp = json_fingerprint(ch_cfg_path)
        meta_path = base_root / "meta.json"

        need_reindex = force
        if not need_reindex and meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("config_fingerprint") != cfg_fp:
                    need_reindex = True
            except Exception:
                need_reindex = True

        env = merged_env(chunkhound_env(source_config_path=chunkhound_cfg.base_config_path))
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
            out = active_output()
            if out is not None:
                index_result = out.run_logged_cmd(
                    index_cmd,
                    kind="chunkhound",
                    cwd=base_root,
                    env=env,
                    check=True,
                    stream_requested=stream,
                )
            else:
                index_result = _run_cmd(
                    index_cmd,
                    cwd=base_root,
                    env=env,
                    check=True,
                    stream=stream,
                    stream_label="chunkhound",
                )
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
            "chunkhound_version": _run_cmd(["chunkhound", "--version"]).stdout.strip(),
            "index_cmd": index_cmd,
            "index_duration_seconds": index_result.duration_seconds,
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
    if chunkhound_db_path.exists():
        return None

    base_cache = meta.get("base_cache") if isinstance(meta.get("base_cache"), dict) else {}
    base_db_raw = str((base_cache or {}).get("db_path") or "").strip()
    base_db_path = Path(base_db_raw).resolve() if base_db_raw else None
    if not (base_db_path and base_db_path.exists()):
        baseline = resolve_session_baseline_selection(meta=meta)
        selected_baseline_ref = str(baseline.get("selected_baseline_ref") or "").strip()
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
    pr: PullRequestRef,
    base_ref: str,
    ttl_hours: int,
    refresh: bool,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    effective_config_path = config_path or default_reviewflow_config_path()
    base_root = base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
    meta_path = base_root / "meta.json"
    if refresh or not meta_path.is_file():
        log(f"Base cache refresh: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return _compat_cache_prime(
            paths=paths,
            config_path=effective_config_path,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
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
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            quiet=quiet,
            no_stream=no_stream,
        )

    if ttl_expired(str(meta.get("indexed_at") or ""), ttl_hours):
        log(f"Base cache expired: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return _compat_cache_prime(
            paths=paths,
            config_path=effective_config_path,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
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

    src_wal = src_db_path.with_suffix(src_db_path.suffix + ".wal")
    dst_wal = dst_db_path.with_suffix(dst_db_path.suffix + ".wal")

    dst_db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_db_path, dst_db_path)
    if src_wal.exists():
        shutil.copy2(src_wal, dst_wal)

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
    'validate_and_record_codex_chunkhound_tool_proof',
    'validate_codex_chunkhound_tool_proof',
    'write_pr_context_file',
]
