"""Conversation persistence use cases independent of product and storage."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from agent_platform.core.conversations import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    ConversationState,
    ConversationThread,
    ConversationThreadStatus,
)
from agent_platform.core.errors import (
    ConversationArchivedError,
    ConversationNotFoundError,
    InteractionConflictError,
)
from agent_platform.core.identity import UserContext
from agent_platform.core.interactions import PendingInteraction
from agent_platform.core.presentations import PresentationEnvelope
from agent_platform.core.events import EventExtensionEnvelope
from agent_platform.core.runs import AgentRunEvent
from agent_platform.ports.unit_of_work import ConversationUnitOfWork


class ConversationService:
    def __init__(self, unit_of_work: ConversationUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.threads = unit_of_work.threads
        self.events = unit_of_work.events
        self.states = unit_of_work.states

    async def create_thread(
        self,
        context: UserContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread:
        return await self.threads.create(context, thread_id=thread_id, title=title)

    async def require_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationThread:
        thread = await self.threads.get(context, thread_id)
        if thread is None:
            raise ConversationNotFoundError("Conversation thread not found")
        return thread

    async def get_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationThread | None:
        return await self.threads.get(context, thread_id)

    async def require_active_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationThread:
        thread = await self.require_thread(context, thread_id)
        if thread.status != ConversationThreadStatus.active:
            raise ConversationArchivedError("Conversation thread is archived")
        return thread

    async def get_or_create_primary_thread(self, context: UserContext) -> ConversationThread:
        return await self.threads.get_or_create_primary(context)

    async def append_message(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        presentation: PresentationEnvelope | None = None,
    ) -> ConversationMessage:
        event = await self.events.append_message_once(
            context,
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            content=content,
            extension=_presentation_extension(presentation),
        )
        return _message_from_event(event)

    async def list_messages(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> list[ConversationMessage]:
        await self.require_thread(context, thread_id)
        return [
            _message_from_event(event)
            for event in await self.events.list_messages_for_thread(context, thread_id)
        ]

    async def list_message_page(
        self,
        context: UserContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> ConversationMessagePage:
        await self.require_thread(context, thread_id)
        events, next_cursor = await self.events.list_message_page_for_thread(
            context,
            thread_id,
            before=before,
            limit=limit,
        )
        return ConversationMessagePage(
            items=[_message_from_event(event) for event in events],
            next_cursor=next_cursor,
        )

    async def upsert_assistant_message(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
        presentation: PresentationEnvelope | None,
    ) -> ConversationMessage:
        event = await self.events.append_message_once(
            context,
            thread_id=thread_id,
            run_id=run_id,
            role=ConversationRole.assistant,
            content=content,
            extension=_presentation_extension(presentation),
        )
        return _message_from_event(event)

    async def get_assistant_message_for_run(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> ConversationMessage | None:
        event = await self.events.get_message_for_run(
            context, run_id, ConversationRole.assistant
        )
        return _message_from_event(event) if event is not None else None

    async def get_human_message_for_run(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> ConversationMessage | None:
        event = await self.events.get_message_for_run(context, run_id, ConversationRole.user)
        return _message_from_event(event) if event is not None else None

    async def get_execution_input_for_run(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> str | None:
        event = await self.events.get_execution_input_for_run(context, run_id)
        if event is not None:
            return event.content
        message = await self.get_human_message_for_run(context, run_id)
        return message.content if message is not None else None

    async def update_summary(
        self,
        context: UserContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread:
        thread = await self.threads.update_summary(context, thread_id, summary)
        if thread is None:
            raise ConversationNotFoundError("Conversation thread not found")
        return thread

    async def get_state(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        await self.require_thread(context, thread_id)
        return await self.states.get(context, thread_id)

    async def set_interaction(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        interaction: PendingInteraction,
        expires_at: datetime,
    ) -> ConversationState:
        await self.require_thread(context, thread_id)
        return await self.states.set_interaction(
            context,
            thread_id=thread_id,
            interaction=interaction,
            expires_at=expires_at,
        )

    async def consume_interaction(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        expected_version: int,
    ) -> ConversationState:
        state = await self.states.consume_interaction(
            context,
            thread_id=thread_id,
            expected_version=expected_version,
            consumed_at=datetime.now(UTC),
        )
        if state is None:
            raise InteractionConflictError(
                "Interaction is missing, expired, or changed; refresh and try again"
            )
        return state

    async def clear_interaction(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        return await self.states.clear_interaction(context, thread_id)


def _presentation_extension(
    presentation: PresentationEnvelope | None,
) -> EventExtensionEnvelope | None:
    if presentation is None:
        return None
    return EventExtensionEnvelope(
        kind=presentation.kind,
        schema_version=presentation.schema_version,
        payload=presentation.payload,
    )


def _message_from_event(event: AgentRunEvent) -> ConversationMessage:
    role = {
        "message.human": ConversationRole.user,
        "message.ai": ConversationRole.assistant,
    }.get(event.event_type)
    if role is None or event.category.value != "message" or event.content is None:
        raise ValueError(f"Event {event.id} is not a displayable conversation message")
    presentation = None
    if event.extension is not None:
        presentation = PresentationEnvelope(
            kind=event.extension.kind,
            schema_version=event.extension.schema_version,
            payload=event.extension.payload,
        )
    return ConversationMessage(
        id=event.id,
        thread_id=event.thread_id,
        run_id=event.run_id,
        role=role,
        content=event.content,
        presentation=presentation,
        created_at=event.created_at,
    )
