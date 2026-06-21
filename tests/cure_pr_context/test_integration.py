from __future__ import annotations

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


def test_pr_context_end_to_end_with_deterministic_fixtures(tmp_path: Path) -> None:
    compatible_footer = (
        "Previous review says resolved tests.\n"
        f"{CURE_REVIEW_FOOTER_START}\n_CURe · sha cafe123 · session acme-rocket-pr7-old · 1s_\n{CURE_REVIEW_FOOTER_END}"
    )
    incompatible_footer = (
        "Foreign review.\n"
        f"{CURE_REVIEW_FOOTER_START}\n_CURe · sha bad9999 · session acme-rocket-pr7-old · 1s_\n{CURE_REVIEW_FOOTER_END}"
    )
    fixtures: dict[str, list[dict[str, object]]] = {
        "repos/acme/rocket/issues/7/comments": [
            {"id": "c1", "body": compatible_footer, "user": {"login": "bot"}, "html_url": "u1"},
            {"id": "c2", "body": "Please revisit validation.", "user": {"login": "dev"}, "html_url": "u2"},
        ],
        "repos/acme/rocket/pulls/7/reviews": [
            {"id": "r1", "body": incompatible_footer, "user": {"login": "bot"}, "commit_id": "bad9999"},
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

    assert result["meta"]["n_comments"] == 2
    assert result["meta"]["n_reviews"] == 1
    assert result["meta"]["n_review_comments"] == 1
    assert result["meta"]["n_past_reviews"] == 1
    assert result["meta"]["n_deduped"] == 1
    assert [event["event_id"] for event in result["discussion"]] == ["c2", "r1", "rc1"]
    assert "Pendientes" in result["orientation_brief"]
