from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from cure_pr_context.corpus import CURE_REVIEW_FOOTER_END, CURE_REVIEW_FOOTER_START, deduplicate, find_past_reviews


@dataclass(frozen=True)
class PR:
    host: str = "github.com"
    owner: str = "acme"
    repo: str = "rocket"
    number: int = 7


def _footer(session: str, sha: str) -> str:
    return f"\n---\n{CURE_REVIEW_FOOTER_START}\n_CURe · sha {sha} · session {session} · 1s_\n{CURE_REVIEW_FOOTER_END}\n"


def _write_session(root: Path, *, session_id: str, body: str, head_sha: str) -> None:
    session = root / session_id
    session.mkdir(parents=True)
    review = session / "review.md"
    review.write_text(body, encoding="utf-8")
    (session / "meta.json").write_text(
        json.dumps(
            {
                "status": "done",
                "session_id": session_id,
                "host": "github.com",
                "owner": "acme",
                "repo": "rocket",
                "number": 7,
                "review_head_sha": head_sha,
                "paths": {"review_md": str(review)},
            }
        ),
        encoding="utf-8",
    )


def test_find_past_reviews_scans_sessions_across_heads_and_retains_past_review_side(tmp_path: Path) -> None:
    body = "Prior CURe finding about the migration path."
    _write_session(tmp_path, session_id="acme-rocket-pr7-local", body=body, head_sha="def9999")
    discussion = [
        {"kind": "issue_comment", "event_id": "c1", "body": body, "author": "bot", "url": "u"},
        {"kind": "issue_comment", "event_id": "c2", "body": "human discussion", "author": "dev", "url": "u2"},
    ]

    result = find_past_reviews(pr=PR(), sandbox_root=tmp_path, discussion=discussion, head_sha="abc123456")

    assert len(result["past_reviews"]) == 1
    past_review = result["past_reviews"][0]
    assert past_review["source_type"] == "session_review"
    assert past_review["reviewed_head"] == "def9999"
    assert past_review["current_head"] == "abc123456"
    assert past_review["head_match_status"] == "differs"
    assert [event["event_id"] for event in result["discussion"]] == ["c2"]
    assert result["meta"]["n_deduped"] == 1


def test_find_past_reviews_deduplicates_local_review_and_its_posted_remote_copy(tmp_path: Path) -> None:
    session_id = "acme-rocket-pr7-posted"
    body = " ".join(f"Finding {index}: verify migration path {index}." for index in range(80))
    _write_session(tmp_path, session_id=session_id, body=body, head_sha="abc1234")
    posted_body = body + _footer(session_id, "abc1234")
    discussion = [
        {"kind": "issue_comment", "event_id": "c1", "body": posted_body, "author": "bot", "url": "u"}
    ]

    result = find_past_reviews(pr=PR(), sandbox_root=tmp_path, discussion=discussion, head_sha="abc123456")

    assert len(result["past_reviews"]) == 1
    assert result["past_reviews"][0]["source_type"] == "session_review"
    assert result["discussion"] == []
    assert result["meta"]["n_past_reviews"] == 1
    assert result["meta"]["n_deduped"] == 1


def test_deduplicate_uses_character_trigrams_at_inclusive_threshold() -> None:
    past_body = "abcdefghijklmnopqrst"
    boundary_body = "abcdefghijklmnopqrsuv"

    discussion = [{"kind": "issue_comment", "event_id": "c1", "body": boundary_body}]
    past_reviews = [{"source_type": "session_review", "entry_id": "session:one", "body": past_body}]

    retained, n_deduped = deduplicate(discussion=discussion, past_reviews=past_reviews, threshold=0.85)
    above_boundary, above_boundary_count = deduplicate(
        discussion=discussion, past_reviews=past_reviews, threshold=0.850001
    )

    assert retained == []
    assert n_deduped == 1
    assert above_boundary == discussion
    assert above_boundary_count == 0


def test_find_past_reviews_detects_remote_footers_across_heads_and_rejects_different_pr(tmp_path: Path) -> None:
    matching_head = "CURe review body" + _footer("acme-rocket-pr7-20260101", "abc1234")
    different_head_same_pr = "old CURe review" + _footer("acme-rocket-pr7-20260102", "def9999")
    different_pr = "other PR review" + _footer("acme-rocket-pr8-20260103", "abc1234")
    discussion = [
        {"kind": "issue_comment", "event_id": "c1", "body": matching_head, "author": "bot", "url": "u"},
        {
            "kind": "review",
            "event_id": "r1",
            "body": different_head_same_pr,
            "author": "bot",
            "url": "u2",
            "reviewed_head": "def9999",
        },
        {"kind": "issue_comment", "event_id": "c2", "body": different_pr, "author": "bot", "url": "u3"},
    ]

    result = find_past_reviews(pr=PR(), sandbox_root=tmp_path, discussion=discussion, head_sha="abc123456")

    assert [item["entry_id"] for item in result["past_reviews"]] == ["pr_comment:c1", "pr_review:r1"]
    assert [item["reviewed_head"] for item in result["past_reviews"]] == ["abc1234", "def9999"]
    assert [item["current_head"] for item in result["past_reviews"]] == ["abc123456", "abc123456"]
    assert [item["head_match_status"] for item in result["past_reviews"]] == ["matches", "differs"]
    assert result["past_reviews"][1]["provenance"]["footer_reviewed_head"] == "def9999"
    assert [event["event_id"] for event in result["discussion"]] == ["c2"]
    assert result["meta"]["n_deduped"] == 2


def test_find_past_reviews_ignores_marker_only_remote_footer_without_sha(tmp_path: Path) -> None:
    malformed = (
        "looks like a review\n"
        f"{CURE_REVIEW_FOOTER_START}\n"
        "_CURe · session acme-rocket-pr7-20260103 · 1s_\n"
        f"{CURE_REVIEW_FOOTER_END}"
    )
    discussion = [{"kind": "issue_comment", "event_id": "c1", "body": malformed, "author": "bot", "url": "u"}]

    result = find_past_reviews(pr=PR(), sandbox_root=tmp_path, discussion=discussion, head_sha="abc123456")

    assert result["past_reviews"] == []
    assert result["discussion"] == discussion
    assert result["meta"]["n_deduped"] == 0


def test_find_past_reviews_fails_hard_on_corrupt_local_session_meta(tmp_path: Path) -> None:
    session = tmp_path / "broken-session"
    session.mkdir()
    (session / "meta.json").write_text("{not json", encoding="utf-8")
    (session / "review.md").write_text("prior review", encoding="utf-8")

    with pytest.raises(ValueError, match="failed to parse meta.json"):
        find_past_reviews(pr=PR(), sandbox_root=tmp_path, discussion=[], head_sha="abc123456")
