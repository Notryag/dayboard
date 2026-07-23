"""Versioned product-presentation envelopes."""

from __future__ import annotations

from pydantic import BaseModel, Field, JsonValue


class PresentationEnvelope(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    schema_version: int = Field(ge=1)
    payload: dict[str, JsonValue]
