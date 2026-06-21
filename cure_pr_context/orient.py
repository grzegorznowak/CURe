"""LLM orientation brief construction for PR discussion context."""

from __future__ import annotations

import json
from typing import Any, Callable

RunLlm = Callable[[str], str]

_SECTION_HEADERS = (
    "Áreas resueltas",
    "Problemáticas",
    "Pendientes",
    "Patrones",
    "Decisiones",
)
_USAGE_NOTE = (
    "Use this prior context as orientation only: avoid re-requesting resolved work, "
    "prioritize unresolved risks, and verify every finding against the current checkout."
)


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
        if header.lower() not in body.lower():
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

Summarize only information useful for reviewing the current diff. Return Markdown
with these exact section headings:
- Áreas resueltas
- Problemáticas
- Pendientes
- Patrones
- Decisiones

Input JSON:
```json
{_payload(discussion, past_reviews, pr_stats)}
```
""".strip()
    return _ensure_sections(run_llm(prompt))
