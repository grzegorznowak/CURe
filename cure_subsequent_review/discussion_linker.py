"""LLM-backed discussion linker for subsequent-review discussion signals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from cure_subsequent_review.contracts import DiscussionEvent, DiscussionSignalClass, ReconciledFindingGroup
from cure_subsequent_review.discussion_signals import DiscussionLinkResult
from cure_subsequent_review.memory_store import group_identity_for_cache


DiscussionClassifier = Callable[[str], str | dict[str, Any]]


class DiscussionLinkerMemory(Protocol):
    def get_linker_result(
        self,
        *,
        event_id: str,
        body: str,
        current_head: str | None,
    ) -> dict[str, Any] | None: ...

    def update_linker_result(
        self,
        *,
        event_id: str,
        body: str,
        current_head: str,
        group_ids: tuple[str, ...],
        signal_class: DiscussionSignalClass,
        rationale: str = "",
        group_identities: dict[str, dict[str, Any]] | None = None,
    ) -> None: ...


def _strip_fenced_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(_strip_fenced_json(str(raw)))
    if not isinstance(parsed, dict):
        raise ValueError("discussion linker response must be a JSON object")
    return parsed


def _signal_class(value: object) -> DiscussionSignalClass | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return DiscussionSignalClass(text)
    except ValueError:
        return None


def _group_ids(value: object, *, known_group_ids: set[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_items = value if isinstance(value, list | tuple) else (value,)
    ids: list[str] = []
    for item in raw_items:
        if item is None:
            continue
        group_id = str(item).strip()
        if group_id and group_id in known_group_ids:
            ids.append(group_id)
    return tuple(dict.fromkeys(ids))


def _cached_group_identity_matches(cached: object, current: dict[str, Any] | None) -> bool:
    if not isinstance(cached, dict) or not isinstance(current, dict):
        return False
    cached_fingerprint = str(cached.get("fingerprint") or "").strip()
    current_fingerprint = str(current.get("fingerprint") or "").strip()
    if cached_fingerprint and current_fingerprint and cached_fingerprint == current_fingerprint:
        return True
    cached_origin = str(cached.get("origin_digest") or "").strip()
    current_origin = str(current.get("origin_digest") or "").strip()
    return bool(cached_origin and current_origin and cached_origin == current_origin)


def _prompt(event: DiscussionEvent, groups: tuple[ReconciledFindingGroup, ...]) -> str:
    findings = []
    for group in groups:
        findings.append(
            {
                "group_id": group.group_id,
                "canonical_id": group.canonical_id,
                "finding_ids": list(group.finding_ids),
                "local_findings": list(group.local_findings),
            }
        )
    return (
        "Classify one PR discussion event against prior review findings.\n"
        "Return strict JSON with keys: group_ids (array of confident group ids or null), "
        "signal_class (one of developer_claim_fixed, resolved_thread_hint, by_design, "
        "addressed_elsewhere, duplicate_superseded, unresolved_thread_hint, pushback, "
        "authority_conflict), and rationale. Topical low-confidence matches must use null "
        "rather than guessing a finding id.\n\n"
        f"Event JSON:\n{json.dumps(event.to_json(), indent=2, sort_keys=True)}\n\n"
        f"Prior finding groups JSON:\n{json.dumps(findings, indent=2, sort_keys=True)}\n"
    )


@dataclass(frozen=True)
class LlmDiscussionLinker:
    """Callable discussion linker that normalizes/caches an LLM JSON response."""

    classifier: DiscussionClassifier
    current_head: str | None = None
    memory_store: DiscussionLinkerMemory | None = None

    def __call__(self, event: DiscussionEvent, groups: tuple[ReconciledFindingGroup, ...]) -> DiscussionLinkResult:
        cached = self._cached(event, groups)
        if cached is not None:
            return cached

        known_group_ids = {group.group_id for group in groups}
        try:
            payload = _payload(self.classifier(_prompt(event, groups)))
        except Exception as exc:  # noqa: BLE001 - malformed/failed linker output degrades semantic artifacts
            return DiscussionLinkResult(
                group_ids=(),
                signal_class=None,
                rationale=f"llm_linker_malformed:{type(exc).__name__}",
            )
        signal_class = _signal_class(payload.get("signal_class"))
        group_ids = _group_ids(payload.get("group_ids"), known_group_ids=known_group_ids)
        rationale = str(payload.get("rationale") or "").strip()
        result = DiscussionLinkResult(group_ids=group_ids, signal_class=signal_class, rationale=rationale)
        self._store(event, result, groups)
        return result

    def _cached(self, event: DiscussionEvent, groups: tuple[ReconciledFindingGroup, ...]) -> DiscussionLinkResult | None:
        if self.memory_store is None:
            return None
        try:
            payload = self.memory_store.get_linker_result(
                event_id=event.event_id,
                body=event.body,
                current_head=self.current_head,
            )
        except Exception:  # noqa: BLE001 - cache failure must not block linking
            return None
        if not payload:
            return None
        signal_class = _signal_class(payload.get("signal_class"))
        raw_groups = payload.get("group_ids")
        group_ids = tuple(str(item).strip() for item in raw_groups if str(item).strip()) if isinstance(raw_groups, list) else ()
        current_identities = {group.group_id: group_identity_for_cache(group) for group in groups}
        raw_cached_identities = payload.get("group_identities")
        cached_identities: dict[str, Any] = raw_cached_identities if isinstance(raw_cached_identities, dict) else {}
        valid_group_ids = tuple(
            group_id
            for group_id in group_ids
            if _cached_group_identity_matches(cached_identities.get(group_id), current_identities.get(group_id))
        )
        if group_ids and not valid_group_ids:
            return None
        return DiscussionLinkResult(
            group_ids=valid_group_ids,
            signal_class=signal_class,
            rationale=str(payload.get("rationale") or "").strip(),
        )

    def _store(
        self,
        event: DiscussionEvent,
        result: DiscussionLinkResult,
        groups: tuple[ReconciledFindingGroup, ...],
    ) -> None:
        if self.memory_store is None or result.signal_class is None or not str(self.current_head or "").strip():
            return
        try:
            current_identities = {group.group_id: group_identity_for_cache(group) for group in groups}
            self.memory_store.update_linker_result(
                event_id=event.event_id,
                body=event.body,
                current_head=str(self.current_head),
                group_ids=result.group_ids,
                signal_class=result.signal_class,
                rationale=result.rationale,
                group_identities={group_id: current_identities[group_id] for group_id in result.group_ids if group_id in current_identities},
            )
        except Exception:  # noqa: BLE001 - cache failure must not block linking
            return


__all__ = ["DiscussionClassifier", "DiscussionLinkerMemory", "LlmDiscussionLinker"]
