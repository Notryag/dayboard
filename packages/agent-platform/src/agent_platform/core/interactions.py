"""Versioned resumable-interaction contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, JsonValue


class PendingInteraction(BaseModel):
    interaction_type: str = Field(min_length=1, max_length=80)
    schema_version: int = Field(ge=1)
    source_run_id: UUID
    prompt: str = Field(min_length=1, max_length=1000)
    payload: dict[str, JsonValue]
