"""Persistence ports for durable Runs and their events."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from agent_platform.core.events import EventExtensionEnvelope
from agent_platform.core.identity import UserContext
from agent_platform.core.conversations import ConversationRole
from agent_platform.core.runs import (
    AgentRun,
    AgentRunEvent,
    AgentRunEventCategory,
    AgentRunStatus,
)


class RunStore(Protocol):
    async def create(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        status: AgentRunStatus,
        run_id: UUID | None,
        model_name: str | None = None,
        first_human_message: str | None = None,
    ) -> AgentRun: ...

    async def transition_status(
        self,
        context: UserContext,
        run_id: UUID,
        *,
        from_statuses: set[AgentRunStatus],
        status: AgentRunStatus,
        error: str | None = None,
        message_count: int | None = None,
        first_human_message: str | None = None,
        last_ai_message: str | None = None,
    ) -> AgentRun | None: ...

    async def get(self, context: UserContext, run_id: UUID) -> AgentRun | None: ...

    async def get_for_update(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRun | None: ...

    async def get_for_worker(self, run_id: UUID) -> AgentRun | None: ...

    async def get_active_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> AgentRun | None: ...

    async def list_stale_running(self, *, updated_before: datetime) -> list[AgentRun]: ...

    async def list_stale_queued(self, *, created_before: datetime) -> list[AgentRun]: ...


class RunEventStore(Protocol):
    async def append(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        event_type: str,
        category: AgentRunEventCategory,
        content: str | None = None,
        extension: EventExtensionEnvelope | None = None,
    ) -> AgentRunEvent: ...

    async def append_message_once(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        extension: EventExtensionEnvelope | None = None,
    ) -> AgentRunEvent: ...

    async def append_execution_input_once(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
    ) -> AgentRunEvent: ...

    async def list_for_run(
        self,
        context: UserContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]: ...

    async def get_message_for_run(
        self,
        context: UserContext,
        run_id: UUID,
        role: ConversationRole,
    ) -> AgentRunEvent | None: ...

    async def get_execution_input_for_run(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRunEvent | None: ...

    async def list_messages_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> list[AgentRunEvent]: ...

    async def list_message_page_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> tuple[list[AgentRunEvent], UUID | None]: ...
