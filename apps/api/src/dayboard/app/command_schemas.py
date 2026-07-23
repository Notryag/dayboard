from __future__ import annotations

from pydantic import BaseModel, Field

from agent_platform.runs import AgentRunStatus

class CommandRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CommandRunResponse(BaseModel):
    run_id: str
    status: AgentRunStatus = AgentRunStatus.queued
    thread_id: str | None = None
