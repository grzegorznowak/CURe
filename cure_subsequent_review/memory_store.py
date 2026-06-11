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
            head_entry = {
                "source_state": row.source_state.value,
                "disposition": disposition.action.value if disposition is not None else None,
                "source_verification_row": row.to_json(),
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
                "source_verification_row": row.to_json(),
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
                "rationale": "unchanged resolved finding replayed from per-PR memory; not fresh source proof",
            },
        )
