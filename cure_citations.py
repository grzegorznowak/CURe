"""Shared citation/grounding contract for CURe review prompts and validators.

Story 42 unifies the trailing-suffix citation contract around ``Sources:``
`path:line` so review prompts, validators, and operator-facing diagnostics no
longer drift apart across the single-pass, multipass step, and multipass synth
paths.

Prompts render the contract via a ``$CITATION_CONTRACT`` template variable
populated from ``STEP_CITATION_CONTRACT`` or ``SYNTH_CITATION_CONTRACT``.
Validators use :func:`trailing_sources_suffix` and :func:`has_incomplete_sources`
to classify bullets so error messages distinguish missing suffixes from
incomplete (file-only) suffixes.
"""
from __future__ import annotations

import re

CITATION_LABEL = "Sources"
CITATION_LABEL_PREFIX = f"{CITATION_LABEL}:"

SOURCES_CITATION_SHAPE = "`relative/path:line`"

STEP_CITATION_CONTRACT = (
    f"- Every non-empty `### Findings` bullet ends with a trailing `{CITATION_LABEL_PREFIX}` "
    f"suffix listing one or more real repo citations in {SOURCES_CITATION_SHAPE} form.\n"
    f"- Cite `path:line`, not just `path`. File-only `{CITATION_LABEL_PREFIX}` text is treated "
    "as incomplete and fails grounding.\n"
    "- If there are no findings, write exactly `- None.` with no trailing suffix.\n"
    "- Do not emit an inline `Evidence:` label; the trailing-suffix contract is `"
    f"{CITATION_LABEL_PREFIX}` in all review prompts."
)

SYNTH_CITATION_CONTRACT = (
    f"- Every non-empty bullet under `Strengths`, `In Scope Issues`, `Out of Scope Issues`, "
    f"and `Reusability` ends with a trailing `{CITATION_LABEL_PREFIX}` suffix containing at "
    "least one real primary-evidence citation.\n"
    f"- Cite `path:line`, not just `path`. File-only `{CITATION_LABEL_PREFIX}` text is treated "
    "as incomplete and fails grounding.\n"
    "- Accepted primary evidence: repo or test files under the sandbox checkout "
    "(e.g. `src/module.py:12`, `tests/test_module.py:44`) and stable CURe session "
    "artifacts under `work/` (e.g. `work/pr-context.md:7`).\n"
    "- `review.step-XX.md:line` may be included as extra traceability, but it does "
    "not count as the required primary evidence by itself.\n"
    f"- Do not emit an inline `Evidence:` label; the trailing-suffix contract is `"
    f"{CITATION_LABEL_PREFIX}` in all review prompts."
)

# Single-pass review prompts do not run the multipass grounding validators, so
# this contract intentionally omits the "and fails grounding" consequence and
# the `- None.` escape hatch present in the step/synth variants.
REVIEW_CITATION_CONTRACT = (
    f"- When reporting findings, cite supporting evidence with a trailing "
    f"`{CITATION_LABEL_PREFIX}` suffix in {SOURCES_CITATION_SHAPE} form.\n"
    f"- Cite `path:line`, not just `path`. File-only `{CITATION_LABEL_PREFIX}` text is "
    "treated as incomplete.\n"
    f"- Use `{CITATION_LABEL_PREFIX}` as the trailing-suffix label; do not emit inline "
    "`Evidence:`."
)

CITATION_CONTRACT_KEYS = {
    "STEP_CITATION_CONTRACT": STEP_CITATION_CONTRACT,
    "SYNTH_CITATION_CONTRACT": SYNTH_CITATION_CONTRACT,
    "REVIEW_CITATION_CONTRACT": REVIEW_CITATION_CONTRACT,
}


CITATION_LINE_RE = re.compile(r"`?([A-Za-z0-9._/-]+):([1-9][0-9]*)`?")
_BACKTICKED_SOURCE_ITEM_RE = re.compile(r"`([^`]+)`")


def trailing_sources_suffix(body: str) -> str:
    """Return the trailing text after the last ``Sources:`` marker, or ``""``.

    The suffix is considered absent when either the marker is missing entirely
    or the tail following it is whitespace-only.
    """
    head, sep, tail = body.rpartition(CITATION_LABEL_PREFIX)
    if not sep:
        return ""
    if not head.strip() or not tail.strip():
        return ""
    return tail.strip()


def has_sources_marker(body: str) -> bool:
    """True when the bullet carries a ``Sources:`` suffix (complete or not)."""
    head, sep, tail = body.rpartition(CITATION_LABEL_PREFIX)
    if not sep:
        return False
    return bool(head.strip()) and bool(tail.strip())


def has_path_line_citation(suffix_text: str) -> bool:
    """True when ``suffix_text`` contains at least one ``path:line`` citation."""
    return bool(CITATION_LINE_RE.search(suffix_text or ""))


def _sources_suffix_items(suffix_text: str) -> list[str]:
    """Return the individual citation items carried in a ``Sources:`` suffix."""
    text = str(suffix_text or "").strip()
    if not text:
        return []
    backticked = [match.group(1).strip() for match in _BACKTICKED_SOURCE_ITEM_RE.finditer(text)]
    if backticked:
        return [item for item in backticked if item]
    return [item.strip().strip("`") for item in text.split(",") if item.strip()]


def has_incomplete_sources(body: str) -> bool:
    """True when any citation in the trailing ``Sources:`` suffix is incomplete."""
    suffix = trailing_sources_suffix(body)
    if not suffix:
        return False
    items = _sources_suffix_items(suffix)
    if not items:
        return not has_path_line_citation(suffix)
    return any(CITATION_LINE_RE.fullmatch(item) is None for item in items)
