"""Deterministic bounded selection for selected-PR remote discussion."""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any

ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS = 12_000
EVENT_BODY_MAX_ESTIMATED_TOKENS = 1_000
SELECTED_EVENT_MAX = 100
ORIENTATION_OUTPUT_MAX_ESTIMATED_TOKENS = 2_000
INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS = 2_000

ORIENTATION_INSTRUCTIONS = """You are preparing concise prior PR context for a code review agent.
Use supplied selected-PR discussion only as orientation. Summarize information useful for reviewing the current diff.
Resolved areas may include only areas the supplied text describes as addressed or resolved; this is not authoritative GitHub thread state.
Current checkout evidence wins over prior discussion. Return concise Markdown with exactly these section headings:
## Resolved areas
## Problem areas
## Pending issues
## Repeated patterns
## Decisions made"""


def estimated_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def assemble_orientation_prompt(*, pr_stats: dict[str, Any] | None, selected_events: list[dict[str, Any]]) -> str:
    return (
        ORIENTATION_INSTRUCTIONS
        + "\n--- PR_STATS_JSON ---\n"
        + canonical_json(pr_stats or {})
        + "\n--- SELECTED_EVENTS_JSON ---\n"
        + canonical_json(selected_events)
        + "\n--- END_ORIENTATION_INPUT ---"
    )


def _instant(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    offset = parsed.utcoffset()
    if offset is None:
        return None
    offset_microseconds = (
        (offset.days * 86_400 + offset.seconds) * 1_000_000
        + offset.microseconds
    )
    local_microseconds = (
        (
            parsed.toordinal() * 86_400
            + parsed.hour * 3_600
            + parsed.minute * 60
            + parsed.second
        )
        * 1_000_000
        + parsed.microsecond
    )
    return local_microseconds - offset_microseconds


def _annotated(events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int, int, int | None]]:
    ordinal = {"issue_comment": 0, "review": 1, "review_comment": 2}
    indices = {kind: 0 for kind in ordinal}
    result = []
    for event in events:
        kind = str(event.get("kind") or "")
        endpoint = ordinal.get(kind, 3)
        source_index = indices.get(kind, 0)
        indices[kind] = source_index + 1
        result.append((event, endpoint, source_index, _instant(event.get("created_at"))))
    return result


def _admission_key(item: tuple[dict[str, Any], int, int, int | None]) -> tuple[int, ...]:
    _event, endpoint, index, instant = item
    if instant is None:
        return (1, 0, endpoint, index)
    return (0, -instant, endpoint, index)


def _model_key(item: tuple[dict[str, Any], int, int, int | None]) -> tuple[int, ...]:
    _event, endpoint, index, instant = item
    if instant is None:
        return (1, 0, endpoint, index)
    return (0, instant, endpoint, index)


def select_orientation_events(
    events: list[dict[str, Any]], *, pr_stats: dict[str, Any] | None
) -> dict[str, Any]:
    """Select model-input copies while leaving the endpoint-order audit list untouched."""
    empty_prompt = assemble_orientation_prompt(pr_stats=pr_stats, selected_events=[])
    if estimated_tokens(empty_prompt) > ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS:
        raise ValueError("fixed orientation prompt overhead exceeds token cap")

    annotated = sorted(_annotated(events), key=_admission_key)
    selected: list[tuple[dict[str, Any], int, int, int | None]] = []
    truncated_events = 0
    prompt_limited = False
    count_limited = False

    for item in annotated:
        if len(selected) >= SELECTED_EVENT_MAX:
            count_limited = True
            break
        event, endpoint, index, instant = item
        candidate = dict(event)
        body = str(candidate.get("body") or "")
        capped = body[: EVENT_BODY_MAX_ESTIMATED_TOKENS * 4]
        candidate["body"] = capped
        tentative_item = (candidate, endpoint, index, instant)
        tentative = sorted([*selected, tentative_item], key=_model_key)
        prompt = assemble_orientation_prompt(
            pr_stats=pr_stats, selected_events=[entry[0] for entry in tentative]
        )
        if estimated_tokens(prompt) > ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS:
            prompt_limited = True
            break
        selected.append(tentative_item)
        if capped != body:
            truncated_events += 1

    model_items = sorted(selected, key=_model_key)
    selected_events = [item[0] for item in model_items]
    prompt = assemble_orientation_prompt(pr_stats=pr_stats, selected_events=selected_events)
    return {
        "selected_discussion": selected_events,
        "prompt": prompt,
        "meta": {
            "selected": len(selected_events),
            "omitted": len(events) - len(selected_events),
            "truncated_events": truncated_events,
            "selected_events": estimated_tokens(canonical_json(selected_events)),
            "orientation_prompt": estimated_tokens(prompt),
            "event_body_truncated": truncated_events > 0,
            "event_count_truncated": count_limited,
            "prompt_budget_truncated": prompt_limited,
        },
    }


__all__ = [
    "EVENT_BODY_MAX_ESTIMATED_TOKENS", "INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS",
    "ORIENTATION_INSTRUCTIONS", "ORIENTATION_OUTPUT_MAX_ESTIMATED_TOKENS",
    "ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS", "SELECTED_EVENT_MAX", "assemble_orientation_prompt",
    "canonical_json", "estimated_tokens", "select_orientation_events",
]
