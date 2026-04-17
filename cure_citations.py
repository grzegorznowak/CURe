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


def citation_contract_vars() -> dict[str, str]:
    """Return the ``$*_CITATION_CONTRACT`` template variables for prompt rendering."""
    return dict(CITATION_CONTRACT_KEYS)


_CITATION_LINE_RE = re.compile(r"`?([A-Za-z0-9._/-]+):([1-9][0-9]*)`?")


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
    return bool(_CITATION_LINE_RE.search(suffix_text or ""))


def has_incomplete_sources(body: str) -> bool:
    """True when the bullet has a ``Sources:`` suffix without any ``path:line``.

    This is the file-only case Story 42 reclassifies from "missing" to
    "invalid or incomplete".
    """
    suffix = trailing_sources_suffix(body)
    if not suffix:
        return False
    return not has_path_line_citation(suffix)
