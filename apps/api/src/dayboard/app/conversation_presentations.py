"""Typed Dayboard payloads carried by Platform presentation envelopes."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from agent_platform.core import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    PresentationEnvelope,
)
from dayboard.app.schedule_queries import CalendarEntryView, TaskItemView


DAYBOARD_PRESENTATION_KIND = "dayboard.schedule-results"
DAYBOARD_PRESENTATION_SCHEMA_VERSION = 1

ScheduleOperation = Literal[
    "calendar_entry_created",
    "calendar_entry_found",
    "calendar_entry_rescheduled",
    "calendar_entry_cancelled",
    "task_item_created",
    "task_item_found",
    "task_item_updated",
]


class CalendarPresentationItem(BaseModel):
    kind: Literal["calendar"] = "calendar"
    value: CalendarEntryView


class TaskPresentationItem(BaseModel):
    kind: Literal["task"] = "task"
    value: TaskItemView


SchedulePresentationItem = Annotated[
    CalendarPresentationItem | TaskPresentationItem,
    Field(discriminator="kind"),
]


class ScheduleResultPart(BaseModel):
    tool_call_id: str = Field(min_length=1, max_length=240)
    operation: ScheduleOperation
    item: SchedulePresentationItem

    @model_validator(mode="after")
    def validate_operation_kind(self) -> ScheduleResultPart:
        expected_prefix = "calendar_entry_" if self.item.kind == "calendar" else "task_item_"
        if not self.operation.startswith(expected_prefix):
            raise ValueError("schedule operation does not match its item kind")
        return self


class DayboardPresentationPayload(BaseModel):
    parts: list[ScheduleResultPart] = Field(max_length=100)

    @model_validator(mode="after")
    def require_unique_entities(self) -> DayboardPresentationPayload:
        entity_keys = [(part.item.kind, part.item.value.id) for part in self.parts]
        if len(entity_keys) != len(set(entity_keys)):
            raise ValueError("presentation cannot contain duplicate schedule entities")
        return self


class DayboardPresentationEnvelope(BaseModel):
    kind: Literal["dayboard.schedule-results"] = DAYBOARD_PRESENTATION_KIND
    schema_version: Literal[1] = DAYBOARD_PRESENTATION_SCHEMA_VERSION
    payload: DayboardPresentationPayload


class DayboardConversationMessage(BaseModel):
    id: UUID
    thread_id: UUID
    run_id: UUID
    role: ConversationRole
    content: str
    presentation: DayboardPresentationEnvelope | None
    created_at: AwareDatetime


class DayboardConversationMessagePage(BaseModel):
    items: list[DayboardConversationMessage]
    next_cursor: UUID | None


def build_dayboard_presentation(parts: list[dict]) -> PresentationEnvelope:
    payload = DayboardPresentationPayload.model_validate({"parts": parts})
    return PresentationEnvelope(
        kind=DAYBOARD_PRESENTATION_KIND,
        schema_version=DAYBOARD_PRESENTATION_SCHEMA_VERSION,
        payload=payload.model_dump(mode="json"),
    )


def project_dayboard_presentation(
    presentation: PresentationEnvelope | None,
) -> DayboardPresentationEnvelope | None:
    if (
        presentation is None
        or presentation.kind != DAYBOARD_PRESENTATION_KIND
        or presentation.schema_version != DAYBOARD_PRESENTATION_SCHEMA_VERSION
    ):
        return None
    return DayboardPresentationEnvelope(
        payload=DayboardPresentationPayload.model_validate(presentation.payload)
    )


def dayboard_presentation_parts(presentation: PresentationEnvelope | None) -> list[dict]:
    projected = project_dayboard_presentation(presentation)
    if projected is None:
        return []
    return [part.model_dump(mode="json") for part in projected.payload.parts]


def project_conversation_message(message: ConversationMessage) -> DayboardConversationMessage:
    return DayboardConversationMessage(
        id=message.id,
        thread_id=message.thread_id,
        run_id=message.run_id,
        role=message.role,
        content=message.content,
        presentation=project_dayboard_presentation(message.presentation),
        created_at=message.created_at,
    )


def project_conversation_message_page(
    page: ConversationMessagePage,
) -> DayboardConversationMessagePage:
    return DayboardConversationMessagePage(
        items=[project_conversation_message(message) for message in page.items],
        next_cursor=page.next_cursor,
    )
