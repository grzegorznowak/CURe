"""Shared per-PR memory store for subsequent-review runtime.

The store is audit and performance state only.  Replayed entries can avoid an
unchanged verifier call, but they are never treated as fresh source proof.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cure_subsequent_review.contracts import (
    DiscussionSignalClass,
    DispositionAction,
    DispositionLedger,
    SourceState,
    SourceVerificationLedger,
    SourceVerificationRow,
)

MEMORY_SCHEMA_VERSION = 1
_SAFE_TERMINAL_NON_REPORTABLE_DISPOSITIONS = frozenset(
    {
        DispositionAction.SUPPRESS_DUPLICATE.value,
        DispositionAction.MOVE_OUT_OF_SCOPE.value,
    }
)
_SAFE_TERMINAL_REPLAY_SOURCE_STATES = frozenset({SourceState.STILL_OPEN.value})


def _string_attr(obj: Any, name: str) -> str:
    return str(getattr(obj, name)).strip()


def _clean_head(head: str | None) -> str:
    return str(head or "").strip()


def _body_hash(body: str) -> str:
    return hashlib.sha256(str(body or "").encode("utf-8")).hexdigest()


def _linker_cache_key(*, event_id: str, body: str, current_head: str) -> str:
    return f"{current_head}:{event_id}:{_body_hash(body)}"


def _finding_identity_matches(cached: object, current: tuple[str, ...]) -> bool:
    cached_ids = tuple(str(item).strip() for item in cached if str(item).strip()) if isinstance(cached, list | tuple) else ()
    current_ids = tuple(str(item).strip() for item in current if str(item).strip())
    return bool(cached_ids) and set(cached_ids) == set(current_ids)


def _stable_identity_from_row(row_json: dict[str, Any]) -> dict[str, Any]:
    raw_provenance = row_json.get("provenance")
    provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    raw_cached_identity = provenance.get("stable_identity")
    cached_identity: dict[str, Any] = raw_cached_identity if isinstance(raw_cached_identity, dict) else {}
    raw_citations = row_json.get("current_source_citations")
    citations: list[Any] = raw_citations if isinstance(raw_citations, list) else []
    raw_source_refs = row_json.get("inspected_source_refs")
    source_refs: list[Any] = raw_source_refs if isinstance(raw_source_refs, list) else []
    normalized_source_refs = tuple(str(item).strip() for item in source_refs if str(item).strip())
    normalized_citations = tuple(_normalized_citation(item) for item in citations if isinstance(item, dict))
    computed = {
        "fingerprint": str(provenance.get("fingerprint") or "").strip(),
        "source_refs_digest": _json_digest(normalized_source_refs) if normalized_source_refs else "",
        "citations_digest": _json_digest(normalized_citations) if normalized_citations else "",
        "origin_digest": "",
    }
    return {
        "fingerprint": computed["fingerprint"] or str(cached_identity.get("fingerprint") or "").strip(),
        "source_refs_digest": computed["source_refs_digest"] or str(cached_identity.get("source_refs_digest") or "").strip(),
        "citations_digest": computed["citations_digest"] or str(cached_identity.get("citations_digest") or "").strip(),
        "origin_digest": computed["origin_digest"] or str(cached_identity.get("origin_digest") or "").strip(),
    }


def _json_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _normalized_citation(citation: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(citation.get("path") or "").strip(),
        "line": int(citation.get("start_line") or citation.get("line") or 0),
    }


def _stable_identity_matches(cached: object, current: dict[str, Any] | None) -> bool:
    if not isinstance(cached, dict) or not isinstance(current, dict):
        return False
    rich_keys = ("fingerprint", "source_refs_digest", "citations_digest")
    matched_rich_identity = False
    for key in rich_keys:
        cached_value = str(cached.get(key) or "").strip()
        current_value = str(current.get(key) or "").strip()
        if not cached_value or not current_value:
            continue
        if cached_value != current_value:
            return False
        matched_rich_identity = True
    if matched_rich_identity:
        return True

    cached_has_rich_identity = any(str(cached.get(key) or "").strip() for key in rich_keys)
    current_has_rich_identity = any(str(current.get(key) or "").strip() for key in rich_keys)
    if cached_has_rich_identity or current_has_rich_identity:
        return False

    cached_origin = str(cached.get("origin_digest") or "").strip()
    current_origin = str(current.get("origin_digest") or "").strip()
    return bool(cached_origin and current_origin and cached_origin == current_origin)


def _terminal_replay_fingerprint_from_disposition(disposition: Any | None) -> str:
    if disposition is None:
        return ""
    provenance = getattr(disposition, "provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    return _json_digest(
        {
            "discussion_signal_row_ids": tuple(str(item) for item in getattr(disposition, "discussion_signal_row_ids", ()) or ()),
            "discussion_signal_classes": tuple(str(item) for item in provenance.get("discussion_signal_classes", ()) or ()),
            "discussion_policies": tuple(str(item) for item in provenance.get("discussion_policies", ()) or ()),
            "policy_override": str(provenance.get("policy_override") or ""),
        }
    )


def _terminal_replay_fingerprint_matches(cached: object, current: str | None) -> bool:
    cached_value = str(cached or "").strip()
    current_value = str(current or "").strip()
    return bool(cached_value and current_value and cached_value == current_value)


def group_identity_for_cache(group: Any) -> dict[str, Any]:
    provenance = getattr(group, "provenance", ()) or ()
    source_refs: list[str] = []
    for finding in getattr(group, "local_findings", ()) or ():
        if not isinstance(finding, dict):
            continue
        raw_refs = finding.get("source_evidence_snippets", ())
        if isinstance(raw_refs, str):
            raw_refs = (raw_refs,)
        if isinstance(raw_refs, list | tuple):
            source_refs.extend(str(ref).strip() for ref in raw_refs if str(ref).strip())
    normalized_source_refs = tuple(dict.fromkeys(source_refs))
    origins: list[dict[str, Any]] = []
    for item in provenance:
        if hasattr(item, "to_json"):
            raw = item.to_json()
        elif isinstance(item, dict):
            raw = item
        else:
            raw = {}
        origins.append(
            {
                "entry_id": str(raw.get("corpus_entry_id") or raw.get("entry_id") or "").strip(),
                "source_type": str(raw.get("source_type") or "").strip(),
                "artifact_path": str(raw.get("artifact_path") or "").strip(),
                "comment_url": str(raw.get("comment_url") or "").strip(),
                "reviewed_head": str(raw.get("reviewed_head") or "").strip(),
            }
        )
    return {
        "canonical_id": str(getattr(group, "canonical_id", "") or "").strip(),
        "finding_ids": [str(item).strip() for item in (getattr(group, "finding_ids", ()) or ()) if str(item).strip()],
        "fingerprint": str(getattr(group, "fingerprint", "") or "").strip(),
        "source_refs_digest": _json_digest(normalized_source_refs) if normalized_source_refs else "",
        "origin_digest": _json_digest(tuple(origins)) if origins else "",
    }


@dataclass(frozen=True)
class ReviewMemoryStore:
    path: Path

    @classmethod
    def for_pr(cls, *, root: Path, pr: Any) -> "ReviewMemoryStore":
        path = (
            root
            / _string_attr(pr, "host")
            / _string_attr(pr, "owner")
            / _string_attr(pr, "repo")
            / _string_attr(pr, "number")
            / "cure_memory.json"
        )
        return cls(path=path)

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": MEMORY_SCHEMA_VERSION, "findings": {}, "linker_results": {}}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty()
        if not isinstance(payload, dict):
            return self._empty()
        if not isinstance(payload.get("findings"), dict):
            payload["findings"] = {}
        if not isinstance(payload.get("linker_results"), dict):
            payload["linker_results"] = {}
        payload["schema_version"] = MEMORY_SCHEMA_VERSION
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f".{self.path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(self.path)

    def update_findings(
        self,
        *,
        current_head: str,
        source_verification: SourceVerificationLedger,
        disposition_ledger: DispositionLedger | None = None,
        run_provenance: dict[str, Any] | None = None,
    ) -> None:
        head = _clean_head(current_head)
        if not head:
            return
        payload = self.load()
        findings = payload["findings"]
        dispositions = {
            row.group_id: row
            for row in (disposition_ledger.dispositions if disposition_ledger is not None else ())
        }
        provenance = dict(run_provenance or {})

        for row in source_verification.rows:
            previous = findings.get(row.group_id)
            previous_heads: list[str] = []
            heads: dict[str, Any] = {}
            if isinstance(previous, dict):
                raw_previous_heads = previous.get("previous_heads", [])
                if isinstance(raw_previous_heads, list):
                    previous_heads = [str(item) for item in raw_previous_heads if str(item).strip()]
                raw_heads = previous.get("heads", {})
                if isinstance(raw_heads, dict):
                    heads = {str(key): value for key, value in raw_heads.items() if isinstance(value, dict)}
                previous_head = str(previous.get("last_seen_head") or "").strip()
                if previous_head and previous_head != head and previous_head not in previous_heads:
                    previous_heads.append(previous_head)

            disposition = dispositions.get(row.group_id)
            row_json = row.to_json()
            stable_identity = _stable_identity_from_row(row_json)
            terminal_replay_fingerprint = _terminal_replay_fingerprint_from_disposition(disposition)
            head_entry = {
                "source_state": row.source_state.value,
                "disposition": disposition.action.value if disposition is not None else None,
                "terminal_replay_fingerprint": terminal_replay_fingerprint,
                "stable_identity": stable_identity,
                "source_verification_row": row_json,
                "disposition_row_id": disposition.row_id if disposition is not None else None,
                "run_provenance": provenance,
            }
            heads[head] = head_entry
            findings[row.group_id] = {
                "group_id": row.group_id,
                "finding_ids": list(row.finding_ids),
                "source_state": row.source_state.value,
                "disposition": disposition.action.value if disposition is not None else None,
                "terminal_replay_fingerprint": terminal_replay_fingerprint,
                "last_seen_head": head,
                "previous_heads": previous_heads,
                "heads": heads,
                "stable_identity": stable_identity,
                "source_verification_row": row_json,
                "disposition_row_id": disposition.row_id if disposition is not None else None,
                "run_provenance": provenance,
            }
        self.save(payload)

    def get_linker_result(
        self,
        *,
        event_id: str,
        body: str,
        current_head: str | None,
    ) -> dict[str, Any] | None:
        head = _clean_head(current_head)
        event = str(event_id or "").strip()
        if not head or not event:
            return None
        entry = self.load().get("linker_results", {}).get(
            _linker_cache_key(event_id=event, body=body, current_head=head)
        )
        if not isinstance(entry, dict):
            return None
        if entry.get("head") != head or entry.get("event_id") != event or entry.get("body_hash") != _body_hash(body):
            return None
        return dict(entry)

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
    ) -> None:
        head = _clean_head(current_head)
        event = str(event_id or "").strip()
        if not head or not event:
            return
        payload = self.load()
        linker_results = payload["linker_results"]
        body_digest = _body_hash(body)
        linker_results[_linker_cache_key(event_id=event, body=body, current_head=head)] = {
            "event_id": event,
            "body_hash": body_digest,
            "head": head,
            "group_ids": list(group_ids),
            "group_identities": dict(group_identities or {}),
            "signal_class": signal_class.value,
            "rationale": rationale,
        }
        self.save(payload)

    def _matching_head_entry(
        self,
        *,
        group_id: str,
        current_head: str,
        current_identity: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not isinstance(current_identity, dict):
            return None
        findings = self.load().get("findings", {})
        if not isinstance(findings, dict):
            return None

        candidates: list[dict[str, Any]] = []
        direct = findings.get(group_id)
        if isinstance(direct, dict):
            candidates.append(direct)
        candidates.extend(
            entry
            for key, entry in findings.items()
            if key != group_id and isinstance(entry, dict)
        )

        for entry in candidates:
            if entry.get("last_seen_head") != current_head:
                continue
            head_entry = entry
            heads = entry.get("heads")
            if isinstance(heads, dict):
                candidate = heads.get(current_head)
                if isinstance(candidate, dict):
                    head_entry = candidate
            stable_identity = head_entry.get("stable_identity") or entry.get("stable_identity")
            if _stable_identity_matches(stable_identity, current_identity):
                return entry, head_entry
        return None

    def synthesize_source_row(
        self,
        *,
        group_id: str,
        finding_ids: tuple[str, ...],
        row_id: str,
        current_head: str | None,
        current_identity: dict[str, Any] | None = None,
        current_terminal_replay_fingerprint: str | None = None,
    ) -> SourceVerificationRow | None:
        head = _clean_head(current_head)
        if not head:
            return None
        match = self._matching_head_entry(group_id=group_id, current_head=head, current_identity=current_identity)
        if match is None:
            return None
        entry, head_entry = match
        source_state_value = str(head_entry.get("source_state") or "").strip()
        disposition = str(head_entry.get("disposition") or "").strip()
        if source_state_value == SourceState.RESOLVED_FROM_SOURCE.value:
            cache_reason = "resolved_from_source_replay"
        elif (
            source_state_value in _SAFE_TERMINAL_REPLAY_SOURCE_STATES
            and disposition in _SAFE_TERMINAL_NON_REPORTABLE_DISPOSITIONS
            and _terminal_replay_fingerprint_matches(
                head_entry.get("terminal_replay_fingerprint"), current_terminal_replay_fingerprint
            )
        ):
            cache_reason = "terminal_non_reportable_replay"
        else:
            return None

        try:
            source_state = SourceState(source_state_value)
        except ValueError:
            return None

        cached_row = head_entry.get("source_verification_row")
        cached_provenance: dict[str, Any] = {}
        citations: tuple[dict[str, Any], ...] = ()
        inspected_refs: tuple[str, ...] = ()
        cached_unavailable: tuple[str, ...] = ()
        if isinstance(cached_row, dict):
            raw_provenance = cached_row.get("provenance")
            if isinstance(raw_provenance, dict):
                cached_provenance = dict(raw_provenance)
            raw_citations = cached_row.get("current_source_citations", [])
            if isinstance(raw_citations, list):
                citations = tuple(dict(item) for item in raw_citations if isinstance(item, dict))
            raw_refs = cached_row.get("inspected_source_refs", [])
            if isinstance(raw_refs, list):
                inspected_refs = tuple(str(item) for item in raw_refs if str(item).strip())
            raw_unavailable = cached_row.get("unavailable_reasons", [])
            if isinstance(raw_unavailable, list):
                cached_unavailable = tuple(str(item) for item in raw_unavailable if str(item).strip())

        provenance = {
            "source": "memory_cache",
            "cache_status": "hit",
            "cache_reason": cache_reason,
            "not_source_proof": True,
            "cached_group_id": str(entry.get("group_id") or group_id),
            "cached_disposition": disposition or None,
            "last_seen_head": head,
            "memory_path": str(self.path),
            "stable_identity": dict(current_identity or {}),
            "terminal_replay_fingerprint": str(current_terminal_replay_fingerprint or ""),
            "rationale": (
                "unchanged source-verification result replayed from per-PR memory after stable identity match"
                if cache_reason == "resolved_from_source_replay"
                else "safe terminal non-reportable disposition replayed from per-PR memory after stable identity match; not source proof"
            ),
        }
        policy_override = str(cached_provenance.get("policy_override") or "").strip()
        if policy_override:
            provenance["policy_override"] = policy_override
        return SourceVerificationRow(
            row_id=row_id,
            group_id=group_id,
            finding_ids=finding_ids,
            source_state=source_state,
            current_source_citations=citations if source_state is SourceState.RESOLVED_FROM_SOURCE else (),
            inspected_source_refs=inspected_refs,
            unavailable_reasons=cached_unavailable,
            provenance=provenance,
        )

    def synthesize_resolved_source_row(
        self,
        *,
        group_id: str,
        finding_ids: tuple[str, ...],
        row_id: str,
        current_head: str | None,
        current_identity: dict[str, Any] | None = None,
    ) -> SourceVerificationRow | None:
        row = self.synthesize_source_row(
            group_id=group_id,
            finding_ids=finding_ids,
            row_id=row_id,
            current_head=current_head,
            current_identity=current_identity,
        )
        if row is None or row.source_state is not SourceState.RESOLVED_FROM_SOURCE:
            return None
        return row
