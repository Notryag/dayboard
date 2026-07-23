"""Product-neutral outcomes for durable Run execution."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from agent_platform.core.interactions import PendingInteraction
from agent_platform.core.presentations import PresentationEnvelope


class RunExecutionOutcomeKind(StrEnum):
    completed = "completed"
    needs_interaction = "needs_interaction"


class RunExecutionOutcome(BaseModel):
    kind: RunExecutionOutcomeKind
    result_message: str = Field(min_length=1, max_length=4000)
    presentation: PresentationEnvelope | None = None
    interaction: PendingInteraction | None = None
    interaction_expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_interaction_state(self) -> RunExecutionOutcome:
        has_interaction = self.interaction is not None
        has_expiry = self.interaction_expires_at is not None
        if self.kind == RunExecutionOutcomeKind.needs_interaction:
            if not has_interaction or not has_expiry:
                raise ValueError("needs_interaction requires an interaction and expiry")
        elif has_interaction or has_expiry:
            raise ValueError("completed outcomes cannot carry an interaction")
        return self


class RunExecutionFailure(BaseModel):
    error_type: str = Field(min_length=1, max_length=240)
    error_message: str = Field(min_length=1, max_length=4000)
    presentation: PresentationEnvelope | None = None
