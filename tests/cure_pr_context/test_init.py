from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from cure_pr_context import build_pr_context
from cure_pr_context.corpus import CURE_REVIEW_FOOTER_END, CURE_REVIEW_FOOTER_START


@dataclass(frozen=True)
class PR:
    host: str = "github.com"
    owner: str = "acme"
    repo: str = "rocket"
    number: int = 7


def test_build_pr_context_orchestrates_and_writes_pruned_debug_artifacts(tmp_path: Path) -> None:
    footer = f"\n{CURE_REVIEW_FOOTER_START}\n_CURe · sha abc1234 · session acme-rocket-pr7-1 · 1s_\n{CURE_REVIEW_FOOTER_END}"
    remote_review = "Prior CURe review" + footer

    def gh_fetch(path: str) -> list[dict[str, object]]:
        if path.endswith("/issues/7/comments"):
            return [
                {"id": "dup", "body": remote_review, "user": {"login": "bot"}, "created_at": "t", "html_url": "u"},
                {"id": "keep", "body": "new user question", "user": {"login": "dev"}, "created_at": "t2", "html_url": "u2"},
            ]
        return []

    result = build_pr_context(
        pr=PR(),
        sandbox_root=tmp_path / "sandboxes",
        work_dir=tmp_path / "work",
        pr_stats={"changed_files": 1},
        head_sha="abc123456789",  # pragma: allowlist secret
        gh_fetch=gh_fetch,
        run_llm=lambda prompt: "## Problemáticas\n- new user question",
    )

    assert set(result) == {"orientation_brief", "discussion", "past_reviews", "meta"}
    assert [event["event_id"] for event in result["discussion"]] == ["keep"]
    assert result["meta"]["n_comments"] == 2
    assert result["meta"]["n_reviews"] == 0
    assert result["meta"]["n_review_comments"] == 0
    assert result["meta"]["n_deduped"] == 1
    discussion_artifact = json.loads((tmp_path / "work" / "pr_context_discussion.json").read_text(encoding="utf-8"))
    past_artifact = json.loads((tmp_path / "work" / "pr_context_past_reviews.json").read_text(encoding="utf-8"))
    assert [event["event_id"] for event in discussion_artifact] == ["keep"]
    assert past_artifact[0]["source_type"] == "pr_comment"


def test_build_pr_context_fails_hard_without_partial_artifacts(tmp_path: Path) -> None:
    def run_llm(prompt: str) -> str:
        raise RuntimeError("llm unavailable")

    with pytest.raises(RuntimeError, match="llm unavailable"):
        build_pr_context(
            pr=PR(),
            sandbox_root=tmp_path / "sandboxes",
            work_dir=tmp_path / "work",
            pr_stats={},
            head_sha="abc",
            gh_fetch=lambda path: [{"id": 1, "body": "discussion"}] if path.endswith("/comments") else [],
            run_llm=run_llm,
        )

    assert not (tmp_path / "work" / "pr_context_discussion.json").exists()
    assert not (tmp_path / "work" / "pr_context_past_reviews.json").exists()
