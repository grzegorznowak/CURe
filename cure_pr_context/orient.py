"""LLM orientation brief construction for PR discussion context."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

RunLlm = Callable[[str], str]

_SECTION_HEADERS = (
    "Resolved areas",
    "Problem areas",
    "Pending issues",
    "Repeated patterns",
    "Decisions made",
)
_USAGE_NOTE = (
    "Use this prior context as orientation only: avoid re-requesting resolved work, "
    "prioritize unresolved risks, and verify every finding against the current checkout."
)

_USAGE_INSTRUCTIONS = """This brief summarizes prior discussion — it is orientation only. You must still perform a complete, independent review of every changed file. The sections below highlight patterns; they are not a substitute for thoroughness.

- "Resolved areas": do not spend time re-evaluating them unless the diff touches them
- "Problem areas": prioritize them in your review plan
- "Pending issues": verify whether the diff resolved them or not
- "Repeated patterns": mention them as a cross-cutting theme if still present
- "Decisions made": do not question them, accept them as context
- If a section is empty, ignore it"""


def _payload(discussion: list[dict[str, Any]], past_reviews: list[dict[str, Any]], pr_stats: dict[str, Any]) -> str:
    return json.dumps(
        {
            "discussion": discussion,
            "past_reviews": past_reviews,
            "pr_stats": pr_stats,
        },
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )


def _ensure_sections(text: str) -> str:
    body = text.strip()
    if not body:
        body = ""
    parts: list[str] = [f"## How to use this context\n{_USAGE_NOTE}"]
    if body:
        parts.append(body)
    for header in _SECTION_HEADERS:
        heading_pattern = rf"^##[ \t]+{re.escape(header)}[ \t]*$"
        if re.search(heading_pattern, body, flags=re.MULTILINE) is None:
            parts.append(f"## {header}\n- None identified.")
    return "\n\n".join(parts).strip()


def build_orientation_brief(
    *,
    discussion: list[dict[str, Any]],
    past_reviews: list[dict[str, Any]],
    pr_stats: dict[str, Any],
    run_llm: RunLlm,
) -> str:
    """Run a single LLM scan and return a structured prior-context brief."""

    if not discussion and not past_reviews:
        return ""
    prompt = f"""
You are preparing concise prior PR context for a code review agent.

{_USAGE_NOTE}

Summarize only information useful for reviewing the current diff. Populate
Resolved areas only when supplied discussion or past-review text describes an
area as addressed or resolved. This is not authoritative GitHub review-thread resolution state;
do not infer resolution merely from an event's presence or review state. Return Markdown
with these exact section headings:
- Resolved areas
- Problem areas
- Pending issues
- Repeated patterns
- Decisions made

Also include the following usage instructions block verbatim at the top of your output:
{_USAGE_INSTRUCTIONS}

Input JSON:
```json
{_payload(discussion, past_reviews, pr_stats)}
```
""".strip()
    return _ensure_sections(run_llm(prompt))
