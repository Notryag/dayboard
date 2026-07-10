from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.app.conversations import ConversationService
from dayboard.config import Settings
from dayboard.context import TenantContext


async def test_two_runs_persist_complete_thread_history(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    invoked_threads: list[str] = []
    responses = iter(["已经安排。", "已经改好。"])

    async def fake_invoker(**kwargs):
        invoked_threads.append(kwargs["config"]["configurable"]["thread_id"])
        return {"messages": [AIMessage(content=next(responses))]}

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        invoker=fake_invoker,
    )
    first_request = CommandRequest(message="明天八点开会")
    first = await service.create_or_get_command_run(tenant_context, first_request)
    await service.execute_command_run(tenant_context, first_request, first.run_id)
    second_request = CommandRequest(message="改到后天")
    second = await service.create_or_get_command_run(
        tenant_context,
        second_request,
        thread_id=first.thread_id,
    )
    await service.execute_command_run(tenant_context, second_request, second.run_id)

    messages = await ConversationService(db_session).list_messages(
        tenant_context, first.thread_id
    )

    assert second.thread_id == first.thread_id
    assert invoked_threads == [str(first.thread_id), str(first.thread_id)]
    assert [(message.role.value, message.content) for message in messages] == [
        ("user", "明天八点开会"),
        ("assistant", "已经安排。"),
        ("user", "改到后天"),
        ("assistant", "已经改好。"),
    ]


async def test_pending_clarification_state_is_versioned_and_clearable(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = ConversationService(db_session)
    thread = await service.create_thread(tenant_context)
    run_id = uuid4()

    pending = await service.set_pending_clarification(
        tenant_context,
        thread_id=thread.id,
        run_id=run_id,
        question="你指的是 8 点还是 10 点的会议？",
    )
    await db_session.commit()
    loaded = await service.get_state(tenant_context, thread.id)
    cleared = await service.clear_pending(tenant_context, thread.id)
    await db_session.commit()

    assert loaded == pending
    assert pending.pending_action == "clarification"
    assert pending.state_data == {"source_run_id": str(run_id)}
    assert pending.expires_at is not None
    assert pending.expires_at > datetime.now(UTC)
    assert cleared is not None
    assert cleared.pending_action is None
    assert cleared.pending_question is None
    assert cleared.state_data == {}
    assert cleared.version == pending.version + 1


async def test_conversation_state_is_owner_scoped(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = ConversationService(db_session)
    thread = await service.create_thread(tenant_context)
    await service.set_pending_clarification(
        tenant_context,
        thread_id=thread.id,
        run_id=uuid4(),
        question="哪一个？",
    )
    await db_session.commit()
    other_context = TenantContext(
        tenant_id=tenant_context.tenant_id,
        user_id=uuid4(),
        timezone=tenant_context.timezone,
        locale=tenant_context.locale,
    )

    try:
        await service.get_state(other_context, thread.id)
    except LookupError:
        pass
    else:
        raise AssertionError("Another owner must not read conversation state")
