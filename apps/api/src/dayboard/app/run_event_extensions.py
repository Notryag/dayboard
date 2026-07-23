"""Typed Dayboard-owned payloads for durable Run-event extensions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_platform.core import EventExtensionEnvelope


EVENT_EXTENSION_SCHEMA_VERSION = 1
NORTH_MODEL_CALL_EVENT_KIND = "north.model-call"
NORTH_TOOL_CALL_EVENT_KIND = "north.tool-call"


class ModelUsageEventPayload(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class NorthModelCallEventPayload(BaseModel):
    call_id: str | None = None
    call_index: int | None = Field(default=None, ge=1)
    caller: str | None = None
    latency_ms: int | float | None = Field(default=None, ge=0)
    usage: ModelUsageEventPayload = Field(default_factory=ModelUsageEventPayload)
    error_type: str | None = None


class NorthToolCallEventPayload(BaseModel):
    call_id: str | None = None
    tool_name: str = Field(min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | float | None = Field(default=None, ge=0)
    error_type: str | None = None


def build_event_extension(kind: str, payload: BaseModel) -> EventExtensionEnvelope:
    return EventExtensionEnvelope(
        kind=kind,
        schema_version=EVENT_EXTENSION_SCHEMA_VERSION,
        payload=payload.model_dump(mode="json", exclude_none=True),
    )
