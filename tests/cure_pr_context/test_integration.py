from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cure_pr_context import build_pr_context


@dataclass(frozen=True)
class PR:
    owner: str = "acme"
    repo: str = "rocket"
    number: int = 7


def test_remote_endpoint_order_is_public_and_artifact_order(tmp_path: Path) -> None:
    fixtures = {
        "repos/acme/rocket/issues/7/comments": [{"id": "c", "body": "comment", "created_at": "2026-01-03T00:00:00Z"}],
        "repos/acme/rocket/pulls/7/reviews": [{"id": "r", "body": "review", "submitted_at": "2026-01-01T00:00:00Z"}],
        "repos/acme/rocket/pulls/7/comments": [{"id": "rc", "body": "inline", "created_at": "2026-01-02T00:00:00Z"}],
    }
    result = build_pr_context(
        pr=PR(), pr_stats={}, gh_fetch=lambda path: fixtures[path],
        run_llm=lambda _prompt: "## Problem areas\n- inspect",
    )
    assert [item["event_id"] for item in result["discussion"]] == ["c", "r", "rc"]
    assert [item["event_id"] for item in result["selected_discussion"]] == ["r", "rc", "c"]
    assert list(tmp_path.rglob("pr_context_*")) == []
