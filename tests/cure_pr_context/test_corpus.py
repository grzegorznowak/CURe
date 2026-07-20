from __future__ import annotations

import pytest

import cure_pr_context.corpus as corpus
from cure_pr_context.corpus import (
    ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS,
    assemble_orientation_prompt,
    canonical_json,
    estimated_tokens,
    select_orientation_events,
)


def _event(kind: str, event_id: str, created_at: str, body: str = "body") -> dict[str, object]:
    return {
        "kind": kind,
        "event_id": event_id,
        "author": "dev",
        "body": body,
        "created_at": created_at,
        "url": "",
        "path": "",
        "line": None,
        "review_state": "",
    }


def test_estimator_and_canonical_json_contract() -> None:
    assert [estimated_tokens(value) for value in ("", "a", "abcd", "abcde")] == [0, 1, 1, 2]
    assert canonical_json({"z": "é", "a": {"d": 2, "c": 1}}) == '{"a":{"c":1,"d":2},"z":"é"}'


def test_selection_orders_admission_newest_and_model_input_chronologically() -> None:
    events = [
        _event("issue_comment", "old", "2026-01-01T00:00:00Z"),
        _event("review", "same-review", "2026-01-03T01:00:00+01:00"),
        _event("issue_comment", "same-comment", "2026-01-03T00:00:00Z"),
        _event("review_comment", "invalid", "not-a-date"),
        _event("issue_comment", "naive", "2026-01-02T00:00:00"),
    ]
    result = select_orientation_events(events, pr_stats={})
    assert [event["event_id"] for event in result["selected_discussion"]] == [
        "old", "same-comment", "same-review", "naive", "invalid"
    ]
    assert result["meta"]["selected"] == 5
    assert result["meta"]["orientation_prompt"] <= ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS


def test_selection_restores_exact_chronology_for_near_adjacent_instants() -> None:
    events = [
        _event("issue_comment", "later-precision-edge", "9999-01-01T00:00:00.000002Z"),
        _event("review", "earlier-precision-edge", "9999-01-01T00:00:00.000001Z"),
        _event("review_comment", "ordinary-adjacent", "2026-01-01T00:00:00.999999Z"),
    ]

    result = select_orientation_events(events, pr_stats={})

    assert [event["event_id"] for event in result["selected_discussion"]] == [
        "ordinary-adjacent",
        "earlier-precision-edge",
        "later-precision-edge",
    ]


def test_parser_accepted_aware_year_boundaries_are_valid_and_instant_ordered() -> None:
    events = [
        _event("review_comment", "invalid", "not-a-date"),
        _event("review", "minimum-utc", "0001-01-01T00:00:00Z"),
        _event("issue_comment", "maximum-overflow", "9999-12-31T23:59:59-00:01"),
        _event("review_comment", "maximum-utc", "9999-12-31T23:59:59Z"),
        _event("issue_comment", "minimum-underflow", "0001-01-01T00:00:00+00:01"),
    ]

    result = select_orientation_events(events, pr_stats={})

    assert [event["event_id"] for event in result["selected_discussion"]] == [
        "minimum-underflow",
        "minimum-utc",
        "maximum-utc",
        "maximum-overflow",
        "invalid",
    ]


@pytest.mark.parametrize(
    ("body_length", "expected_length", "expected_truncated"),
    [(3999, 3999, False), (4000, 4000, False), (4001, 4000, True)],
)
def test_selection_body_cap_exact_boundaries_without_mutating_audit(
    body_length: int, expected_length: int, expected_truncated: bool
) -> None:
    body = "x" * body_length
    events = [_event("issue_comment", "boundary", "2026-01-01T00:00:00Z", body)]

    result = select_orientation_events(events, pr_stats={})

    assert events[0]["body"] == body
    assert len(result["selected_discussion"][0]["body"]) == expected_length
    assert result["meta"]["truncated_events"] == int(expected_truncated)
    assert result["meta"]["event_body_truncated"] is expected_truncated


@pytest.mark.parametrize(
    ("event_count", "expected_selected", "expected_omitted", "expected_limited"),
    [(99, 99, 0, False), (100, 100, 0, False), (101, 100, 1, True)],
)
def test_selection_event_count_exact_boundaries(
    event_count: int,
    expected_selected: int,
    expected_omitted: int,
    expected_limited: bool,
) -> None:
    events = [
        _event(
            "issue_comment",
            str(index),
            f"2026-01-01T00:{index // 60:02}:{index % 60:02}Z",
        )
        for index in range(event_count)
    ]

    result = select_orientation_events(events, pr_stats={})

    assert result["meta"]["selected"] == expected_selected
    assert result["meta"]["omitted"] == expected_omitted
    assert result["meta"]["event_count_truncated"] is expected_limited
    assert [event["event_id"] for event in result["selected_discussion"]] == [
        str(index) for index in range(event_count - expected_selected, event_count)
    ]


