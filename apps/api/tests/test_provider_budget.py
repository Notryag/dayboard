from __future__ import annotations

from types import SimpleNamespace

import pytest

from dayboard.agent.budget import ProviderBudgetExceeded, ProviderBudgetGuard, estimate_prompt_tokens
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
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


async def test_command_service_checks_budget_before_model_execution(
    tenant_context: TenantContext,
    monkeypatch,
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

    class FakeRunService:
        def __init__(self, session) -> None:
            self.session = session

        async def create_run(self, context, *, input_message, thread_id=None):
            del context, input_message, thread_id
            return SimpleNamespace(id="fake-run")

        async def get_run_row(self, context, run_id):
            del context
            return SimpleNamespace(id=run_id, status="queued")

        async def mark_running(self, context, run):
            del context
            return run

        async def mark_needs_clarification(self, context, run, *, question):
            result = run
            del context, question, run
            return result

        async def mark_completed(self, context, run, *, result_message, event_metadata=None):
            result = run
            del context, result_message, event_metadata, run
            return result

        async def mark_failed(self, context, run, *, error_type, error_message):
            result = run
            del context, error_type, error_message, run
            return result

    class FakeSession:
        async def commit(self) -> None:
            return None

    monkeypatch.setattr("dayboard.app.commands.AgentRunService", FakeRunService)

    service = CommandService(
        FakeSession(),
        settings=guard.settings,
        budget_guard=guard,
        invoker=fake_invoker,
    )

    first = CommandRequest(message="安排明天开会")
    first_run_id = await service.create_command_run(tenant_context, first)
    await service.execute_command_run(tenant_context, first, first_run_id)

    with pytest.raises(ProviderBudgetExceeded):
        second = CommandRequest(message="安排后天开会")
        second_run_id = await service.create_command_run(tenant_context, second)
        await service.execute_command_run(tenant_context, second, second_run_id)
