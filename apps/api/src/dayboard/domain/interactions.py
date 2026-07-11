from __future__ import annotations

from pydantic import BaseModel, Field


class ClarificationChoiceRequest(BaseModel):
    state_version: int = Field(ge=1)
    option_key: str = Field(pattern=r"^candidate_[1-9][0-9]*$", max_length=40)
