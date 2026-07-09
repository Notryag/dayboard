from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent.budget import ProviderBudgetExceeded, ProviderBudgetGuard, estimate_prompt_tokens
from dayboard.agent.executor import NorthCommandExecutor
from dayboard.app.command_schemas import CommandRequest
from dayboard.config import Settings
from dayboard.context import TenantContext


def test_estimate_prompt_tokens_is_nonzero() -> None:
    assert estimate_prompt_tokens("") == 1
    assert estimate_prompt_tokens("安排明天上午十点开会") >= 1


def test_provider_budget_guard_rejects_request_over_limit(tenant_context: TenantContext) -> None:
    guard = ProviderBudgetGuard(
        Settings(
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
            DAYBOARD_PROVIDER_BUDGET_REQUEST_LIMIT="1/minute",
            DAYBOARD_PROVIDER_BUDGET_TOKEN_LIMIT="1000/minute",
        )
    )

    estimate = guard.estimate(input_text="安排明天上午十点开会")
    guard.check(context=tenant_context, model_name="openai:gpt-test", estimate=estimate)

    with pytest.raises(ProviderBudgetExceeded) as exc_info:
        guard.check(context=tenant_context, model_name="openai:gpt-test", estimate=estimate)

    assert exc_info.value.budget_type == "request"


async def test_north_command_executor_checks_budget_before_model_execution(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    guard = ProviderBudgetGuard(
        Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
            DAYBOARD_PROVIDER_BUDGET_REQUEST_LIMIT="1/minute",
            DAYBOARD_PROVIDER_BUDGET_TOKEN_LIMIT="1000/minute",
        )
    )
    async def fake_invoker(**kwargs):
        del kwargs
        return {"messages": [{"content": "ok"}]}

    executor = NorthCommandExecutor(settings=guard.settings, budget_guard=guard, invoker=fake_invoker)

    response = await executor.execute(db_session, tenant_context, CommandRequest(message="安排明天开会"))

    assert response.status == "completed"

    with pytest.raises(ProviderBudgetExceeded):
        await executor.execute(db_session, tenant_context, CommandRequest(message="安排后天开会"))