def test_timestamp_valid_empty_missing_invalid_have_deterministic_model_order() -> None:
    missing = _event("issue_comment", "missing", "placeholder")
    missing.pop("created_at")
    events = [
        _event("review_comment", "invalid", "not-a-date"),
        _event("review", "valid-new", "2026-01-03T00:00:00Z"),
        _event("review", "empty", ""),
        missing,
        _event("issue_comment", "valid-old", "2026-01-01T00:00:00Z"),
    ]

    result = select_orientation_events(events, pr_stats={})

    assert [event["event_id"] for event in result["selected_discussion"]] == [
        "valid-old",
        "valid-new",
        "missing",
        "empty",
        "invalid",
    ]


def test_timestamp_valid_empty_missing_invalid_have_deterministic_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(corpus, "SELECTED_EVENT_MAX", 3)
    missing = _event("issue_comment", "missing", "placeholder")
    missing.pop("created_at")
    events = [
        _event("review_comment", "invalid", "not-a-date"),
        _event("review", "empty", ""),
        missing,
        _event("issue_comment", "valid", "2020-01-01T00:00:00Z"),
    ]

    result = select_orientation_events(events, pr_stats={})

    assert [event["event_id"] for event in result["selected_discussion"]] == [
        "valid",
        "missing",
        "empty",
    ]
    assert result["meta"]["omitted"] == 1
    assert result["meta"]["event_count_truncated"] is True


def _stats_for_exact_prompt_tokens(
    target: int, *, selected_events: list[dict[str, object]]
) -> dict[str, str]:
    empty_value_tokens = estimated_tokens(
        assemble_orientation_prompt(
            pr_stats={"padding": ""}, selected_events=selected_events
        )
    )
    approximate = (target - empty_value_tokens) * 4
    for length in range(max(0, approximate - 8), approximate + 9):
        stats = {"padding": "x" * length}
        if estimated_tokens(
            assemble_orientation_prompt(
                pr_stats=stats, selected_events=selected_events
            )
        ) == target:
            return stats
    raise AssertionError(f"could not assemble exact {target}-token prompt")


def _stats_for_exact_empty_prompt_tokens(target: int) -> dict[str, str]:
    return _stats_for_exact_prompt_tokens(target, selected_events=[])


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_complete_selected_event_prompt_cap_boundaries(offset: int) -> None:
    event = _event("issue_comment", "one", "2026-01-01T00:00:00Z")
    target = ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS + offset
    stats = _stats_for_exact_prompt_tokens(target, selected_events=[event])
    assert estimated_tokens(
        assemble_orientation_prompt(pr_stats=stats, selected_events=[event])
    ) == target

    result = select_orientation_events([event], pr_stats=stats)

    if offset <= 0:
        assert result["selected_discussion"] == [event]
        assert result["meta"]["orientation_prompt"] == target
        assert result["meta"]["prompt_budget_truncated"] is False
    else:
        assert result["selected_discussion"] == []
        assert result["meta"]["orientation_prompt"] <= ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS
        assert result["meta"]["prompt_budget_truncated"] is True


@pytest.mark.parametrize("offset", [-1, 0])
def test_fixed_overhead_at_or_below_cap_is_admitted_exactly(offset: int) -> None:
    target = ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS + offset
    result = select_orientation_events(
        [], pr_stats=_stats_for_exact_empty_prompt_tokens(target)
    )
    assert estimated_tokens(result["prompt"]) == target
    assert result["meta"]["orientation_prompt"] == target
    assert result["selected_discussion"] == []


def test_fixed_overhead_above_cap_fails_before_event_admission() -> None:
    events = [_event("issue_comment", "one", "2026-01-01T00:00:00Z")]
    stats = _stats_for_exact_empty_prompt_tokens(
        ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS + 1
    )

    with pytest.raises(ValueError, match="fixed orientation prompt overhead"):
        select_orientation_events(events, pr_stats=stats)

    assert events == [
        _event("issue_comment", "one", "2026-01-01T00:00:00Z")
    ]


def test_nonempty_corpus_can_select_zero_at_exact_fixed_overhead_cap() -> None:
    events = [_event("issue_comment", "one", "2026-01-01T00:00:00Z")]
    result = select_orientation_events(
        events,
        pr_stats=_stats_for_exact_empty_prompt_tokens(
            ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS
        ),
    )
    assert result["selected_discussion"] == []
    assert result["meta"]["selected"] == 0
    assert result["meta"]["omitted"] == 1
    assert result["meta"]["prompt_budget_truncated"] is True
    assert result["meta"]["orientation_prompt"] == ORIENTATION_PROMPT_MAX_ESTIMATED_TOKENS
