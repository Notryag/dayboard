from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from north import RuntimeEvent
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.config import Settings
from dayboard.context import TenantContext
from dayboard.db.provider_usage_repository import ProviderUsageRepository


async def test_command_service_records_provider_usage(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async def fake_invoker(**kwargs):
        sink = kwargs["event_sink"]
        await sink(
            RuntimeEvent(
                "model.completed",
                "model",
                metadata={
                    "call_id": "call-1",
                    "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
                },
            )
        )
        await sink(
            RuntimeEvent(
                "model.completed",
                "model",
                metadata={
                    "call_id": "call-2",
                    "usage": {"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
                },
            )
        )
        return {
            "messages": [
                HumanMessage(content="安排会议"),
                AIMessage(
                    content="调用工具",
                    usage_metadata={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
                ),
                AIMessage(
                    content="会议已创建",
                    usage_metadata={"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
                ),
            ]
        }

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        invoker=fake_invoker,
    )

    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, request, run_id)
    records = await ProviderUsageRepository(db_session).list_for_run(
        tenant_context,
        run_id,
    )

    assert len(records) == 1
    assert records[0].provider == "openai"
    assert records[0].model == "openai:gpt-test"
    assert records[0].input_tokens == 50
    assert records[0].output_tokens == 13
    assert records[0].total_tokens == 63
    assert len(records[0].usage_metadata["calls"]) == 2


async def test_command_service_does_not_invent_missing_provider_usage(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async def fake_invoker(**kwargs):
        del kwargs
        return {"messages": [AIMessage(content="完成")]}

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        invoker=fake_invoker,
    )

    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, request, run_id)

    assert await ProviderUsageRepository(db_session).list_for_run(tenant_context, run_id) == []
