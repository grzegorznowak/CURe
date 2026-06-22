"""Simple PR discussion context for CURe review prompts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .corpus import find_past_reviews
from .fetcher import fetch_pr_discussion
from .orient import build_orientation_brief

GhFetch = Callable[[str], list[Any]]
RunLlm = Callable[[str], str]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _discussion_kind_counts(discussion: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "n_comments": sum(1 for event in discussion if event.get("kind") == "issue_comment"),
        "n_reviews": sum(1 for event in discussion if event.get("kind") == "review"),
        "n_review_comments": sum(1 for event in discussion if event.get("kind") == "review_comment"),
    }


def build_pr_context(
    *,
    pr: Any,
    sandbox_root: Path,
    work_dir: Path,
    pr_stats: dict[str, Any],
    head_sha: str,
    gh_fetch: GhFetch,
    run_llm: RunLlm,
) -> dict[str, Any]:
    """Build prior PR context and debug artifacts.

    The function intentionally fails hard: GitHub, filesystem, and LLM errors are
    allowed to propagate so ``cure pr`` aborts before prompt rendering.
    """

    discussion = fetch_pr_discussion(pr=pr, gh_fetch=gh_fetch)
    corpus = find_past_reviews(
        pr=pr,
        sandbox_root=sandbox_root,
        discussion=discussion,
        head_sha=head_sha,
    )
    pruned_discussion = list(corpus["discussion"])
    past_reviews = list(corpus["past_reviews"])
    orientation_brief = build_orientation_brief(
        discussion=pruned_discussion,
        past_reviews=past_reviews,
        pr_stats=pr_stats,
        run_llm=run_llm,
    )
    _write_json(work_dir / "pr_context_discussion.json", pruned_discussion)
    _write_json(work_dir / "pr_context_past_reviews.json", past_reviews)
    meta = {
        "head_sha": str(head_sha or ""),
        **_discussion_kind_counts(discussion),
        "n_discussion_fetched": len(discussion),
        "n_discussion": len(pruned_discussion),
        "n_past_reviews": len(past_reviews),
        "n_deduped": int(corpus.get("meta", {}).get("n_deduped", 0)),
        "artifacts": {
            "discussion": str(work_dir / "pr_context_discussion.json"),
            "past_reviews": str(work_dir / "pr_context_past_reviews.json"),
        },
    }
    return {
        "orientation_brief": orientation_brief,
        "discussion": pruned_discussion,
        "past_reviews": past_reviews,
        "meta": meta,
    }


__all__ = ["build_pr_context", "fetch_pr_discussion", "find_past_reviews", "build_orientation_brief"]
