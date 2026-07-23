from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from dayboard.domain.calendar import CalendarTimingKind


CLARIFICATION_INTERACTION_TYPE = "dayboard.clarification"
CLARIFICATION_SCHEMA_VERSION = 1


class ClarificationChoiceRequest(BaseModel):
    state_version: int = Field(ge=1)
    option_key: str = Field(pattern=r"^candidate_[1-9][0-9]*$", max_length=40)


class SuggestedChoiceOption(BaseModel):
    key: str = Field(pattern=r"^candidate_[1-9][0-9]*$", max_length=40)
    label: str = Field(min_length=1, max_length=240)


class SuggestedChoiceCandidate(SuggestedChoiceOption):
    kind: Literal["suggested"] = "suggested"
    value: str = Field(min_length=1, max_length=1000)


class CalendarEntryChoiceOption(BaseModel):
    key: str = Field(pattern=r"^candidate_[1-9][0-9]*$", max_length=40)
    title: str = Field(min_length=1, max_length=240)
    timing_kind: CalendarTimingKind
    scheduled_date: date | None = None
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    timezone: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_timing(self) -> CalendarEntryChoiceOption:
        if self.timing_kind is CalendarTimingKind.anytime:
            if self.scheduled_date is None or self.start_time is not None or self.end_time is not None:
                raise ValueError("anytime candidates require only scheduled_date")
        elif self.start_time is None or self.end_time is None or self.scheduled_date is not None:
            raise ValueError("timed candidates require start_time and end_time")
        return self


class CalendarEntryChoiceCandidate(CalendarEntryChoiceOption):
    kind: Literal["calendar"] = "calendar"
    id: UUID
    row_version: int = Field(ge=1)
    status: Literal["scheduled", "completed", "cancelled"]


class SuggestedChoicePresentation(BaseModel):
    type: Literal["suggested_choice"] = "suggested_choice"
    options: list[SuggestedChoiceOption] = Field(min_length=1, max_length=10)


class CalendarEntryChoicePresentation(BaseModel):
    type: Literal["calendar_entry_choice"] = "calendar_entry_choice"
    options: list[CalendarEntryChoiceOption] = Field(min_length=1, max_length=10)


ClarificationCandidate = Annotated[
    SuggestedChoiceCandidate | CalendarEntryChoiceCandidate,
    Field(discriminator="kind"),
]
ClarificationPresentation = Annotated[
    SuggestedChoicePresentation | CalendarEntryChoicePresentation,
    Field(discriminator="type"),
]


class ClarificationPayload(BaseModel):
    response_kind: Literal["free_text", "single_choice", "calendar_choice"]
    candidates: list[ClarificationCandidate] = Field(default_factory=list, max_length=10)
    presentation: ClarificationPresentation | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> ClarificationPayload:
        if self.response_kind == "free_text":
            if self.candidates or self.presentation is not None:
                raise ValueError("free-text clarification cannot contain choices")
            return self

        if not self.candidates or self.presentation is None:
            raise ValueError("choice clarification requires candidates and presentation")
        if self.response_kind == "single_choice":
            expected_kind = "suggested"
            expected_presentation = "suggested_choice"
        else:
            expected_kind = "calendar"
            expected_presentation = "calendar_entry_choice"
        if any(candidate.kind != expected_kind for candidate in self.candidates):
            raise ValueError("candidate kind does not match clarification response kind")
        if self.presentation.type != expected_presentation:
            raise ValueError("presentation does not match clarification response kind")
        if [candidate.key for candidate in self.candidates] != [
            option.key for option in self.presentation.options
        ]:
            raise ValueError("candidate and presentation option keys must match")
        return self


class ClarificationPublicPayload(BaseModel):
    presentation: ClarificationPresentation | None = None


class ClarificationInteractionView(BaseModel):
    interaction_type: Literal["dayboard.clarification"] = CLARIFICATION_INTERACTION_TYPE
    schema_version: Literal[1] = CLARIFICATION_SCHEMA_VERSION
    source_run_id: UUID
    prompt: str = Field(min_length=1, max_length=1000)
    payload: ClarificationPublicPayload


class ClarificationConversationState(BaseModel):
    thread_id: UUID
    interaction: ClarificationInteractionView
    version: int = Field(ge=1)
    expires_at: AwareDatetime
    updated_at: AwareDatetime
