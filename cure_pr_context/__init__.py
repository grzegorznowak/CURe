"""Bounded selected-PR remote discussion context."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from .corpus import select_orientation_events
from .fetcher import fetch_pr_discussion
from .orient import (
    InjectedContextFinalizationFailure,
    OrientationFinalizationFailure,
    OrientationOutputFinalizationFailure,
    build_orientation_brief,
)

GhFetch = Callable[[str], list[Any]]
RunLlm = Callable[[str], str]
UsageObserver = Callable[[], Mapping[str, int] | None]


class OrientationProviderExecutionFailure(RuntimeError):
    """Marks only an orientation provider execution failure as degradable."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


class PrContextStageError(RuntimeError):
    """Failure attributed to one named PR-context enrichment stage."""

    def __init__(
        self,
        stage: str,
        cause: Exception,
        *,
        meta: dict[str, Any] | None = None,
        discussion: list[dict[str, Any]] | None = None,
    ) -> None:
        self.stage = stage
        self.meta = dict(meta or {})
        self.discussion = list(discussion) if discussion is not None else None
        super().__init__(str(cause))


def build_pr_context(
    *,
    pr: Any,
    pr_stats: dict[str, Any] | None,
    gh_fetch: GhFetch,
    run_llm: RunLlm,
    usage_observer: UsageObserver | None = None,
) -> dict[str, Any]:
    """Fetch, preserve, select, and orient remote discussion without persistence."""
    total_started = time.monotonic()
    fetch_started = time.monotonic()
    fetched_count = 0

    def record_fetched(count: int) -> None:
        nonlocal fetched_count
        fetched_count = count

    try:
        discussion = fetch_pr_discussion(
            pr=pr, gh_fetch=gh_fetch, fetched_observer=record_fetched
        )
    except Exception as exc:
        fetch_ms = int(max(0.0, time.monotonic() - fetch_started) * 1000)
        total_ms = int(max(0.0, time.monotonic() - total_started) * 1000)
        raise PrContextStageError(
            "fetch_failed",
            exc,
            meta={
                "counts": {
                    "fetched": fetched_count,
                    "normalized": 0,
                    "selected": 0,
                    "omitted": 0,
                    "truncated_events": 0,
                },
                "latency_ms": {
                    "fetch": fetch_ms,
                    "selection": 0,
                    "orientation": 0,
                    "total_enrichment": total_ms,
                },
            },
        ) from exc
    fetch_ms = int(max(0.0, time.monotonic() - fetch_started) * 1000)
    base_counts = {
        "fetched": fetched_count, "normalized": len(discussion), "selected": 0,
        "omitted": 0, "truncated_events": 0,
    }
    if not discussion:
        return {
            "orientation_brief": "", "discussion": discussion, "selected_discussion": [],
            "meta": {
                "reason": "no_remote_context", "counts": base_counts,
                "latency_ms": {
                    "fetch": fetch_ms, "selection": 0, "orientation": 0,
                    "total_enrichment": int(max(0.0, time.monotonic() - total_started) * 1000),
                },
            },
        }

    selection_started = time.monotonic()
    try:
        selection = select_orientation_events(discussion, pr_stats=pr_stats)
        selected = selection["selected_discussion"]
        selection_meta = selection["meta"]
    except Exception as exc:
        selection_ms = int(max(0.0, time.monotonic() - selection_started) * 1000)
        raise PrContextStageError(
            "selection_failed",
            exc,
            meta={
                "counts": base_counts,
                "latency_ms": {
                    "fetch": fetch_ms,
                    "selection": selection_ms,
                    "orientation": 0,
                    "total_enrichment": int(
                        max(0.0, time.monotonic() - total_started) * 1000
                    ),
                },
            },
            discussion=discussion,
        ) from exc
    selection_ms = int(max(0.0, time.monotonic() - selection_started) * 1000)
    counts = {
        **base_counts,
        "selected": selection_meta["selected"],
        "omitted": selection_meta["omitted"],
        "truncated_events": selection_meta["truncated_events"],
    }
    if not selected:
        return {
            "orientation_brief": "", "discussion": discussion, "selected_discussion": [],
            "meta": {
                "reason": "no_selected_context", "counts": counts, "selection": selection_meta,
                "latency_ms": {
                    "fetch": fetch_ms, "selection": selection_ms, "orientation": 0,
                    "total_enrichment": int(max(0.0, time.monotonic() - total_started) * 1000),
                },
            },
        }

    orientation_started = time.monotonic()
    try:
        orientation = build_orientation_brief(
            discussion=selected, pr_stats=pr_stats or {}, run_llm=run_llm
        )
    except (OrientationProviderExecutionFailure, OrientationOutputFinalizationFailure) as exc:
        try:
            usage = usage_observer() if usage_observer is not None else None
        except Exception:
            usage = None
        orientation_ms = int(max(0.0, time.monotonic() - orientation_started) * 1000)
        raise PrContextStageError(
            "orientation_failed",
            exc,
            meta={
                "counts": counts,
                "selection": selection_meta,
                "provider_usage": dict(usage) if usage else None,
                "latency_ms": {
                    "fetch": fetch_ms,
                    "selection": selection_ms,
                    "orientation": orientation_ms,
                    "total_enrichment": int(
                        max(0.0, time.monotonic() - total_started) * 1000
                    ),
                },
            },
            discussion=discussion,
        ) from exc
    try:
        usage = usage_observer() if usage_observer is not None else None
    except Exception:
        usage = None
    orientation_ms = int(max(0.0, time.monotonic() - orientation_started) * 1000)
    return {
        "orientation_brief": orientation["brief"],
        "discussion": discussion,
        "selected_discussion": selected,
        "meta": {
            "reason": "context_built", "counts": counts, "selection": selection_meta,
            "orientation": orientation["meta"], "provider_usage": dict(usage) if usage else None,
            "latency_ms": {
                "fetch": fetch_ms, "selection": selection_ms, "orientation": orientation_ms,
                "total_enrichment": int(max(0.0, time.monotonic() - total_started) * 1000),
            },
        },
    }


__all__ = [
    "InjectedContextFinalizationFailure", "OrientationFinalizationFailure",
    "OrientationOutputFinalizationFailure", "OrientationProviderExecutionFailure",
    "PrContextStageError",
    "build_pr_context", "build_orientation_brief",
    "fetch_pr_discussion", "select_orientation_events",
]
