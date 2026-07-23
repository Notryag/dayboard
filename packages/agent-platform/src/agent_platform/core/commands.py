"""Contracts for durable command submission."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from agent_platform.core.runs import AgentRunStatus


@dataclass(frozen=True, slots=True)
class CommandSubmission:
    run_id: UUID
    status: AgentRunStatus
    created: bool
    thread_id: UUID
