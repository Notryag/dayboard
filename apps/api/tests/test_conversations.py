from __future__ import annotations

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
