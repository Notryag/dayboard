"""Versioned extensions for durable Run events."""

from __future__ import annotations

from pydantic import BaseModel, Field, JsonValue


AGENT_PLATFORM_FAILURE_EVENT_KIND = "agent-platform.failure"


class EventExtensionEnvelope(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    schema_version: int = Field(ge=1)
    payload: dict[str, JsonValue]


class RunFailureEventPayload(BaseModel):
    error_type: str = Field(min_length=1, max_length=240)


def build_run_failure_event_extension(error_type: str) -> EventExtensionEnvelope:
    payload = RunFailureEventPayload(error_type=error_type)
    return EventExtensionEnvelope(
        kind=AGENT_PLATFORM_FAILURE_EVENT_KIND,
        schema_version=1,
        payload=payload.model_dump(mode="json"),
    )
