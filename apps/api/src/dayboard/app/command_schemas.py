from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

class CommandRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CommandRunResponse(BaseModel):
    run_id: str
    status: Literal["queued"] = "queued"
