from __future__ import annotations

from typing import Any


class ReviewflowError(RuntimeError):
    pass


class StepGroundingValidationError(ReviewflowError):
    def __init__(
        self,
        message: str,
        *,
        step_validation: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.step_validation = dict(step_validation) if isinstance(step_validation, dict) else None
