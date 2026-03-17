from __future__ import annotations

import re
from typing import Any, Iterable


_INITIAL_STATS_RE = re.compile(
    r"Initial stats:\s+(?P<files>\d+)\s+files,\s+(?P<chunks>\d+)\s+chunks,\s+(?P<embeddings>\d+)\s+embeddings"
)
_COUNT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("processed_files", re.compile(r"Processed:\s+(?P<value>\d+)\s+files")),
    ("skipped_files", re.compile(r"Skipped:\s+(?P<value>\d+)\s+files")),
    ("error_files", re.compile(r"Errors:\s+(?P<value>\d+)\s+files")),
    ("total_chunks", re.compile(r"Total chunks:\s+(?P<value>\d+)")),
    ("embeddings", re.compile(r"Embeddings:\s+(?P<value>\d+)")),
)
_TIME_RE = re.compile(r"Time:\s+(?P<value>.+)$")


def parse_chunkhound_index_summary(
    source: str | Iterable[str],
    *,
    scope: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(source, str):
        lines = source.splitlines()
    else:
        lines = [str(line) for line in source]

    summary: dict[str, Any] = {}
    for raw in lines:
        text = str(raw or "").strip()
        if not text:
            continue

        match = _INITIAL_STATS_RE.match(text)
        if match:
            summary["initial_files"] = int(match.group("files"))
            summary["initial_chunks"] = int(match.group("chunks"))
            summary["initial_embeddings"] = int(match.group("embeddings"))
            continue

        handled = False
        for key, pattern in _COUNT_PATTERNS:
            match = pattern.match(text)
            if match:
                summary[key] = int(match.group("value"))
                handled = True
                break
        if handled:
            continue

        match = _TIME_RE.match(text)
        if match:
            summary["duration_text"] = match.group("value").strip()

    if not summary:
        return None
    if scope:
        summary["scope"] = str(scope)
    return summary


def render_chunkhound_index_context_lines(summary: dict[str, Any]) -> list[str]:
    if not isinstance(summary, dict) or not summary:
        return []

    scope = str(summary.get("scope") or "").strip()
    scope_label = {
        "base_cache": "base cache",
        "topup": "top-up",
        "followup": "follow-up",
    }.get(scope, scope.replace("_", " ").strip())

    lines: list[str] = []
    title = "Index"
    if scope_label:
        title += f": {scope_label}"
    lines.append(title)

    run_bits: list[str] = []
    if isinstance(summary.get("processed_files"), int):
        run_bits.append(f"{summary['processed_files']} proc")
    if isinstance(summary.get("skipped_files"), int):
        run_bits.append(f"{summary['skipped_files']} skip")
    if isinstance(summary.get("error_files"), int):
        run_bits.append(f"{summary['error_files']} err")
    if run_bits:
        lines.append("Run: " + " · ".join(run_bits))

    output_bits: list[str] = []
    if isinstance(summary.get("total_chunks"), int):
        output_bits.append(f"{summary['total_chunks']} chunks")
    if isinstance(summary.get("embeddings"), int):
        output_bits.append(f"{summary['embeddings']} emb")
    duration_text = str(summary.get("duration_text") or "").strip()
    if duration_text:
        output_bits.append(duration_text)
    if output_bits:
        lines.append("Output: " + " · ".join(output_bits))

    before_bits: list[str] = []
    if isinstance(summary.get("initial_files"), int):
        before_bits.append(f"{summary['initial_files']} files")
    if isinstance(summary.get("initial_chunks"), int):
        before_bits.append(f"{summary['initial_chunks']} chunks")
    if isinstance(summary.get("initial_embeddings"), int):
        before_bits.append(f"{summary['initial_embeddings']} emb")
    if before_bits:
        lines.append("Before: " + " · ".join(before_bits))

    return lines
