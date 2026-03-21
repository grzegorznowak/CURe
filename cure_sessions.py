from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from chunkhound_summary import parse_chunkhound_index_summary
from cure_branding import PRIMARY_CLI_COMMAND
from cure_errors import ReviewflowError
from meta import write_redacted_json


DEFAULT_LEGACY_CODEX_PRESET = "legacy_codex"
DEFAULT_IMPLICIT_CODEX_PRESET = "codex-cli"
IMPLICIT_CODEX_PRESET_SOURCE = "implicit_codex_cli"


def _normalize_llm_preset_name(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text == DEFAULT_LEGACY_CODEX_PRESET:
        return DEFAULT_IMPLICIT_CODEX_PRESET
    return text


def _reviewflow_defaults_meta(value: object) -> dict[str, Any]:
    cfg = value if isinstance(value, dict) else {}
    reviewflow_defaults = cfg.get("reviewflow_defaults")
    if isinstance(reviewflow_defaults, dict):
        return dict(reviewflow_defaults)
    legacy_defaults = cfg.get("legacy_codex_defaults")
    if isinstance(legacy_defaults, dict):
        return dict(legacy_defaults)
    return {}


def _normalize_llm_config_meta(value: object) -> dict[str, Any] | None:
    cfg = value if isinstance(value, dict) else None
    if cfg is None:
        return None
    out = dict(cfg)
    selected_source = str(out.get("selected_preset_source") or "").strip()
    if selected_source == "synthetic_legacy_codex":
        out["selected_preset_source"] = IMPLICIT_CODEX_PRESET_SOURCE
    normalized_selected = _normalize_llm_preset_name(out.get("selected_name"))
    if normalized_selected is not None:
        out["selected_name"] = normalized_selected
    normalized_resolved = _normalize_llm_preset_name(out.get("resolved_preset_id"))
    if normalized_resolved is not None:
        out["resolved_preset_id"] = normalized_resolved
    reviewflow_defaults = _reviewflow_defaults_meta(out)
    if reviewflow_defaults:
        out["reviewflow_defaults"] = reviewflow_defaults
    out.pop("legacy_codex_defaults", None)
    resolved = out.get("resolved") if isinstance(out.get("resolved"), dict) else None
    if resolved is not None:
        normalized_resolved_meta = dict(resolved)
        for key, raw_value in list(normalized_resolved_meta.items()):
            if str(raw_value or "").strip() == DEFAULT_LEGACY_CODEX_PRESET:
                normalized_resolved_meta[key] = "reviewflow_defaults"
        out["resolved"] = normalized_resolved_meta
    return out


def _normalize_pr_identity_value(raw: object) -> str:
    return str(raw or "").strip().lower()


def _saved_session_supports_resume(meta: dict[str, Any]) -> bool:
    llm = resolve_meta_llm(meta)
    return bool(((llm.get("capabilities") or {}).get("supports_resume")))


def _multipass_has_invalid_artifacts(meta: dict[str, Any]) -> bool:
    multipass = meta.get("multipass") if isinstance(meta.get("multipass"), dict) else {}
    validation = multipass.get("validation") if isinstance(multipass.get("validation"), dict) else {}
    mode = str(validation.get("mode") or multipass.get("grounding_mode") or "").strip().lower()
    if mode == "off":
        return False
    invalid = validation.get("invalid_artifacts")
    if isinstance(invalid, list) and invalid:
        return True
    artifacts = validation.get("artifacts")
    if isinstance(artifacts, dict):
        return any(isinstance(value, dict) and (value.get("valid") is False) for value in artifacts.values())
    return bool(validation.get("has_invalid_artifacts"))


@dataclass(frozen=True)
class PullRequestRef:
    host: str
    owner: str
    repo: str
    number: int

    @property
    def owner_repo(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def gh_repo(self) -> str:
        if self.host == "github.com":
            return self.owner_repo
        return f"{self.host}/{self.owner_repo}"


def parse_pr_url(pr_url: str) -> PullRequestRef:
    text = pr_url.strip()
    if "://" not in text:
        text = "https://" + text

    parsed = urlparse(text)
    host = _normalize_pr_identity_value(parsed.hostname)
    if not host:
        raise ReviewflowError(f"Invalid PR URL (missing host): {pr_url}")

    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 4 or parts[2].strip().lower() != "pull":
        raise ReviewflowError(f"Invalid PR URL (expected /OWNER/REPO/pull/NUMBER): {pr_url}")

    owner = _normalize_pr_identity_value(parts[0])
    repo = _normalize_pr_identity_value(parts[1])
    try:
        number = int(parts[3])
    except ValueError as e:
        raise ReviewflowError(f"Invalid PR URL (bad PR number): {pr_url}") from e

    return PullRequestRef(host=host, owner=owner, repo=repo, number=number)


def parse_owner_repo(value: str) -> tuple[str, str, str]:
    text = value.strip().strip("/")
    parts = text.split("/")
    if len(parts) == 2:
        return ("github.com", _normalize_pr_identity_value(parts[0]), _normalize_pr_identity_value(parts[1]))
    if len(parts) == 3:
        return (
            _normalize_pr_identity_value(parts[0]),
            _normalize_pr_identity_value(parts[1]),
            _normalize_pr_identity_value(parts[2]),
        )
    raise ReviewflowError(f"Expected OWNER/REPO or HOST/OWNER/REPO, got: {value}")


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


def _load_session_meta(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_session_meta_strict(meta_path: Path, *, command_name: str) -> dict[str, Any]:
    if not meta_path.is_file():
        raise ReviewflowError(f"{command_name}: missing meta.json at {meta_path}")
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ReviewflowError(f"{command_name}: failed to parse meta.json at {meta_path}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"{command_name}: meta.json must contain a JSON object: {meta_path}")
    return payload


def _tail_file_lines(path: Path, n: int, *, max_bytes: int = 256 * 1024) -> list[str]:
    n = max(0, int(n))
    if n == 0:
        return []
    try:
        if not path.is_file():
            return []
    except Exception:
        return []

    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            buf = b""
            while pos > 0 and buf.count(b"\n") <= n:
                take = min(4096, pos)
                pos -= take
                fh.seek(pos, os.SEEK_SET)
                buf = fh.read(take) + buf
                if len(buf) > max_bytes:
                    buf = buf[-max_bytes:]
                    break
        text = buf.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-n:] if len(lines) > n else lines
    except Exception:
        return []


def _resolve_log_path(*, session_dir: Path, raw: str | None) -> Path | None:
    if not raw:
        return None
    try:
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = (session_dir / path).resolve()
        return path
    except Exception:
        return None


def _resolve_session_relative_path(*, session_dir: Path, raw: str | None, default: Path) -> Path:
    if raw:
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            return (session_dir / path).resolve()
        return path.resolve()
    return default.resolve()


@dataclass(frozen=True)
class ResolvedObservationTarget:
    requested_target: dict[str, Any]
    resolved_target: dict[str, Any]
    resolution_strategy: str
    session_id: str
    session_dir: Path
    meta_path: Path
    meta: dict[str, Any]


def _resolve_session_id_target(raw: str, *, sandbox_root: Path, command_name: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ReviewflowError(f"{command_name} requires a session_id or PR URL.")
    if Path(text).is_absolute() or ("/" in text) or ("\\" in text):
        raise ReviewflowError(
            f"{command_name} expects a session id (folder name) or a PR URL. "
            f"Tip: run `{PRIMARY_CLI_COMMAND} list` to find a session id. Got: {text!r}"
        )
    return text


def _meta_matches_pr(*, meta: dict[str, Any], pr: PullRequestRef) -> bool:
    if _normalize_pr_identity_value(meta.get("host")) != _normalize_pr_identity_value(pr.host):
        return False
    if _normalize_pr_identity_value(meta.get("owner")) != _normalize_pr_identity_value(pr.owner):
        return False
    if _normalize_pr_identity_value(meta.get("repo")) != _normalize_pr_identity_value(pr.repo):
        return False
    try:
        return int(meta.get("number") or 0) == int(pr.number)
    except Exception:
        return False


def resolve_resume_target(target: str, *, sandbox_root: Path, from_phase: str) -> tuple[str, str]:
    raw = str(target or "").strip()
    if not raw:
        raise ReviewflowError("resume requires a session_id.")

    try:
        pr = parse_pr_url(raw)
    except ReviewflowError:
        pr = None

    if pr is None:
        if Path(raw).is_absolute() or ("/" in raw) or ("\\" in raw):
            raise ReviewflowError(
                "resume expects a session id (folder name) or a PR URL. "
                f"Tip: run `{PRIMARY_CLI_COMMAND} list` to find a session id. Got: {raw!r}"
            )
        return (raw, "resume")

    if not sandbox_root.is_dir():
        raise ReviewflowError(
            f"No review sandboxes found under {sandbox_root} (needed to resolve PR {pr.owner}/{pr.repo}#{pr.number})."
        )

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    resumable: list[tuple[datetime, str]] = []
    completed: list[tuple[datetime, str]] = []

    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta = _load_session_meta(entry / "meta.json")
        if not meta or (not _meta_matches_pr(meta=meta, pr=pr)):
            continue

        status = str(meta.get("status") or "").strip().lower()
        notes = meta.get("notes") if isinstance(meta.get("notes"), dict) else {}
        no_index = bool((notes or {}).get("no_index") or False)
        multipass = meta.get("multipass") if isinstance(meta.get("multipass"), dict) else {}
        multipass_enabled = bool((multipass or {}).get("enabled") is True)
        supports_resume = _saved_session_supports_resume(meta)

        if multipass_enabled and (not no_index) and supports_resume and (
            status in {"running", "error"} or _multipass_has_invalid_artifacts(meta)
        ):
            resumed_at = str(meta.get("resumed_at") or "").strip() or None
            failed_at = str(meta.get("failed_at") or "").strip() or None
            completed_at = str(meta.get("completed_at") or "").strip() or None
            created_at = str(meta.get("created_at") or "").strip() or None
            dt = (
                _parse_iso_dt(resumed_at)
                or _parse_iso_dt(failed_at)
                or _parse_iso_dt(completed_at)
                or _parse_iso_dt(created_at)
                or epoch
            )
            resumable.append((dt, entry.name))
            continue

        completed_at = str(meta.get("completed_at") or "").strip() or None
        if status == "done" or completed_at:
            review_md_path = _resolve_session_review_md_path(session_dir=entry, meta=meta)
            if review_md_path is None:
                continue
            created_at = str(meta.get("created_at") or "").strip() or None
            dt = _parse_iso_dt(completed_at) or _parse_iso_dt(created_at) or epoch
            completed.append((dt, entry.name))

    resumable.sort(key=lambda item: item[0], reverse=True)
    completed.sort(key=lambda item: item[0], reverse=True)

    if resumable:
        return (resumable[0][1], "resume")

    if str(from_phase or "auto").strip().lower() != "auto":
        raise ReviewflowError(
            f"No resumable multipass session found for PR {pr.owner}/{pr.repo}#{pr.number}. "
            f"Tip: run `{PRIMARY_CLI_COMMAND} list` to find a session id."
        )

    if completed:
        return (completed[0][1], "followup")

    raise ReviewflowError(
        f"No sessions found for PR {pr.owner}/{pr.repo}#{pr.number} under {sandbox_root}. "
        f"Tip: run `{PRIMARY_CLI_COMMAND} list`."
    )


def resolve_resume_session_id(target: str, *, sandbox_root: Path, from_phase: str) -> str:
    session_id, _ = resolve_resume_target(target, sandbox_root=sandbox_root, from_phase=from_phase)
    return session_id


def _observation_activity_dt(meta: dict[str, Any]) -> datetime:
    return (
        _parse_iso_dt(str(meta.get("resumed_at") or "").strip())
        or _parse_iso_dt(str(meta.get("created_at") or "").strip())
        or datetime(1970, 1, 1, tzinfo=timezone.utc)
    )


def resolve_observation_target(
    target: str,
    *,
    sandbox_root: Path,
    command_name: str,
) -> ResolvedObservationTarget:
    raw = str(target or "").strip()
    if not raw:
        raise ReviewflowError(f"{command_name} requires a session_id or PR URL.")

    try:
        pr = parse_pr_url(raw)
    except ReviewflowError:
        pr = None

    if pr is None:
        session_id = _resolve_session_id_target(raw, sandbox_root=sandbox_root, command_name=command_name)
        session_dir = sandbox_root / session_id
        if not session_dir.is_dir():
            raise ReviewflowError(f"{command_name}: session not found under {sandbox_root}: {session_id}")
        meta_path = session_dir / "meta.json"
        meta = _load_session_meta_strict(meta_path, command_name=command_name)
        host = _normalize_pr_identity_value(meta.get("host")) or "github.com"
        owner = _normalize_pr_identity_value(meta.get("owner"))
        repo = _normalize_pr_identity_value(meta.get("repo"))
        try:
            number = int(meta.get("number") or 0)
        except Exception:
            number = 0
        pr_url = f"https://{host}/{owner}/{repo}/pull/{number}" if owner and repo and number > 0 else None
        return ResolvedObservationTarget(
            requested_target={"raw": raw, "kind": "session_id"},
            resolved_target={"kind": "session", "session_id": session_id, "session_dir": str(session_dir), "pr_url": pr_url},
            resolution_strategy="exact_session_id",
            session_id=session_id,
            session_dir=session_dir,
            meta_path=meta_path,
            meta=meta,
        )

    if not sandbox_root.is_dir():
        raise ReviewflowError(
            f"No review sandboxes found under {sandbox_root} (needed to resolve PR {pr.owner}/{pr.repo}#{pr.number})."
        )

    running: list[tuple[datetime, Path, dict[str, Any]]] = []
    others: list[tuple[datetime, Path, dict[str, Any]]] = []
    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta = _load_session_meta(entry / "meta.json")
        if not meta or (not _meta_matches_pr(meta=meta, pr=pr)):
            continue
        status = str(meta.get("status") or "").strip().lower()
        item = (_observation_activity_dt(meta), entry, meta)
        if status == "running":
            running.append(item)
        else:
            others.append(item)

    strategy = ""
    selected: tuple[datetime, Path, dict[str, Any]] | None = None
    if running:
        running.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        selected = running[0]
        strategy = "newest_running"
    elif others:
        others.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        selected = others[0]
        strategy = "newest_activity"

    if selected is None:
        raise ReviewflowError(
            f"No sessions found for PR {pr.owner}/{pr.repo}#{pr.number} under {sandbox_root}. "
            f"Tip: run `{PRIMARY_CLI_COMMAND} list`."
        )

    _, session_dir, meta = selected
    session_id = str(meta.get("session_id") or session_dir.name).strip() or session_dir.name
    pr_url = f"https://{pr.host}/{pr.owner}/{pr.repo}/pull/{pr.number}"
    return ResolvedObservationTarget(
        requested_target={
            "raw": raw,
            "kind": "pr_url",
            "host": pr.host,
            "owner": pr.owner,
            "repo": pr.repo,
            "number": pr.number,
            "pr_url": pr_url,
        },
        resolved_target={"kind": "session", "session_id": session_id, "session_dir": str(session_dir), "pr_url": pr_url},
        resolution_strategy=strategy,
        session_id=session_id,
        session_dir=session_dir,
        meta_path=session_dir / "meta.json",
        meta=meta,
    )


def _resolve_session_work_dir(*, session_dir: Path, meta: dict[str, Any]) -> Path:
    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    raw = str((meta_paths or {}).get("work_dir") or "").strip()
    if raw:
        path = Path(raw)
        return ((session_dir / path).resolve() if not path.is_absolute() else path.resolve())
    return session_dir / "work"


def _resolve_session_logs_dir(*, session_dir: Path, meta: dict[str, Any], work_dir: Path) -> Path:
    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    raw = str((meta_paths or {}).get("logs_dir") or "").strip()
    if raw:
        path = Path(raw)
        return ((session_dir / path).resolve() if not path.is_absolute() else path.resolve())
    logs = meta.get("logs") if isinstance(meta.get("logs"), dict) else {}
    for key in ("cure", "reviewflow", "chunkhound", "codex"):
        candidate = _resolve_log_path(session_dir=session_dir, raw=str(logs.get(key) or "").strip())
        if candidate is not None:
            return candidate.parent
    return work_dir / "logs"


def _resolve_session_log_paths(*, session_dir: Path, meta: dict[str, Any], logs_dir: Path) -> dict[str, str]:
    logs = meta.get("logs") if isinstance(meta.get("logs"), dict) else {}
    payload: dict[str, str] = {}
    for key in ("cure", "reviewflow", "chunkhound", "codex", "codex_events"):
        candidate = _resolve_log_path(session_dir=session_dir, raw=str(logs.get(key) or "").strip())
        if candidate is None:
            suffix = "codex.events.jsonl" if key == "codex_events" else f"{key}.log"
            fallback = logs_dir / suffix
            candidate = fallback if fallback.exists() else None
        if candidate is not None:
            payload[key] = str(candidate)
    return payload


@dataclass(frozen=True)
class ReviewVerdicts:
    business: str | None
    technical: str | None

    def is_empty(self) -> bool:
        return not (self.business or self.technical)


_DECISION_LINE_RE = re.compile("(?im)^\\s*\\*\\*Decision\\*\\*:\\s*(.+?)\\s*$")
_VERDICT_LINE_RE = re.compile("(?im)^\\s*\\*\\*Verdict\\*\\*:\\s*(.+?)\\s*$")
_SECTION_HEADING_RE = re.compile("(?im)^\\s{0,3}#{1,6}\\s+.+?\\s*$")
_BUSINESS_SECTION_RE = re.compile(
    "(?im)^\\s{0,3}#{1,6}\\s+Business\\s*/\\s*Product\\s+Assessment\\s*$"
)
_TECHNICAL_SECTION_RE = re.compile("(?im)^\\s{0,3}#{1,6}\\s+Technical\\s+Assessment\\s*$")


def normalize_review_verdict(raw: object) -> str | None:
    verdict = str(raw or "").strip()
    if not verdict:
        return None
    verdict = verdict.strip("[]").strip()
    verdict = re.sub("^\\*+|\\*+$", "", verdict).strip()
    if verdict.startswith("`") and verdict.endswith("`") and len(verdict) >= 2:
        verdict = verdict[1:-1].strip()
    verdict = re.sub(r"\\s+", " ", verdict).strip()
    if not verdict:
        return None
    upper = verdict.upper()
    if upper in {"APPROVE", "REJECT"}:
        return upper
    if upper in {"REQUEST CHANGES", "REQUEST_CHANGES"}:
        return "REQUEST CHANGES"
    return verdict


def _extract_markdown_section(text: str, *, heading_re: re.Pattern[str]) -> str | None:
    match = heading_re.search(text or "")
    if match is None:
        return None
    start = match.end()
    next_heading = _SECTION_HEADING_RE.search(text or "", start)
    end = next_heading.start() if next_heading is not None else len(text or "")
    return (text or "")[start:end]


def extract_decision_from_markdown(text: str) -> str | None:
    matches = _DECISION_LINE_RE.findall(text or "")
    if not matches:
        return None
    for raw in reversed(matches):
        decision = normalize_review_verdict(raw)
        if decision:
            return decision
    return None


def normalize_review_verdicts(raw: object) -> ReviewVerdicts | None:
    if isinstance(raw, ReviewVerdicts):
        verdicts = ReviewVerdicts(
            business=normalize_review_verdict(raw.business),
            technical=normalize_review_verdict(raw.technical),
        )
        return None if verdicts.is_empty() else verdicts
    if not isinstance(raw, dict):
        return None
    verdicts = ReviewVerdicts(
        business=normalize_review_verdict(raw.get("business")),
        technical=normalize_review_verdict(raw.get("technical")),
    )
    return None if verdicts.is_empty() else verdicts


def review_verdicts_to_meta(verdicts: ReviewVerdicts) -> dict[str, str | None]:
    return {"business": verdicts.business, "technical": verdicts.technical}


def extract_review_verdicts_from_markdown(text: str) -> ReviewVerdicts | None:
    business_section = _extract_markdown_section(
        text, heading_re=_BUSINESS_SECTION_RE
    )
    technical_section = _extract_markdown_section(
        text, heading_re=_TECHNICAL_SECTION_RE
    )
    business = None
    technical = None
    if business_section is not None:
        match = _VERDICT_LINE_RE.search(business_section)
        if match is not None:
            business = normalize_review_verdict(match.group(1))
    if technical_section is not None:
        match = _VERDICT_LINE_RE.search(technical_section)
        if match is not None:
            technical = normalize_review_verdict(match.group(1))

    verdicts = ReviewVerdicts(business=business, technical=technical)
    if not verdicts.is_empty():
        return verdicts

    legacy = extract_decision_from_markdown(text)
    if legacy is None:
        return None
    return ReviewVerdicts(business=legacy, technical=legacy)


def format_review_verdicts_compact(verdicts: ReviewVerdicts | None) -> str:
    if verdicts is None:
        return "biz=? tech=?"
    return f"biz={verdicts.business or '?'} tech={verdicts.technical or '?'}"


def _parse_codex_flag_assignment(raw: object, *, key: str) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    prefix = f"{key}="
    if not text.startswith(prefix):
        return None
    value = text[len(prefix) :].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value.strip() or None


def _legacy_llm_meta_from_codex(meta: dict[str, Any]) -> dict[str, Any]:
    codex = meta.get("codex") if isinstance(meta.get("codex"), dict) else {}
    cfg = codex.get("config") if isinstance(codex.get("config"), dict) else {}
    resolved = cfg.get("resolved") if isinstance(cfg.get("resolved"), dict) else {}
    model = str(resolved.get("model") or "").strip() or None
    effort = str(resolved.get("model_reasoning_effort") or "").strip() or None
    plan_effort = str(resolved.get("plan_mode_reasoning_effort") or "").strip() or None
    flags = codex.get("flags")
    if isinstance(flags, list):
        flag_items = [str(item) for item in flags if isinstance(item, str)]
        for idx, item in enumerate(flag_items):
            if model is None and item == "-m" and idx + 1 < len(flag_items):
                candidate = str(flag_items[idx + 1]).strip()
                if candidate:
                    model = candidate
            if item != "-c" or idx + 1 >= len(flag_items):
                continue
            assignment = flag_items[idx + 1]
            if effort is None:
                effort = _parse_codex_flag_assignment(assignment, key="model_reasoning_effort")
            if plan_effort is None:
                plan_effort = _parse_codex_flag_assignment(assignment, key="plan_mode_reasoning_effort")
    resume = codex.get("resume") if isinstance(codex.get("resume"), dict) else {}
    return {
        "preset": DEFAULT_IMPLICIT_CODEX_PRESET,
        "transport": "cli",
        "provider": "codex",
        "model": model,
        "reasoning_effort": effort,
        "plan_reasoning_effort": plan_effort,
        "resume": resume,
        "capabilities": {"supports_resume": bool(resume.get("command"))},
    }


def resolve_meta_llm(meta: dict[str, Any]) -> dict[str, Any]:
    llm = meta.get("llm") if isinstance(meta.get("llm"), dict) else {}
    if llm:
        out = dict(llm)
        normalized_preset = _normalize_llm_preset_name(out.get("preset"))
        if normalized_preset is not None:
            out["preset"] = normalized_preset
        normalized_selected = _normalize_llm_preset_name(out.get("selected_name"))
        if normalized_selected is not None:
            out["selected_name"] = normalized_selected
        normalized_config = _normalize_llm_config_meta(out.get("config"))
        if normalized_config is not None:
            out["config"] = normalized_config
        out["capabilities"] = (
            dict(out.get("capabilities"))
            if isinstance(out.get("capabilities"), dict)
            else {"supports_resume": False}
        )
        return out
    return _legacy_llm_meta_from_codex(meta)


def resolve_codex_summary(meta: dict[str, Any]) -> str:
    llm = resolve_meta_llm(meta)
    preset = _normalize_llm_preset_name(llm.get("preset")) or DEFAULT_IMPLICIT_CODEX_PRESET
    model = str(llm.get("model") or "").strip() or None
    effort = str(llm.get("reasoning_effort") or "").strip() or None
    plan_effort = str(llm.get("plan_reasoning_effort") or "").strip() or None
    thinking = effort or plan_effort
    if model and thinking:
        return f"llm={preset}/{model}/{thinking}"
    if model:
        return f"llm={preset}/{model}/?"
    if thinking:
        return f"llm={preset}/?/{thinking}"
    return f"llm={preset}/?"


def review_verdicts_include_reject(verdicts: ReviewVerdicts | None) -> bool:
    if verdicts is None:
        return False
    return verdicts.business == "REJECT" or verdicts.technical == "REJECT"


def persist_review_verdicts_from_markdown(*, meta: dict[str, Any], markdown_path: Path) -> ReviewVerdicts | None:
    try:
        verdicts = extract_review_verdicts_from_markdown(markdown_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if verdicts is not None:
        meta["verdicts"] = review_verdicts_to_meta(verdicts)
    return verdicts


@dataclass(frozen=True)
class ZipSourceArtifact:
    session_id: str
    session_dir: Path
    kind: str
    artifact_path: Path
    completed_at: str | None
    verdicts: ReviewVerdicts | None
    target_head_sha: str

    def sort_dt(self) -> datetime:
        return _parse_iso_dt(self.completed_at) or datetime(1970, 1, 1, tzinfo=timezone.utc)


def _short_sha(value: str | None, *, length: int = 12) -> str:
    text = str(value or "").strip()
    return text[: max(1, int(length))] if text else "?"


def _zip_input_display_line(entry: dict[str, Any], *, markdown: bool) -> str:
    session_id = str(entry.get("session_id") or "?").strip() or "?"
    kind = str(entry.get("kind") or "?").strip() or "?"
    verdicts = normalize_review_verdicts(entry.get("verdicts"))
    if verdicts is None:
        legacy = normalize_review_verdict(entry.get("decision"))
        if legacy is not None:
            verdicts = ReviewVerdicts(business=legacy, technical=legacy)
    verdicts_text = format_review_verdicts_compact(verdicts)
    completed_at = str(entry.get("completed_at") or "?").strip() or "?"
    target_head_sha = _short_sha(str(entry.get("target_head_sha") or "").strip(), length=12)
    path = str(entry.get("path") or "?").strip() or "?"
    if markdown:
        return f"- `{session_id}` • `{kind}` • {verdicts_text} • {completed_at} • head `{target_head_sha}` • `{path}`"
    return f"- {session_id} [{kind}] {verdicts_text} {completed_at} head {target_head_sha} {path}"


def build_zip_input_display_lines(*, inputs_meta: list[dict[str, Any]], markdown: bool = False) -> list[str]:
    return [_zip_input_display_line(entry, markdown=markdown) for entry in inputs_meta if isinstance(entry, dict)]


def append_zip_inputs_provenance(*, markdown_path: Path, inputs_meta: list[dict[str, Any]]) -> None:
    if not markdown_path.is_file():
        raise ReviewflowError(f"zip: output markdown missing: {markdown_path}")
    body = markdown_path.read_text(encoding="utf-8")
    if not body.endswith("\n"):
        body += "\n"
    lines = build_zip_input_display_lines(inputs_meta=inputs_meta, markdown=True)
    if not lines:
        return
    section = "\n".join(["---", "## Inputs Processed", *lines]) + "\n"
    markdown_path.write_text(body + "\n" + section, encoding="utf-8")


def _resolve_session_review_md_path(*, session_dir: Path, meta: dict[str, Any]) -> Path | None:
    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    raw_review_md = str((meta_paths or {}).get("review_md") or (session_dir / "review.md")).strip()
    review_md_path = Path(raw_review_md) if raw_review_md else (session_dir / "review.md")
    review_md_path = (
        (session_dir / review_md_path).resolve() if not review_md_path.is_absolute() else review_md_path.resolve()
    )
    return review_md_path if review_md_path.is_file() else None


def _resolve_session_verdicts(*, meta_path: Path, meta: dict[str, Any], review_md_path: Path) -> ReviewVerdicts | None:
    stored = normalize_review_verdicts(meta.get("verdicts"))
    if stored is not None:
        normalized = review_verdicts_to_meta(stored)
        if meta.get("verdicts") != normalized:
            meta["verdicts"] = normalized
            try:
                write_redacted_json(meta_path, meta)
            except Exception:
                pass
        return stored
    legacy = normalize_review_verdict(meta.get("decision"))
    if legacy is not None:
        verdicts = ReviewVerdicts(business=legacy, technical=legacy)
        meta["verdicts"] = review_verdicts_to_meta(verdicts)
        try:
            write_redacted_json(meta_path, meta)
        except Exception:
            pass
        return verdicts
    extracted = extract_review_verdicts_from_markdown(review_md_path.read_text(encoding="utf-8"))
    if extracted is not None:
        meta["verdicts"] = review_verdicts_to_meta(extracted)
        try:
            write_redacted_json(meta_path, meta)
        except Exception:
            pass
    return extracted


def _resolve_artifact_verdicts(*, meta: dict[str, Any], artifact_path: Path) -> ReviewVerdicts | None:
    stored = normalize_review_verdicts(meta.get("verdicts"))
    if stored is not None:
        return stored
    legacy = normalize_review_verdict(meta.get("decision"))
    if legacy is not None:
        return ReviewVerdicts(business=legacy, technical=legacy)
    try:
        return extract_review_verdicts_from_markdown(artifact_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_session_review_head_sha(*, meta: dict[str, Any]) -> str | None:
    for key in ("review_head_sha", "head_sha"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return None


def _resolve_latest_session_artifact_path(*, session_dir: Path, meta: dict[str, Any], review_md_path: Path) -> Path:
    latest_path = review_md_path
    latest_dt = _parse_iso_dt(str(meta.get("completed_at") or "").strip())
    followups = meta.get("followups") if isinstance(meta.get("followups"), list) else []
    for followup in followups:
        if not isinstance(followup, dict):
            continue
        raw_output = str(followup.get("output_path") or "").strip()
        if not raw_output:
            continue
        candidate = _resolve_session_relative_path(session_dir=session_dir, raw=raw_output, default=session_dir / raw_output)
        if not candidate.is_file():
            continue
        candidate_dt = _parse_iso_dt(str(followup.get("completed_at") or "").strip())
        if latest_dt is None or (candidate_dt is not None and candidate_dt >= latest_dt):
            latest_path = candidate
            latest_dt = candidate_dt
    return latest_path


@dataclass(frozen=True)
class HistoricalReviewSession:
    session_id: str
    session_dir: Path
    review_md_path: Path
    created_at: str | None
    completed_at: str | None
    verdicts: ReviewVerdicts | None
    codex_summary: str = "codex=?"
    review_head_sha: str | None = None

    def sort_dt(self) -> datetime:
        return _parse_iso_dt(self.completed_at) or _parse_iso_dt(self.created_at) or datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class InteractiveReviewSession:
    session_id: str
    session_dir: Path
    host: str
    owner: str
    repo: str
    number: int
    repo_slug: str
    review_md_path: Path
    latest_artifact_path: Path
    created_at: str | None
    completed_at: str | None
    verdicts: ReviewVerdicts | None
    codex_summary: str
    resume_command: str
    provider: str = "codex"
    supports_resume: bool = True

    def sort_dt(self) -> datetime:
        return _parse_iso_dt(self.completed_at) or _parse_iso_dt(self.created_at) or datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CleanupSession:
    session_id: str
    session_dir: Path
    host: str
    owner: str
    repo: str
    number: int
    repo_slug: str
    title: str
    status: str
    created_at: str | None
    completed_at: str | None
    failed_at: str | None
    resumed_at: str | None = None
    verdicts: ReviewVerdicts | None = None
    codex_summary: str = "codex=?"
    size_bytes: int = 0
    path_display: str = ""
    is_running: bool = False
    is_recent: bool = False
    is_risky: bool = False

    def activity_dt(self) -> datetime:
        return (
            _parse_iso_dt(self.completed_at)
            or _parse_iso_dt(self.failed_at)
            or _parse_iso_dt(self.resumed_at)
            or _parse_iso_dt(self.created_at)
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        )

    def age_td(self, *, now: datetime) -> timedelta:
        delta = now - self.activity_dt()
        return timedelta(0) if delta.total_seconds() < 0 else delta


def _cleanup_now() -> datetime:
    return datetime.now(timezone.utc)


def _cleanup_dir_size_bytes(path: Path) -> int:
    total = 0
    try:
        for child in path.rglob("*"):
            try:
                if child.is_file():
                    total += int(child.stat().st_size)
            except Exception:
                continue
    except Exception:
        return 0
    return total


def scan_completed_sessions_for_pr(*, sandbox_root: Path, pr: PullRequestRef) -> list[HistoricalReviewSession]:
    if not sandbox_root.is_dir():
        return []
    sessions: list[HistoricalReviewSession] = []
    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        meta = _load_session_meta(meta_path)
        if not meta or str(meta.get("status") or "") != "done" or (not _meta_matches_pr(meta=meta, pr=pr)):
            continue
        review_md_path = _resolve_session_review_md_path(session_dir=entry, meta=meta)
        if review_md_path is None:
            continue
        sessions.append(
            HistoricalReviewSession(
                session_id=str(meta.get("session_id") or entry.name),
                session_dir=entry,
                review_md_path=review_md_path,
                created_at=str(meta.get("created_at") or "").strip() or None,
                completed_at=str(meta.get("completed_at") or "").strip() or None,
                verdicts=_resolve_session_verdicts(meta_path=meta_path, meta=meta, review_md_path=review_md_path),
                codex_summary=resolve_codex_summary(meta),
                review_head_sha=_resolve_session_review_head_sha(meta=meta),
            )
        )
    sessions.sort(key=lambda item: item.sort_dt(), reverse=True)
    return sessions


def scan_interactive_review_sessions(*, sandbox_root: Path) -> list[InteractiveReviewSession]:
    if not sandbox_root.is_dir():
        return []
    sessions: list[InteractiveReviewSession] = []
    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        meta = _load_session_meta(meta_path)
        if not meta or str(meta.get("status") or "").strip() != "done":
            continue
        review_md_path = _resolve_session_review_md_path(session_dir=entry, meta=meta)
        if review_md_path is None:
            continue
        llm_meta = resolve_meta_llm(meta)
        llm_resume = llm_meta.get("resume") if isinstance(llm_meta.get("resume"), dict) else {}
        host = _normalize_pr_identity_value(meta.get("host")) or "?"
        owner = _normalize_pr_identity_value(meta.get("owner")) or "?"
        repo = _normalize_pr_identity_value(meta.get("repo")) or "?"
        try:
            number = int(meta.get("number") or 0)
        except Exception:
            number = 0
        sessions.append(
            InteractiveReviewSession(
                session_id=str(meta.get("session_id") or entry.name),
                session_dir=entry,
                host=host,
                owner=owner,
                repo=repo,
                number=number,
                repo_slug=f"{owner}/{repo}#{number}",
                review_md_path=review_md_path,
                latest_artifact_path=_resolve_latest_session_artifact_path(session_dir=entry, meta=meta, review_md_path=review_md_path),
                created_at=str(meta.get("created_at") or "").strip() or None,
                completed_at=str(meta.get("completed_at") or "").strip() or None,
                verdicts=_resolve_session_verdicts(meta_path=meta_path, meta=meta, review_md_path=review_md_path),
                codex_summary=resolve_codex_summary(meta),
                resume_command=str((llm_resume or {}).get("command") or "").strip(),
                provider=str(llm_meta.get("provider") or "unknown").strip() or "unknown",
                supports_resume=bool(((llm_meta.get("capabilities") or {}).get("supports_resume"))),
            )
        )
    sessions.sort(key=lambda item: item.sort_dt(), reverse=True)
    return sessions


def scan_cleanup_sessions(*, sandbox_root: Path) -> list[CleanupSession]:
    if not sandbox_root.is_dir():
        return []
    now = _cleanup_now()
    sessions: list[CleanupSession] = []
    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        meta = _load_session_meta(meta_path)
        if not meta:
            continue
        host = _normalize_pr_identity_value(meta.get("host")) or "?"
        owner = _normalize_pr_identity_value(meta.get("owner")) or "?"
        repo = _normalize_pr_identity_value(meta.get("repo")) or "?"
        try:
            number = int(meta.get("number") or 0)
        except Exception:
            number = 0
        repo_slug = f"{owner}/{repo}#{number if number else '?'}"
        if host not in {"", "?", "github.com"}:
            repo_slug = f"{host}:{repo_slug}"
        review_md_path = _resolve_session_review_md_path(session_dir=entry, meta=meta)
        verdicts = (
            _resolve_session_verdicts(meta_path=meta_path, meta=meta, review_md_path=review_md_path)
            if review_md_path is not None
            else None
        )
        created_at = str(meta.get("created_at") or "").strip() or None
        completed_at = str(meta.get("completed_at") or "").strip() or None
        failed_at = str(meta.get("failed_at") or "").strip() or None
        resumed_at = str(meta.get("resumed_at") or "").strip() or None
        status = str(meta.get("status") or "").strip().lower() or "unknown"
        activity_dt = _parse_iso_dt(completed_at) or _parse_iso_dt(failed_at) or _parse_iso_dt(resumed_at) or _parse_iso_dt(created_at) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        age = now - activity_dt
        if age.total_seconds() < 0:
            age = timedelta(0)
        sessions.append(
            CleanupSession(
                session_id=str(meta.get("session_id") or entry.name),
                session_dir=entry,
                host=host,
                owner=owner,
                repo=repo,
                number=number,
                repo_slug=repo_slug,
                title=str(meta.get("title") or "").strip(),
                status=status,
                created_at=created_at,
                completed_at=completed_at,
                failed_at=failed_at,
                resumed_at=resumed_at,
                verdicts=verdicts,
                codex_summary=resolve_codex_summary(meta),
                size_bytes=_cleanup_dir_size_bytes(entry),
                path_display=str(entry),
                is_running=(status == "running"),
                is_recent=(age < timedelta(days=1)),
                is_risky=(status == "running" or age < timedelta(days=1)),
            )
        )
    sessions.sort(key=lambda item: (-item.activity_dt().timestamp(), item.session_id))
    return sessions


def select_zip_sources_for_pr_head(*, sandbox_root: Path, pr: PullRequestRef, head_sha: str) -> list[ZipSourceArtifact]:
    head = str(head_sha or "").strip().lower()
    if not head:
        raise ReviewflowError("zip: missing head SHA")
    if not sandbox_root.is_dir():
        return []

    selected_by_session: dict[str, ZipSourceArtifact] = {}
    kind_rank = {"review": 0, "followup": 1}
    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta = _load_session_meta(entry / "meta.json")
        if not meta or str(meta.get("status") or "") != "done" or (not _meta_matches_pr(meta=meta, pr=pr)):
            continue

        session_id = str(meta.get("session_id") or entry.name)
        review_md_path = _resolve_session_relative_path(
            session_dir=entry,
            raw=str(((meta.get("paths") or {}).get("review_md") if isinstance(meta.get("paths"), dict) else "") or "").strip(),
            default=entry / "review.md",
        )
        review_head_sha = str(meta.get("head_sha") or "").strip().lower()
        review_completed_at = str(meta.get("completed_at") or meta.get("created_at") or "").strip() or None
        if review_md_path.is_file() and review_head_sha == head:
            review_verdicts = _resolve_session_verdicts(meta_path=entry / "meta.json", meta=meta, review_md_path=review_md_path)
            if not review_verdicts_include_reject(review_verdicts):
                selected_by_session[session_id] = ZipSourceArtifact(
                    session_id=session_id,
                    session_dir=entry,
                    kind="review",
                    artifact_path=review_md_path,
                    completed_at=review_completed_at,
                    verdicts=review_verdicts,
                    target_head_sha=review_head_sha,
                )

        followups = meta.get("followups") if isinstance(meta.get("followups"), list) else []
        for followup in followups:
            if not isinstance(followup, dict):
                continue
            followup_head_sha = str(followup.get("head_sha_after") or "").strip().lower()
            if followup_head_sha != head:
                continue
            output_path = str(followup.get("output_path") or "").strip()
            if not output_path:
                continue
            artifact_path = _resolve_session_relative_path(session_dir=entry, raw=output_path, default=entry / output_path)
            if not artifact_path.is_file():
                continue
            verdicts = _resolve_artifact_verdicts(meta=followup, artifact_path=artifact_path)
            if review_verdicts_include_reject(verdicts):
                continue
            candidate = ZipSourceArtifact(
                session_id=session_id,
                session_dir=entry,
                kind="followup",
                artifact_path=artifact_path,
                completed_at=str(followup.get("completed_at") or "").strip() or None,
                verdicts=verdicts,
                target_head_sha=followup_head_sha,
            )
            previous = selected_by_session.get(session_id)
            if previous is None or candidate.sort_dt() > previous.sort_dt() or (
                candidate.sort_dt() == previous.sort_dt() and kind_rank.get(candidate.kind, 0) > kind_rank.get(previous.kind, 0)
            ):
                selected_by_session[session_id] = candidate

    sources = list(selected_by_session.values())
    sources.sort(key=lambda item: item.sort_dt(), reverse=True)
    return sources


def build_status_payload(target: str, *, sandbox_root: Path, command_name: str = "status") -> dict[str, Any]:
    resolved = resolve_observation_target(target, sandbox_root=sandbox_root, command_name=command_name)
    meta = _load_session_meta_strict(resolved.meta_path, command_name=command_name)
    session_dir = resolved.session_dir
    work_dir = _resolve_session_work_dir(session_dir=session_dir, meta=meta)
    logs_dir = _resolve_session_logs_dir(session_dir=session_dir, meta=meta, work_dir=work_dir)
    logs = _resolve_session_log_paths(session_dir=session_dir, meta=meta, logs_dir=logs_dir)
    review_md_path = _resolve_session_review_md_path(session_dir=session_dir, meta=meta)
    repo_dir_raw = str(((meta.get("paths") or {}).get("repo_dir") if isinstance(meta.get("paths"), dict) else "") or (session_dir / "repo")).strip()
    repo_dir = Path(repo_dir_raw)
    repo_dir = ((session_dir / repo_dir).resolve() if not repo_dir.is_absolute() else repo_dir.resolve())
    latest_artifact = None
    if review_md_path is not None:
        latest_artifact = {"path": str(_resolve_latest_session_artifact_path(session_dir=session_dir, meta=meta, review_md_path=review_md_path))}

    llm_meta = resolve_meta_llm(meta)
    llm_payload = dict(llm_meta) if llm_meta else None
    if llm_payload is not None:
        llm_payload["summary"] = resolve_codex_summary(meta)

    agent_runtime = meta.get("agent_runtime") if isinstance(meta.get("agent_runtime"), dict) else None
    agent_runtime_payload = dict(agent_runtime) if agent_runtime else None
    if agent_runtime_payload is not None:
        profile = str(agent_runtime_payload.get("profile") or "").strip()
        provider = str(agent_runtime_payload.get("provider") or "").strip()
        if profile or provider:
            agent_runtime_payload["summary"] = "/".join(part for part in (profile, provider) if part)

    chunkhound_payload = None
    chunkhound_meta = meta.get("chunkhound") if isinstance(meta.get("chunkhound"), dict) else {}
    last_index = (
        dict(chunkhound_meta.get("last_index"))
        if isinstance(chunkhound_meta.get("last_index"), dict)
        else None
    )
    if last_index is not None:
        chunkhound_payload = {"last_index": last_index}
    elif isinstance(logs.get("chunkhound"), str):
        try:
            parsed = parse_chunkhound_index_summary(
                Path(str(logs["chunkhound"])).read_text(encoding="utf-8")
            )
        except Exception:
            parsed = None
        if parsed is not None:
            chunkhound_payload = {"last_index": parsed}
    access = chunkhound_meta.get("access") if isinstance(chunkhound_meta.get("access"), dict) else None
    if access is not None:
        if chunkhound_payload is None:
            chunkhound_payload = {}
        chunkhound_payload["access"] = dict(access)

    host = _normalize_pr_identity_value(meta.get("host")) or "github.com"
    owner = _normalize_pr_identity_value(meta.get("owner"))
    repo = _normalize_pr_identity_value(meta.get("repo"))
    try:
        number = int(meta.get("number") or 0)
    except Exception:
        number = 0
    pr_url = f"https://{host}/{owner}/{repo}/pull/{number}" if owner and repo and number > 0 else None
    payload: dict[str, Any] = {
        "schema_version": 2,
        "kind": "cure.status",
        "requested_target": resolved.requested_target,
        "resolved_target": resolved.resolved_target,
        "resolution_strategy": resolved.resolution_strategy,
        "session_id": resolved.session_id,
        "status": str(meta.get("status") or "").strip() or "unknown",
        "phase": str(meta.get("phase") or "").strip() or "unknown",
        "phases": meta.get("phases") if isinstance(meta.get("phases"), dict) else {},
        "pr": {"host": host, "owner": owner, "repo": repo, "number": number, "pr_url": pr_url},
        "paths": {
            "session_dir": str(session_dir),
            "repo_dir": str(repo_dir),
            "work_dir": str(work_dir),
            "logs_dir": str(logs_dir),
            "review_md": str(review_md_path) if review_md_path is not None else None,
            "meta_json": str(resolved.meta_path),
        },
        "logs": logs,
    }
    if isinstance(meta.get("live_progress"), dict):
        payload["live_progress"] = dict(meta.get("live_progress"))
    if latest_artifact is not None:
        payload["latest_artifact"] = latest_artifact
    if llm_payload is not None:
        payload["llm"] = llm_payload
    if agent_runtime_payload is not None:
        payload["agent_runtime"] = agent_runtime_payload
    if chunkhound_payload is not None:
        payload["chunkhound"] = chunkhound_payload
    if isinstance(meta.get("error"), dict):
        payload["error"] = meta.get("error")
        payload["terminal_error"] = meta.get("error")
    return payload
