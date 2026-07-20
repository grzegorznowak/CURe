from __future__ import annotations

from pathlib import Path

from cure_pr_context import runtime
from cure_pr_context.orient import USAGE_INSTRUCTIONS, finalize_orientation_brief, is_valid_orientation_brief

HEADINGS = ("Resolved areas", "Problem areas", "Pending issues", "Repeated patterns", "Decisions made")


def _valid_crlf_brief() -> str:
    brief, _ = finalize_orientation_brief("## Problem areas\n- preserve line endings")
    return brief.replace("\n", "\r\n")


def _valid_crlf_brief_of_length(length: int) -> str:
    brief = _valid_crlf_brief()
    assert len(brief) <= length
    return brief + ("x" * (length - len(brief)))


def test_read_persisted_context_accepts_exact_crlf_cap_boundary(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    brief = _valid_crlf_brief_of_length(8_000)
    (work_dir / "pr_context_orientation.md").write_bytes(brief.encode("utf-8"))

    assert len(brief) == 8_000
    assert runtime.estimated_tokens(brief) == 2_000
    assert runtime.read_persisted_context(work_dir, {"outcome": "used"}) == (
        brief,
        "context_delivered",
    )


def test_read_persisted_context_rejects_exact_crlf_over_cap(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    brief = _valid_crlf_brief_of_length(8_001)
    normalized = brief.replace("\r\n", "\n")
    (work_dir / "pr_context_orientation.md").write_bytes(brief.encode("utf-8"))

    assert runtime.estimated_tokens(brief) == 2_001
    assert runtime.estimated_tokens(normalized) <= 2_000
    assert is_valid_orientation_brief(normalized)
    assert runtime.read_persisted_context(work_dir, {"outcome": "used"}) == (
        "",
        "resume_invalid_context",
    )


def test_read_persisted_context_preserves_exact_crlf_bytes(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    brief = _valid_crlf_brief()
    expected = brief.encode("utf-8")
    (work_dir / "pr_context_orientation.md").write_bytes(expected)

    actual, reason = runtime.read_persisted_context(work_dir, {"outcome": "used"})

    assert reason == "context_delivered"
    assert actual == brief
    assert actual.encode("utf-8") == expected


def test_atomic_write_persisted_context_round_trips_exact_crlf_bytes(tmp_path: Path) -> None:
    path = tmp_path / "work" / "pr_context_orientation.md"
    brief = _valid_crlf_brief()
    expected = brief.encode("utf-8")

    runtime.atomic_write_persisted_context(path, brief)

    assert path.read_bytes() == expected
    assert runtime.read_persisted_context(path.parent, {"outcome": "used"}) == (
        brief,
        "context_delivered",
    )


def test_read_persisted_context_rejects_invalid_utf8(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "pr_context_orientation.md").write_bytes(b"\xff")

    assert runtime.read_persisted_context(work_dir, {"outcome": "used"}) == (
        "",
        "resume_invalid_context",
    )


def test_read_persisted_context_rejects_malformed_fence_closer(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    malformed = "\r\n".join(
        [
            "```text",
            "```trailing-content",
            *(f"## {heading}" for heading in HEADINGS),
            USAGE_INSTRUCTIONS,
        ]
    )
    (work_dir / "pr_context_orientation.md").write_bytes(malformed.encode("utf-8"))

    assert runtime.read_persisted_context(work_dir, {"outcome": "used"}) == (
        "",
        "resume_invalid_context",
    )


def test_read_persisted_context_rejects_invalid_brief(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "pr_context_orientation.md").write_bytes(b"not a valid orientation brief")

    assert runtime.read_persisted_context(work_dir, {"outcome": "used"}) == (
        "",
        "resume_invalid_context",
    )


def test_read_persisted_context_requires_used_origin(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "pr_context_orientation.md").write_bytes(_valid_crlf_brief().encode("utf-8"))

    assert runtime.read_persisted_context(work_dir, {"outcome": "bypassed"}) == (
        "",
        "resume_without_used_context",
    )
