from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from agent_platform.application import RunExecutionCoordinator
from agent_platform.core import (
    AgentRun,
    AgentRunEvent,
    AgentRunEventCategory,
    AgentRunStatus,
    ConversationRole,
    ConversationState,
    ConversationThread,
    ConversationThreadStatus,
    PendingInteraction,
    PresentationEnvelope,
    RunExecutionFailure,
    RunExecutionOutcome,
    RunExecutionOutcomeKind,
    UserContext,
)
from agent_platform.ports.execution import RunCompletionCallback, RunFailureCallback


class MemoryRunStore:
    def __init__(self, run: AgentRun) -> None:
        self.record = run

    async def get(self, context: UserContext, run_id: UUID) -> AgentRun | None:
        if (
            run_id != self.record.id
            or context.user_id != self.record.user_id
        ):
            return None
        return self.record

    async def get_for_update(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRun | None:
        return await self.get(context, run_id)

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
    ) -> AgentRun | None:
        current = await self.get(context, run_id)
        if current is None or current.status not in from_statuses:
            return None
        self.record = current.model_copy(
            update={
                "status": status,
                "error": error if error is not None else current.error,
                "message_count": (
                    message_count if message_count is not None else current.message_count
                ),
                "first_human_message": (
                    first_human_message
                    if first_human_message is not None
                    else current.first_human_message
                ),
                "last_ai_message": (
                    last_ai_message
                    if last_ai_message is not None
                    else current.last_ai_message
                ),
                "updated_at": datetime.now(UTC),
            }
        )
        return self.record


