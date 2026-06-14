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
    DispositionLedger,
    SourceState,
    SourceVerificationLedger,
    SourceVerificationRow,
)

MEMORY_SCHEMA_VERSION = 1


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
    raw_citations = row_json.get("current_source_citations")
    citations: list[Any] = raw_citations if isinstance(raw_citations, list) else []
    raw_source_refs = row_json.get("inspected_source_refs")
    source_refs: list[Any] = raw_source_refs if isinstance(raw_source_refs, list) else []
    return {
        "fingerprint": str(provenance.get("fingerprint") or "").strip(),
        "source_refs_digest": _json_digest(tuple(str(item).strip() for item in source_refs if str(item).strip())),
        "citations_digest": _json_digest(tuple(_normalized_citation(item) for item in citations if isinstance(item, dict))),
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
    cached_fingerprint = str(cached.get("fingerprint") or "").strip()
    current_fingerprint = str(current.get("fingerprint") or "").strip()
    if cached_fingerprint and current_fingerprint and cached_fingerprint == current_fingerprint:
        return True
    for key in ("source_refs_digest", "citations_digest", "origin_digest"):
        cached_value = str(cached.get(key) or "").strip()
        current_value = str(current.get(key) or "").strip()
        if cached_value and current_value and cached_value == current_value:
            return True
    return False


def group_identity_for_cache(group: Any) -> dict[str, Any]:
    provenance = getattr(group, "provenance", ()) or ()
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
            head_entry = {
                "source_state": row.source_state.value,
                "disposition": disposition.action.value if disposition is not None else None,
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

    def synthesize_resolved_source_row(
        self,
        *,
        group_id: str,
        finding_ids: tuple[str, ...],
        row_id: str,
        current_head: str | None,
        current_identity: dict[str, Any] | None = None,
    ) -> SourceVerificationRow | None:
        head = _clean_head(current_head)
        if not head:
            return None
        entry = self.load().get("findings", {}).get(group_id)
        if not isinstance(entry, dict):
            return None
        if entry.get("last_seen_head") != head:
            return None
        head_entry = entry
        heads = entry.get("heads")
        if isinstance(heads, dict):
            candidate = heads.get(head)
            if isinstance(candidate, dict):
                head_entry = candidate
        if head_entry.get("source_state") != SourceState.RESOLVED_FROM_SOURCE.value:
            return None
        if not _finding_identity_matches(entry.get("finding_ids"), finding_ids):
            return None
        if not _stable_identity_matches(head_entry.get("stable_identity") or entry.get("stable_identity"), current_identity):
            return None

        cached_row = head_entry.get("source_verification_row")
        citations: tuple[dict[str, Any], ...] = ()
        inspected_refs: tuple[str, ...] = ()
        if isinstance(cached_row, dict):
            raw_citations = cached_row.get("current_source_citations", [])
            if isinstance(raw_citations, list):
                citations = tuple(dict(item) for item in raw_citations if isinstance(item, dict))
            raw_refs = cached_row.get("inspected_source_refs", [])
            if isinstance(raw_refs, list):
                inspected_refs = tuple(str(item) for item in raw_refs if str(item).strip())

        return SourceVerificationRow(
            row_id=row_id,
            group_id=group_id,
            finding_ids=finding_ids,
            source_state=SourceState.RESOLVED_FROM_SOURCE,
            current_source_citations=citations,
            inspected_source_refs=inspected_refs,
            provenance={
                "source": "memory_cache",
                "not_source_proof": True,
                "last_seen_head": head,
                "memory_path": str(self.path),
                "stable_identity": dict(current_identity or {}),
                "rationale": "unchanged resolved finding replayed from per-PR memory after stable group identity match; not fresh source proof",
            },
        )
