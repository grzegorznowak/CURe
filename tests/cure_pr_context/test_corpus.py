from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from cure_pr_context.corpus import CURE_REVIEW_FOOTER_END, CURE_REVIEW_FOOTER_START, find_past_reviews


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


def test_find_past_reviews_scans_sessions_and_retains_past_review_side(tmp_path: Path) -> None:
    body = "Prior CURe finding about the migration path."
    _write_session(tmp_path, session_id="acme-rocket-pr7-local", body=body, head_sha="abcdef1")
    discussion = [
        {"kind": "issue_comment", "event_id": "c1", "body": body, "author": "bot", "url": "u"},
        {"kind": "issue_comment", "event_id": "c2", "body": "human discussion", "author": "dev", "url": "u2"},
    ]

    result = find_past_reviews(pr=PR(), sandbox_root=tmp_path, discussion=discussion, head_sha="abcdef123")

    assert len(result["past_reviews"]) == 1
    assert result["past_reviews"][0]["source_type"] == "session_review"
    assert [event["event_id"] for event in result["discussion"]] == ["c2"]
    assert result["meta"]["n_deduped"] == 1


def test_find_past_reviews_detects_remote_footer_and_checks_head(tmp_path: Path) -> None:
    compatible = "CURe review body" + _footer("acme-rocket-pr7-20260101", "abc1234")
    incompatible = "old CURe review" + _footer("acme-rocket-pr7-20260102", "def9999")
    discussion = [
        {"kind": "issue_comment", "event_id": "c1", "body": compatible, "author": "bot", "url": "u"},
        {"kind": "review", "event_id": "r1", "body": incompatible, "author": "bot", "url": "u2", "reviewed_head": "def9999"},
    ]

    result = find_past_reviews(pr=PR(), sandbox_root=tmp_path, discussion=discussion, head_sha="abc123456")

    assert [item["entry_id"] for item in result["past_reviews"]] == ["pr_comment:c1"]
    assert result["discussion"] == [discussion[1]]
    assert result["meta"]["n_deduped"] == 1


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
