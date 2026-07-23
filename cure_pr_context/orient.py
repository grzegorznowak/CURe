"""Bounded five-section orientation brief construction."""

from __future__ import annotations

import re
from typing import Any, Callable

from .corpus import (
    INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS,
    ORIENTATION_INSTRUCTIONS,
    ORIENTATION_OUTPUT_MAX_ESTIMATED_TOKENS,
    assemble_orientation_prompt,
    estimated_tokens,
)

RunLlm = Callable[[str], str]


class OrientationFinalizationFailure(RuntimeError):
    """Base marker for an internal PR-context finalization failure."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


class OrientationOutputFinalizationFailure(OrientationFinalizationFailure):
    """Marks finalization of provider output as an orientation-stage failure."""


class InjectedContextFinalizationFailure(OrientationFinalizationFailure):
    """Marks independent finalization of fresh context before delivery."""


SECTION_HEADERS = ("Resolved areas", "Problem areas", "Pending issues", "Repeated patterns", "Decisions made")
USAGE_INSTRUCTIONS = '''INSTRUCTIONS FOR USING PRIOR_CONTEXT:
- "Resolved areas": do not spend time re-evaluating them unless the diff touches them
- "Problem areas": prioritize them in your review plan
- "Pending issues": verify whether the diff resolved them or not
- "Repeated patterns": mention them as a cross-cutting theme if still present
- "Decisions made": do not question them, accept them as context
- If a section is empty, ignore it'''


def _markdown_structure(text: str) -> tuple[set[str], tuple[str, int] | None]:
    """Scan CommonMark-style structural headings and fences used by fresh/resume validation."""
    headings: set[str] = set()
    open_fence: tuple[str, int] | None = None
    for line in text.splitlines():
        structural = re.match(r"^[ ]{0,3}(.*)$", line)
        if structural is None:  # Four or more spaces are indented code.
            continue
        content = structural.group(1)
        if open_fence is None:
            opener = re.match(r"^(`{3,}|~{3,})(.*)$", content)
            if opener is not None:
                run = opener.group(1)
                open_fence = (run[0], len(run))
                continue
            heading = re.match(r"^##[ \t]+(.+?)[ \t]*$", content)
            if heading is not None:
                headings.add(heading.group(1))
            continue

        closer = re.match(r"^(`{3,}|~{3,})[ \t]*$", content)
        if closer is not None:
            run = closer.group(1)
            if run[0] == open_fence[0] and len(run) >= open_fence[1]:
                open_fence = None
    return headings, open_fence


def _compose(raw: str) -> str:
    raw = raw.strip().replace(USAGE_INSTRUCTIONS, "").strip()
    headings, fence = _markdown_structure(raw)
    parts = [raw] if raw else []
    if fence is not None:
        parts.append(fence[0] * fence[1])
    parts.append(USAGE_INSTRUCTIONS)
    for heading in SECTION_HEADERS:
        if heading not in headings:
            parts.append(f"## {heading}\n- None identified.")
    return "\n\n".join(parts).strip()


def _finalize_to_cap(raw: str, max_estimated_tokens: int) -> tuple[str, bool]:
    original = raw
    retained = raw[: max_estimated_tokens * 4]
    while True:
        brief = _compose(retained)
        if estimated_tokens(brief) <= max_estimated_tokens:
            return brief, retained != original
        excess = len(brief) - max_estimated_tokens * 4
        retained = retained[: max(0, len(retained) - max(1, excess))]


def finalize_orientation_brief(raw: str) -> tuple[str, bool]:
    try:
        return _finalize_to_cap(raw, ORIENTATION_OUTPUT_MAX_ESTIMATED_TOKENS)
    except Exception as exc:
        raise OrientationOutputFinalizationFailure(exc) from exc


def finalize_injected_context(brief: str) -> dict[str, Any]:
    """Finalize fresh injected context under its independent delivery cap."""
    try:
        finalized, truncated = _finalize_to_cap(
            brief, INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS
        )
        return {
            "brief": finalized,
            "estimated_tokens": estimated_tokens(finalized),
            "truncated": truncated,
        }
    except Exception as exc:
        raise InjectedContextFinalizationFailure(exc) from exc


def _is_valid_at_cap(text: str, max_estimated_tokens: int) -> bool:
    if not text.strip() or estimated_tokens(text) > max_estimated_tokens:
        return False
    headings, fence = _markdown_structure(text)
    return fence is None and text.count(USAGE_INSTRUCTIONS) == 1 and all(
        heading in headings for heading in SECTION_HEADERS
    )


def is_valid_orientation_brief(text: str) -> bool:
    return _is_valid_at_cap(text, ORIENTATION_OUTPUT_MAX_ESTIMATED_TOKENS)


def is_valid_injected_context(text: str) -> bool:
    return _is_valid_at_cap(text, INJECTED_CONTEXT_MAX_ESTIMATED_TOKENS)


def build_orientation_brief(
    *, discussion: list[dict[str, Any]], pr_stats: dict[str, Any], run_llm: RunLlm
) -> dict[str, Any]:
    prompt = assemble_orientation_prompt(pr_stats=pr_stats, selected_events=discussion)
    raw = run_llm(prompt)
    brief, truncated = finalize_orientation_brief(str(raw or ""))
    return {"brief": brief, "meta": {"estimated_tokens": estimated_tokens(brief), "truncated": truncated}}


__all__ = [
    "InjectedContextFinalizationFailure",
    "ORIENTATION_INSTRUCTIONS",
    "OrientationFinalizationFailure",
    "OrientationOutputFinalizationFailure",
    "USAGE_INSTRUCTIONS",
    "build_orientation_brief",
    "finalize_injected_context",
    "finalize_orientation_brief",
    "is_valid_injected_context",
    "is_valid_orientation_brief",
]
