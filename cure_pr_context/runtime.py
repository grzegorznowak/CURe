"""Run-level PR-context policy, metadata, and persisted-context validation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .corpus import INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS, estimated_tokens
from .orient import is_valid_orientation_brief


def empty_metadata(*, enabled: bool, eligible: bool, enablement_source: str, outcome: str, reason: str) -> dict[str, Any]:
    return {
        "outcome": outcome, "reason": reason, "enabled": enabled,
        "enablement_source": enablement_source, "eligible": eligible,
        "counts": {"fetched": 0, "normalized": 0, "selected": 0, "omitted": 0, "truncated_events": 0},
        "estimated_tokens": {"selected_events": 0, "orientation_prompt": 0, "orientation_output": 0, "injected": 0},
        "provider_usage": {
            "orientation_input_tokens": None, "orientation_output_tokens": None,
            "delivery_input_tokens": None, "delivery_output_tokens": None,
            "fallback_input_tokens": None, "fallback_output_tokens": None,
        },
        "truncation": {
            "event_body": False, "event_count": False, "prompt_budget": False,
            "orientation_output": False, "injected_context": False,
        },
        "latency_ms": {"fetch": 0, "selection": 0, "orientation": 0, "delivery": 0, "total_enrichment": 0},
        "persistence": {
            "discussion_artifact": "not_attempted", "orientation_artifact": "not_attempted",
            "meta_artifact": "not_attempted", "warning": None,
        },
        "context_mode": "off",
    }


def classify_fresh(args: Any) -> dict[str, Any]:
    value = getattr(args, "pr_context", None)
    source = "default" if value is None else "cli_explicit"
    if value is None:
        return empty_metadata(enabled=False, eligible=True, enablement_source=source, outcome="bypassed", reason="disabled_default")
    if value is False:
        return empty_metadata(enabled=False, eligible=True, enablement_source=source, outcome="bypassed", reason="disabled_cli")
    if getattr(args, "prompt", None) is not None or getattr(args, "prompt_file", None) is not None:
        return empty_metadata(enabled=True, eligible=False, enablement_source=source, outcome="bypassed", reason="custom_prompt")
    if str(getattr(args, "prompt_profile", "auto") or "auto") == "default":
        return empty_metadata(enabled=True, eligible=False, enablement_source=source, outcome="bypassed", reason="unsupported_profile")
    return empty_metadata(enabled=True, eligible=True, enablement_source=source, outcome="used", reason="context_delivered")


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_build_metadata(target: dict[str, Any], built: dict[str, Any], brief: str) -> None:
    source_raw = built.get("meta")
    source: dict[str, Any] = source_raw if isinstance(source_raw, dict) else {}
    counts_raw = source.get("counts")
    counts: dict[str, Any] = counts_raw if isinstance(counts_raw, dict) else {}
    target["counts"].update({key: int(counts.get(key, 0)) for key in target["counts"]})
    selection_raw = source.get("selection")
    selection: dict[str, Any] = selection_raw if isinstance(selection_raw, dict) else {}
    orientation_raw = source.get("orientation")
    orientation: dict[str, Any] = orientation_raw if isinstance(orientation_raw, dict) else {}
    target["estimated_tokens"].update({
        "selected_events": int(selection.get("selected_events", 0)),
        "orientation_prompt": int(selection.get("orientation_prompt", 0)),
        "orientation_output": int(orientation.get("estimated_tokens", 0)),
        "injected": estimated_tokens(brief),
    })
    target["truncation"].update({
        "event_body": bool(selection.get("event_body_truncated")),
        "event_count": bool(selection.get("event_count_truncated")),
        "prompt_budget": bool(selection.get("prompt_budget_truncated")),
        "orientation_output": bool(orientation.get("truncated")),
    })
    usage = _mapping(source.get("provider_usage"))
    target["provider_usage"]["orientation_input_tokens"] = _nullable_nonnegative_int(
        usage.get("input_tokens", usage.get("orientation_input_tokens"))
    )
    target["provider_usage"]["orientation_output_tokens"] = _nullable_nonnegative_int(
        usage.get("output_tokens", usage.get("orientation_output_tokens"))
    )
    latency = _mapping(source.get("latency_ms"))
    for key in ("fetch", "selection", "orientation", "total_enrichment"):
        target["latency_ms"][key] = _nonnegative_int(latency.get(key))
    reason = str(source.get("reason") or "")
    if reason in {"no_remote_context", "no_selected_context"}:
        target.update(outcome="bypassed", reason=reason, context_mode="off")
    elif brief:
        target.update(outcome="used", reason="context_delivered", context_mode="on")


def atomic_write_persisted_context(path: Path, brief: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(brief.encode("utf-8"))
    temporary.replace(path)


def read_persisted_context(work_dir: Path, origin: object) -> tuple[str, str]:
    if not isinstance(origin, dict) or origin.get("outcome") != "used":
        return "", "resume_without_used_context"
    path = work_dir / "pr_context_orientation.md"
    try:
        if not path.is_file():
            return "", "resume_invalid_context"
        brief = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        return "", "resume_invalid_context"
    validation_text = brief.replace("\r\n", "\n").replace("\r", "\n")
    if (
        estimated_tokens(brief) > INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS
        or not is_valid_orientation_brief(validation_text)
    ):
        return "", "resume_invalid_context"
    return brief, "context_delivered"


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _nullable_nonnegative_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def metadata_for_resume(origin: object, *, brief: str, reason: str) -> dict[str, Any]:
    """Create a current delivery record with only canonical used-origin acquisition data."""
    used_origin = isinstance(origin, dict) and origin.get("outcome") == "used"
    source = origin if isinstance(origin, dict) else {}
    if used_origin:
        enabled, eligible, enablement_source = True, True, "cli_explicit"
    else:
        raw_enabled = source.get("enabled")
        raw_eligible = source.get("eligible")
        raw_source = source.get("enablement_source")
        enabled = raw_enabled if isinstance(raw_enabled, bool) else False
        eligible = raw_eligible if isinstance(raw_eligible, bool) else True
        enablement_source = raw_source if raw_source in {"default", "cli_explicit"} else "default"
    meta = empty_metadata(
        enabled=enabled,
        eligible=eligible,
        enablement_source=enablement_source,
        outcome="used" if brief else "bypassed",
        reason=reason,
    )
    meta["context_mode"] = "on" if brief else "off"
    meta["estimated_tokens"]["injected"] = estimated_tokens(brief)
    if not used_origin:
        return meta

    counts = _mapping(source.get("counts"))
    for key in meta["counts"]:
        meta["counts"][key] = _nonnegative_int(counts.get(key))
    estimates = _mapping(source.get("estimated_tokens"))
    for key in ("selected_events", "orientation_prompt", "orientation_output"):
        meta["estimated_tokens"][key] = _nonnegative_int(estimates.get(key))
    usage = _mapping(source.get("provider_usage"))
    for key in ("orientation_input_tokens", "orientation_output_tokens"):
        meta["provider_usage"][key] = _nullable_nonnegative_int(usage.get(key))
    truncation = _mapping(source.get("truncation"))
    for key in ("event_body", "event_count", "prompt_budget", "orientation_output"):
        value = truncation.get(key)
        meta["truncation"][key] = value if isinstance(value, bool) else False
    latency = _mapping(source.get("latency_ms"))
    for key in ("fetch", "selection", "orientation"):
        meta["latency_ms"][key] = _nonnegative_int(latency.get(key))
    persistence = _mapping(source.get("persistence"))
    for key in ("discussion_artifact", "orientation_artifact"):
        value = persistence.get(key)
        meta["persistence"][key] = value if value in {"not_attempted", "written", "failed"} else "not_attempted"
    return meta


def preserve_origin(origin: object) -> object:
    return copy.deepcopy(origin)


def atomic_write_metadata(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