class MemoryRunEventStore:
    def __init__(self) -> None:
        self.records: list[AgentRunEvent] = []

    async def append(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        event_type: str,
        category: AgentRunEventCategory,
        content: str | None = None,
        extension=None,
    ) -> AgentRunEvent:
        event = AgentRunEvent(
            id=uuid4(),
            thread_id=thread_id,
            run_id=run_id,
            seq=len(self.records) + 1,
            event_type=event_type,
            category=category,
            content=content,
            extension=extension,
            created_at=datetime.now(UTC),
        )
        self.records.append(event)
        return event

    async def append_message_once(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        extension=None,
    ) -> AgentRunEvent:
        event_type = {
            ConversationRole.user: "message.human",
            ConversationRole.assistant: "message.ai",
        }[role]
        existing = await self.get_message_for_run(context, run_id, role)
        if existing is not None:
            if role == ConversationRole.assistant:
                updates = {"extension": extension}
                if content:
                    updates["content"] = content
                updated = existing.model_copy(update=updates)
                self.records[self.records.index(existing)] = updated
                return updated
            return existing
        return await self.append(
            context,
            thread_id=thread_id,
            run_id=run_id,
            event_type=event_type,
            category=AgentRunEventCategory.message,
            content=content,
            extension=extension,
        )

    async def get_message_for_run(
        self,
        context: UserContext,
        run_id: UUID,
        role: ConversationRole,
    ) -> AgentRunEvent | None:
        del context
        event_type = {
            ConversationRole.user: "message.human",
            ConversationRole.assistant: "message.ai",
        }[role]
        return next(
            (
                event
                for event in self.records
                if event.run_id == run_id and event.event_type == event_type
            ),
            None,
        )

    async def get_execution_input_for_run(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRunEvent | None:
        del context, run_id
        return None

    async def list_messages_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> list[AgentRunEvent]:
        del context
        return [
            event
            for event in self.records
            if event.thread_id == thread_id
            and event.category == AgentRunEventCategory.message
        ]

    async def list_message_page_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> tuple[list[AgentRunEvent], UUID | None]:
        messages = await self.list_messages_for_thread(context, thread_id)
        if before is not None:
            cursor = next(index for index, item in enumerate(messages) if item.id == before)
            messages = messages[:cursor]
        page = messages[-limit:]
        next_cursor = page[0].id if len(messages) > len(page) else None
        return page, next_cursor


class MemoryThreadStore:
    def __init__(self, thread: ConversationThread) -> None:
        self.record = thread

    async def get(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationThread | None:
        if (
            thread_id != self.record.id
            or context.user_id != self.record.user_id
        ):
            return None
        return self.record


class MemoryStateStore:
    def __init__(self) -> None:
        self.record: ConversationState | None = None

    async def set_interaction(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        interaction: PendingInteraction,
        expires_at: datetime,
    ) -> ConversationState:
        del context
        self.record = ConversationState(
            thread_id=thread_id,
            interaction=interaction,
            version=(self.record.version + 1) if self.record is not None else 1,
            expires_at=expires_at,
            updated_at=datetime.now(UTC),
        )
        return self.record

    async def clear_interaction(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        del context
        if self.record is None:
            return None
        self.record = self.record.model_copy(
            update={
                "interaction": None,
                "version": self.record.version + 1,
                "expires_at": None,
                "updated_at": datetime.now(UTC),
            }
        )
        assert self.record.thread_id == thread_id
        return self.record


class MemoryPlatformUnitOfWork:
    def __init__(self, context: UserContext, *, status: AgentRunStatus) -> None:
        now = datetime.now(UTC)
        thread = ConversationThread(
            id=uuid4(),
            user_id=context.user_id,
            is_primary=True,
            title=None,
            status=ConversationThreadStatus.active,
            summary=None,
            created_at=now,
            updated_at=now,
        )
        run = AgentRun(
            id=uuid4(),
            user_id=context.user_id,
            thread_id=thread.id,
            status=status,
            message_count=1,
            first_human_message="安排会议",
            created_at=now,
            updated_at=now,
        )
        self.runs = MemoryRunStore(run)
        self.events = MemoryRunEventStore()
        self.events.records.append(
            AgentRunEvent(
                id=uuid4(),
                thread_id=thread.id,
                run_id=run.id,
                seq=1,
                event_type="message.human",
                category=AgentRunEventCategory.message,
                content="安排会议",
                created_at=now,
            )
        )
        self.threads = MemoryThreadStore(thread)
        self.states = MemoryStateStore()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


ExecuteCallback = Callable[
    [AgentRun, RunCompletionCallback, RunFailureCallback],
    Awaitable[None],
]


class CallbackDriver:
    def __init__(self, callback: ExecuteCallback) -> None:
        self.callback = callback
        self.seen_run: AgentRun | None = None

    async def execute(
        self,
        context: UserContext,
        run: AgentRun,
        input_message: str,
        *,
        on_completed: RunCompletionCallback,
        on_failed: RunFailureCallback,
    ) -> None:
        del context
        assert input_message == "安排会议"
        self.seen_run = run
        await self.callback(run, on_completed, on_failed)

    def failure_from_exception(self, exc: Exception) -> RunExecutionFailure:
        return RunExecutionFailure(
            error_type=type(exc).__name__,
            error_message=str(exc) or type(exc).__name__,
        )


def build_context() -> UserContext:
    return UserContext(
        user_id=uuid4(),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )


def test_completed_run_and_assistant_message_share_terminal_commit() -> None:
    async def scenario() -> None:
        context = build_context()
        unit_of_work = MemoryPlatformUnitOfWork(context, status=AgentRunStatus.queued)
        presentation = PresentationEnvelope(
            kind="example.results",
            schema_version=1,
            payload={"items": []},
        )

        async def complete(run, on_completed, on_failed) -> None:
            del run, on_failed
            await on_completed(
                RunExecutionOutcome(
                    kind=RunExecutionOutcomeKind.completed,
                    result_message="已安排",
                    presentation=presentation,
                )
            )

        driver = CallbackDriver(complete)
        await RunExecutionCoordinator(unit_of_work).execute(
            context,
            unit_of_work.runs.record.id,
            driver,
        )

        assert driver.seen_run is not None
        assert driver.seen_run.status == AgentRunStatus.running
        assert unit_of_work.runs.record.status == AgentRunStatus.completed
        assistant = await unit_of_work.events.get_message_for_run(
            context,
            unit_of_work.runs.record.id,
            ConversationRole.assistant,
        )
        assert assistant is not None
        assert assistant.content == "已安排"
        assert assistant.extension is not None
        assert assistant.extension.payload == presentation.payload
        assert [event.event_type for event in unit_of_work.events.records] == [
            "message.human",
            "run.started",
            "run.completed",
            "message.ai",
        ]
        assert unit_of_work.commits == 2

    asyncio.run(scenario())


def test_interaction_outcome_persists_versioned_platform_event() -> None:
    async def scenario() -> None:
        context = build_context()
        unit_of_work = MemoryPlatformUnitOfWork(context, status=AgentRunStatus.running)
        interaction = PendingInteraction(
            interaction_type="example.choice",
            schema_version=1,
            source_run_id=unit_of_work.runs.record.id,
            prompt="选择哪一个？",
            payload={"options": ["a", "b"]},
        )
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        async def request_interaction(run, on_completed, on_failed) -> None:
            del run, on_failed
            await on_completed(
                RunExecutionOutcome(
                    kind=RunExecutionOutcomeKind.needs_interaction,
                    result_message=interaction.prompt,
                    interaction=interaction,
                    interaction_expires_at=expires_at,
                )
            )

        await RunExecutionCoordinator(unit_of_work).execute(
            context,
            unit_of_work.runs.record.id,
            CallbackDriver(request_interaction),
        )

        assert unit_of_work.runs.record.status == AgentRunStatus.needs_clarification
        assert unit_of_work.states.record is not None
        assert unit_of_work.states.record.interaction == interaction
        event = unit_of_work.events.records[-1]
        assert event.event_type == "message.ai"
        lifecycle_event = unit_of_work.events.records[-2]
        assert lifecycle_event.event_type == "run.needs_clarification"
        assert lifecycle_event.extension is not None
        assert lifecycle_event.extension.kind == "agent-platform.interaction-state"
        assert lifecycle_event.extension.schema_version == 1
        assert lifecycle_event.extension.payload == {"state_version": 1}
        assert unit_of_work.commits == 1

    asyncio.run(scenario())


def test_driver_failure_persists_terminal_failure_before_propagating() -> None:
    async def scenario() -> None:
        context = build_context()
        unit_of_work = MemoryPlatformUnitOfWork(context, status=AgentRunStatus.running)

        async def fail(run, on_completed, on_failed) -> None:
            del run, on_completed
            error = RuntimeError("provider unavailable")
            assert await on_failed(
                RunExecutionFailure(
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
            )
            raise error

        with pytest.raises(RuntimeError, match="provider unavailable"):
            await RunExecutionCoordinator(unit_of_work).execute(
                context,
                unit_of_work.runs.record.id,
                CallbackDriver(fail),
            )

        assert unit_of_work.runs.record.status == AgentRunStatus.failed
        assistant = await unit_of_work.events.get_message_for_run(
            context,
            unit_of_work.runs.record.id,
            ConversationRole.assistant,
        )
        assert assistant is not None
        assert assistant.content == "provider unavailable"
        assert unit_of_work.events.records[-2].event_type == "run.failed"
        assert unit_of_work.commits == 1

    asyncio.run(scenario())


def test_driver_returning_without_terminal_callback_is_failed() -> None:
    async def scenario() -> None:
        context = build_context()
        unit_of_work = MemoryPlatformUnitOfWork(context, status=AgentRunStatus.running)

        async def return_early(run, on_completed, on_failed) -> None:
            del run, on_completed, on_failed

        with pytest.raises(RuntimeError, match="without settling"):
            await RunExecutionCoordinator(unit_of_work).execute(
                context,
                unit_of_work.runs.record.id,
                CallbackDriver(return_early),
            )

        assert unit_of_work.runs.record.status == AgentRunStatus.failed
        assistant = await unit_of_work.events.get_message_for_run(
            context,
            unit_of_work.runs.record.id,
            ConversationRole.assistant,
        )
        assert assistant is not None
        assert assistant.content is not None
        assert "without settling" in assistant.content

    asyncio.run(scenario())


def test_terminal_race_does_not_overwrite_cancelled_run() -> None:
    async def scenario() -> None:
        context = build_context()
        unit_of_work = MemoryPlatformUnitOfWork(context, status=AgentRunStatus.running)

        async def complete_after_cancellation(run, on_completed, on_failed) -> None:
            del run, on_failed
            unit_of_work.runs.record = unit_of_work.runs.record.model_copy(
                update={"status": AgentRunStatus.cancelled}
            )
            await on_completed(
                RunExecutionOutcome(
                    kind=RunExecutionOutcomeKind.completed,
                    result_message="不应写入",
                )
            )

        with pytest.raises(asyncio.CancelledError):
            await RunExecutionCoordinator(unit_of_work).execute(
                context,
                unit_of_work.runs.record.id,
                CallbackDriver(complete_after_cancellation),
            )

        assert unit_of_work.runs.record.status == AgentRunStatus.cancelled
        assert await unit_of_work.events.get_message_for_run(
            context,
            unit_of_work.runs.record.id,
            ConversationRole.assistant,
        ) is None
        assert unit_of_work.commits == 0

    asyncio.run(scenario())
