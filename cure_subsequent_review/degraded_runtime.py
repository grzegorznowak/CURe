"""Runtime controller for degraded subsequent-review discussion fetches."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from meta import write_json

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    ModuleStatus,
    SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
)

DiscussionChoice = Literal["retry", "skip", "abort"]
DiscussionChoiceProvider = Callable[[DiscussionArtifact, int], str]
DiscussionFetcher = Callable[[], DiscussionArtifact]

_DEGRADED_DISCUSSION_REASONS = {
    "discussion_unavailable",
    "discussion_incomplete",
    "discussion_payload_malformed",
}


class DiscussionFetchAborted(RuntimeError):
    """Raised when the operator aborts after a degraded discussion fetch."""


@dataclass(frozen=True)
class DiscussionFetchController:
    """Fetch PR discussion once, then gate degraded results before artifact writes."""

    fetch_discussion: DiscussionFetcher
    artifact_dir: Path
    interactive: bool = False
    choice_provider: DiscussionChoiceProvider | None = None
    max_noninteractive_attempts: int = 3
    _attempts: list[dict[str, object]] = field(default_factory=list, init=False, repr=False)
    _choices: list[dict[str, object]] = field(default_factory=list, init=False, repr=False)

    @property
    def artifact_path(self) -> Path:
        return self.artifact_dir / "degraded_runtime.json"

    def fetch(self) -> DiscussionArtifact:
        attempt = 0
        while True:
            attempt += 1
            artifact = self.fetch_discussion()
            self._record_attempt(attempt=attempt, artifact=artifact)
            if not _is_degraded_discussion(artifact):
                if self._choices or artifact.status is ModuleStatus.SUCCESS:
                    self._write(status=ModuleStatus.SUCCESS, final_reason="discussion_available")
                return artifact

            choice = self._choose(artifact=artifact, attempt=attempt)
            self._choices.append({"attempt": attempt, "choice": choice})
            if choice == "retry":
                continue
            if choice == "skip":
                skipped = _skipped_discussion(artifact)
                self._write(status=ModuleStatus.DEGRADED, final_reason="operator_skipped_degraded_discussion")
                return skipped
            self._write(status="aborted", final_reason="operator_aborted_degraded_discussion")
            raise DiscussionFetchAborted("operator aborted after degraded PR discussion fetch")

    def _record_attempt(self, *, attempt: int, artifact: DiscussionArtifact) -> None:
        self._attempts.append(
            {
                "attempt": attempt,
                "status": artifact.status.value,
                "event_count": len(artifact.events),
                "status_reasons": list(artifact.status_reasons),
            }
        )

    def _choose(self, *, artifact: DiscussionArtifact, attempt: int) -> DiscussionChoice:
        if not self.interactive:
            return "retry" if attempt < max(1, self.max_noninteractive_attempts) else "skip"
        raw = self.choice_provider(artifact, attempt) if self.choice_provider is not None else _prompt_choice(artifact)
        normalized = str(raw or "").strip().lower()
        aliases = {"r": "retry", "s": "skip", "a": "abort"}
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"retry", "skip", "abort"}:
            return "skip"
        return normalized  # type: ignore[return-value]

    def _write(self, *, status: ModuleStatus | str, final_reason: str) -> None:
        status_value = status.value if isinstance(status, ModuleStatus) else status
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            self.artifact_path,
            {
                "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
                "module": "degraded_runtime_manager",
                "status": status_value,
                "final_reason": final_reason,
                "attempts": list(self._attempts),
                "operator_choices": list(self._choices),
            },
        )


def _is_degraded_discussion(artifact: DiscussionArtifact) -> bool:
    reasons = tuple(str(reason or "").strip() for reason in artifact.status_reasons if str(reason or "").strip())
    if reasons:
        return any(reason in _DEGRADED_DISCUSSION_REASONS for reason in reasons)
    return artifact.status is ModuleStatus.DEGRADED


def _skipped_discussion(artifact: DiscussionArtifact) -> DiscussionArtifact:
    reasons = tuple(dict.fromkeys((*artifact.status_reasons, "operator_skipped_degraded_discussion")))
    return DiscussionArtifact(status=ModuleStatus.DEGRADED, events=(), pagination=artifact.pagination, status_reasons=reasons)


def _prompt_choice(artifact: DiscussionArtifact) -> DiscussionChoice:
    reasons = ", ".join(artifact.status_reasons) if artifact.status_reasons else artifact.status.value
    while True:
        response = input(f"PR discussion fetch degraded ({reasons}). [R]etry / [S]kip / [A]bort: ")
        normalized = str(response or "").strip().lower()
        if normalized in {"r", "retry"}:
            return "retry"
        if normalized in {"s", "skip"}:
            return "skip"
        if normalized in {"a", "abort"}:
            return "abort"


__all__ = ["DiscussionFetchAborted", "DiscussionFetchController", "DiscussionFetcher"]
