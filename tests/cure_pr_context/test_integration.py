from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cure_pr_context import build_pr_context
from cure_pr_context.corpus import CURE_REVIEW_FOOTER_END, CURE_REVIEW_FOOTER_START


@dataclass(frozen=True)
class PR:
    host: str = "github.com"
    owner: str = "acme"
    repo: str = "rocket"
    number: int = 7


def _footer(session: str, sha: str) -> str:
    return f"{CURE_REVIEW_FOOTER_START}\n_CURe · sha {sha} · session {session} · 1s_\n{CURE_REVIEW_FOOTER_END}"


def test_pr_context_end_to_end_with_deterministic_fixtures(tmp_path: Path) -> None:
    matching_head_footer = "Previous review says resolved tests.\n" + _footer("acme-rocket-pr7-old", "cafe123")
    different_head_same_pr_footer = "Earlier head found validation issue.\n" + _footer(
        "acme-rocket-pr7-older", "bad9999"
    )
    different_pr_footer = "Foreign review should stay ordinary discussion.\n" + _footer("acme-rocket-pr8-old", "cafe123")
    fixtures: dict[str, list[dict[str, object]]] = {
        "repos/acme/rocket/issues/7/comments": [
            {"id": "c1", "body": matching_head_footer, "user": {"login": "bot"}, "html_url": "u1"},
            {"id": "c2", "body": "Please revisit validation.", "user": {"login": "dev"}, "html_url": "u2"},
            {"id": "c3", "body": different_pr_footer, "user": {"login": "bot"}, "html_url": "u3"},
        ],
        "repos/acme/rocket/pulls/7/reviews": [
            {
                "id": "r1",
                "body": different_head_same_pr_footer,
                "user": {"login": "bot"},
                "commit_id": "bad9999",
            },
        ],
        "repos/acme/rocket/pulls/7/comments": [
            {"id": "rc1", "body": "inline concern", "user": {"login": "rev"}, "path": "a.py", "line": 8},
        ],
    }

    result = build_pr_context(
        pr=PR(),
        sandbox_root=tmp_path / "sandboxes",
        work_dir=tmp_path / "work",
        pr_stats={"changed_files": 3, "changed_lines": 30},
        head_sha="cafe123456789",  # pragma: allowlist secret
        gh_fetch=lambda path: fixtures[path],
        run_llm=lambda prompt: "## Pendientes\n- Please revisit validation.",
    )

    assert result["meta"]["n_comments"] == 3
    assert result["meta"]["n_reviews"] == 1
    assert result["meta"]["n_review_comments"] == 1
    assert result["meta"]["n_past_reviews"] == 2
    assert result["meta"]["n_deduped"] == 2
    assert [item["entry_id"] for item in result["past_reviews"]] == ["pr_comment:c1", "pr_review:r1"]
    assert [item["reviewed_head"] for item in result["past_reviews"]] == ["cafe123", "bad9999"]
    assert [item["current_head"] for item in result["past_reviews"]] == ["cafe123456789", "cafe123456789"]
    assert [item["head_match_status"] for item in result["past_reviews"]] == ["matches", "differs"]
    assert [event["event_id"] for event in result["discussion"]] == ["c2", "c3", "rc1"]
    assert "Pendientes" in result["orientation_brief"]

    written_past_reviews = json.loads((tmp_path / "work" / "pr_context_past_reviews.json").read_text())
    written_discussion = json.loads((tmp_path / "work" / "pr_context_discussion.json").read_text())
    assert [item["head_match_status"] for item in written_past_reviews] == ["matches", "differs"]
    assert [event["event_id"] for event in written_discussion] == ["c2", "c3", "rc1"]
