from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

import cure_pr_context
import cure_pr_context.orient as orient
from cure_pr_context import (
    OrientationProviderExecutionFailure,
    PrContextStageError,
    build_pr_context,
)
from cure_errors import ReviewflowError
from cure_pr_context.corpus import (
    ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS,
    assemble_orientation_prompt,
    estimated_tokens,
)


@dataclass(frozen=True)
class PR:
    owner: str = "acme"
    repo: str = "rocket"
    number: int = 7


def test_build_pr_context_is_remote_only_and_preserves_complete_audit(tmp_path: Path) -> None:
    audit = [
        {"id": 1, "body": "x" * 4001, "user": {"login": "dev"}, "created_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "body": "footer/session text stays ordinary", "user": {"login": "bot"}, "created_at": "bad"},
    ]
    prompts: list[str] = []

    def fetch(path: str) -> list[dict[str, object]]:
        return audit if path.endswith("issues/7/comments") else []

    result = build_pr_context(
        pr=PR(), work_dir=tmp_path / "work", pr_stats={"changed_files": 1},
        gh_fetch=fetch, run_llm=lambda prompt: prompts.append(prompt) or "## Problem areas\n- inspect",
    )
    assert set(result) == {"orientation_brief", "discussion", "selected_discussion", "meta"}
    assert [item["body"] for item in result["discussion"]] == [audit[0]["body"], audit[1]["body"]]
    assert len(result["selected_discussion"][0]["body"]) == 4000
    written = json.loads((tmp_path / "work/pr_context_discussion.json").read_text())
    assert written == result["discussion"]
    assert len(prompts) == 1
    assert result["meta"]["counts"] == {"fetched": 2, "normalized": 2, "selected": 2, "omitted": 0, "truncated_events": 1}


def test_normalization_failure_retains_fetched_but_not_normalized_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = [
        {"id": 1, "body": "first"},
        {"id": 2, "body": "second"},
    ]
    original = cure_pr_context.fetch_pr_discussion.__globals__["_normalize_item"]
    normalized_calls = 0

    def fail_second(kind: str, item: dict[str, object]) -> dict[str, object]:
        nonlocal normalized_calls
        normalized_calls += 1
        if normalized_calls == 2:
            raise ValueError("normalization exploded")
        return original(kind, item)

    monkeypatch.setitem(
        cure_pr_context.fetch_pr_discussion.__globals__, "_normalize_item", fail_second
    )
    ticks = iter([1.0, 2.0, 2.25, 2.5])
    monkeypatch.setattr(cure_pr_context.time, "monotonic", ticks.__next__)

    def fetch(path: str) -> list[dict[str, object]]:
        return raw if path.endswith("issues/7/comments") else []

    with pytest.raises(PrContextStageError, match="normalization exploded") as raised:
        build_pr_context(
            pr=PR(), work_dir=tmp_path / "work", pr_stats={}, gh_fetch=fetch,
            run_llm=lambda _prompt: "unused",
        )

    assert raised.value.stage == "fetch_failed"
    assert raised.value.meta == {
        "counts": {
            "fetched": 2,
            "normalized": 0,
            "selected": 0,
            "omitted": 0,
            "truncated_events": 0,
        },
        "latency_ms": {
            "fetch": 250,
            "selection": 0,
            "orientation": 0,
            "total_enrichment": 1500,
        },
    }
    assert not (tmp_path / "work/pr_context_discussion.json").exists()


def test_partial_stage_failures_expose_exact_completed_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {"id": 1, "body": "body", "created_at": "2026-01-01T00:00:00Z"}

    def fetch(path: str) -> list[dict[str, object]]:
        return [event] if path.endswith("issues/7/comments") else []

    monkeypatch.setattr(cure_pr_context.time, "monotonic", iter([1.0, 2.0, 3.0, 4.0]).__next__)
    monkeypatch.setattr(
        cure_pr_context,
        "_write_json",
        lambda _path, _payload: (_ for _ in ()).throw(OSError("audit write failed")),
    )
    with pytest.raises(PrContextStageError, match="audit write failed") as write_error:
        build_pr_context(
            pr=PR(), work_dir=tmp_path / "write", pr_stats={}, gh_fetch=fetch,
            run_llm=lambda _prompt: "unused",
        )
    assert write_error.value.stage == "artifact_write_failed"
    assert write_error.value.meta == {
        "counts": {
            "fetched": 1, "normalized": 1, "selected": 0,
            "omitted": 0, "truncated_events": 0,
        },
        "latency_ms": {
            "fetch": 1000, "selection": 0, "orientation": 0,
            "total_enrichment": 3000,
        },
    }


def test_selection_failure_exposes_exact_completed_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {"id": 1, "body": "body", "created_at": "2026-01-01T00:00:00Z"}

    def fetch(path: str) -> list[dict[str, object]]:
        return [event] if path.endswith("issues/7/comments") else []

    monkeypatch.setattr(cure_pr_context.time, "monotonic", iter([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]).__next__)
    monkeypatch.setattr(
        cure_pr_context,
        "select_orientation_events",
        lambda _discussion, *, pr_stats: (_ for _ in ()).throw(ValueError("selection failed")),
    )
    with pytest.raises(PrContextStageError, match="selection failed") as raised:
        build_pr_context(
            pr=PR(), work_dir=tmp_path / "selection", pr_stats={}, gh_fetch=fetch,
            run_llm=lambda _prompt: "unused",
        )
    assert raised.value.stage == "selection_failed"
    assert raised.value.meta == {
        "counts": {
            "fetched": 1, "normalized": 1, "selected": 0,
            "omitted": 0, "truncated_events": 0,
        },
        "latency_ms": {
            "fetch": 1000, "selection": 1000, "orientation": 0,
            "total_enrichment": 5000,
        },
    }


def test_orientation_failure_exposes_exact_completed_metadata_and_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {"id": 1, "body": "body", "created_at": "2026-01-01T00:00:00Z"}

    def fetch(path: str) -> list[dict[str, object]]:
        return [event] if path.endswith("issues/7/comments") else []

    expected_selection = {
        "selected": 1, "omitted": 0, "truncated_events": 0, "marker": "exact",
    }
    monkeypatch.setattr(
        cure_pr_context,
        "select_orientation_events",
        lambda discussion, *, pr_stats: {
            "selected_discussion": discussion,
            "meta": expected_selection,
        },
    )
    monkeypatch.setattr(
        cure_pr_context.time,
        "monotonic",
        iter([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]).__next__,
    )
    with pytest.raises(PrContextStageError, match="orientation failed") as raised:
        build_pr_context(
            pr=PR(), work_dir=tmp_path / "orientation", pr_stats={}, gh_fetch=fetch,
            run_llm=lambda _prompt: (_ for _ in ()).throw(
                OrientationProviderExecutionFailure(RuntimeError("orientation failed"))
            ),
            usage_observer=lambda: {"input_tokens": 17},
        )
    assert raised.value.stage == "orientation_failed"
    assert raised.value.meta == {
        "counts": {
            "fetched": 1, "normalized": 1, "selected": 1,
            "omitted": 0, "truncated_events": 0,
        },
        "selection": expected_selection,
        "provider_usage": {"input_tokens": 17},
        "latency_ms": {
            "fetch": 1000, "selection": 1000, "orientation": 1000,
            "total_enrichment": 7000,
        },
    }


def test_pr_context_metadata_orientation_finalization_fail_open_preserves_completed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = {"id": 1, "body": "body", "created_at": "2026-01-01T00:00:00Z"}

    def fetch(path: str) -> list[dict[str, object]]:
        return [event] if path.endswith("issues/7/comments") else []

    expected_selection = {
        "selected": 1, "omitted": 0, "truncated_events": 0, "marker": "exact",
    }
    monkeypatch.setattr(
        cure_pr_context,
        "select_orientation_events",
        lambda discussion, *, pr_stats: {
            "selected_discussion": discussion,
            "meta": expected_selection,
        },
    )
    monkeypatch.setattr(
        cure_pr_context.time,
        "monotonic",
        iter([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]).__next__,
    )
    failure = ValueError("orientation output finalizer failed")
    monkeypatch.setattr(
        orient,
        "_finalize_to_cap",
        lambda _raw, _cap: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(PrContextStageError) as raised:
        build_pr_context(
            pr=PR(), work_dir=tmp_path / "orientation", pr_stats={}, gh_fetch=fetch,
            run_llm=lambda _prompt: "scanner output",
            usage_observer=lambda: {"input_tokens": 17},
        )

    assert raised.value.stage == "orientation_failed"
    assert raised.value.meta == {
        "counts": {
            "fetched": 1, "normalized": 1, "selected": 1,
            "omitted": 0, "truncated_events": 0,
        },
        "selection": expected_selection,
        "provider_usage": {"input_tokens": 17},
        "latency_ms": {
            "fetch": 1000, "selection": 1000, "orientation": 1000,
            "total_enrichment": 7000,
        },
    }
    persisted_discussion = json.loads(
        (tmp_path / "orientation/pr_context_discussion.json").read_text()
    )
    assert len(persisted_discussion) == 1
    assert persisted_discussion[0]["body"] == event["body"]


@pytest.mark.parametrize(
    "failure",
    [ReviewflowError("orientation control failed"), OSError("orientation output failed")],
)
def test_orientation_nonprovider_failures_propagate_without_stage_attribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    event = {"id": 1, "body": "body", "created_at": "2026-01-01T00:00:00Z"}
    monkeypatch.setattr(
        cure_pr_context,
        "select_orientation_events",
        lambda discussion, *, pr_stats: {
            "selected_discussion": discussion,
            "meta": {"selected": 1, "omitted": 0, "truncated_events": 0},
        },
    )

    def fetch(path: str) -> list[dict[str, object]]:
        return [event] if path.endswith("issues/7/comments") else []

    with pytest.raises(type(failure), match=str(failure)) as raised:
        build_pr_context(
            pr=PR(), work_dir=tmp_path / "orientation", pr_stats={}, gh_fetch=fetch,
            run_llm=lambda _prompt: (_ for _ in ()).throw(failure),
        )

    assert raised.value is failure


def test_empty_remote_writes_empty_audit_and_skips_orientation(tmp_path: Path) -> None:
    called = False
    def run_llm(_prompt: str) -> str:
        nonlocal called
        called = True
        return "unused"
    result = build_pr_context(
        pr=PR(), work_dir=tmp_path / "work", pr_stats={}, gh_fetch=lambda _path: [], run_llm=run_llm
    )
    assert result["orientation_brief"] == ""
    assert result["discussion"] == []
    assert result["meta"]["reason"] == "no_remote_context"
    assert json.loads((tmp_path / "work/pr_context_discussion.json").read_text()) == []
    assert called is False


def _stats_for_exact_empty_prompt_tokens(target: int) -> dict[str, str]:
    empty_value_tokens = estimated_tokens(
        assemble_orientation_prompt(pr_stats={"padding": ""}, selected_events=[])
    )
    approximate = (target - empty_value_tokens) * 4
    for length in range(max(0, approximate - 8), approximate + 9):
        stats = {"padding": "x" * length}
        if estimated_tokens(
            assemble_orientation_prompt(pr_stats=stats, selected_events=[])
        ) == target:
            return stats
    raise AssertionError(f"could not assemble exact {target}-token empty prompt")


def test_fixed_overhead_over_cap_is_degraded_selection_failed_with_truthful_partial_state(
    tmp_path: Path,
) -> None:
    called = False
    raw_event = {
        "id": 1,
        "body": "body",
        "user": {"login": "dev"},
        "created_at": "2026-01-01T00:00:00Z",
    }

    def fetch(path: str) -> list[dict[str, object]]:
        return [raw_event] if path.endswith("issues/7/comments") else []

    def run_llm(_prompt: str) -> str:
        nonlocal called
        called = True
        return "unused"

    stats = _stats_for_exact_empty_prompt_tokens(
        ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS + 1
    )
    with pytest.raises(PrContextStageError) as raised:
        build_pr_context(
            pr=PR(), work_dir=tmp_path / "work", pr_stats=stats,
            gh_fetch=fetch, run_llm=run_llm,
        )

    assert raised.value.stage == "selection_failed"
    assert raised.value.meta["counts"] == {
        "fetched": 1,
        "normalized": 1,
        "selected": 0,
        "omitted": 0,
        "truncated_events": 0,
    }
    assert raised.value.meta["latency_ms"]["orientation"] == 0
    assert called is False
    assert json.loads(
        (tmp_path / "work/pr_context_discussion.json").read_text(encoding="utf-8")
    ) == [
        {
            "kind": "issue_comment",
            "event_id": "1",
            "author": "dev",
            "body": "body",
            "created_at": "2026-01-01T00:00:00Z",
            "url": "",
            "path": "",
            "line": None,
            "review_state": "",
        }
    ]


def test_nonempty_zero_selected_at_exact_cap_skips_orientation_and_preserves_audit(
    tmp_path: Path,
) -> None:
    called = False

    def fetch(path: str) -> list[dict[str, object]]:
        return [{"id": 1, "body": "body", "created_at": "2026-01-01T00:00:00Z"}] if path.endswith("issues/7/comments") else []

    def run_llm(_prompt: str) -> str:
        nonlocal called
        called = True
        return "unused"

    result = build_pr_context(
        pr=PR(), work_dir=tmp_path / "work",
        pr_stats=_stats_for_exact_empty_prompt_tokens(
            ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS
        ),
        gh_fetch=fetch, run_llm=run_llm,
    )
    assert result["meta"]["reason"] == "no_selected_context"
    assert result["meta"]["counts"] == {
        "fetched": 1,
        "normalized": 1,
        "selected": 0,
        "omitted": 1,
        "truncated_events": 0,
    }
    assert len(result["discussion"]) == 1 and result["selected_discussion"] == []
    assert json.loads(
        (tmp_path / "work/pr_context_discussion.json").read_text(encoding="utf-8")
    ) == result["discussion"]
    assert called is False
