from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fake_runtime import fake_executor_factory

from dayboard.agent.budget import ProviderBudgetExceeded, ProviderBudgetGuard, estimate_prompt_tokens
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService, _safe_error_message
from dayboard.config import Settings
from agent_platform.identity import TenantContext


class FakeConversationService:
    async def create_thread(self, context, *, thread_id=None, title=None):
        del context, title
        return SimpleNamespace(id=thread_id or uuid4())

    async def require_thread(self, context, thread_id):
        del context
        return SimpleNamespace(id=thread_id)

    async def append_message(self, context, **kwargs):
        del context, kwargs
        return None

    async def upsert_assistant_message(self, context, **kwargs):
        del context, kwargs
        return None

    async def update_summary(self, context, thread_id, summary):
        del context, thread_id, summary
        return None

    async def set_pending(self, context, **kwargs):
        del context, kwargs
        return SimpleNamespace(version=1, state_data={})

    async def clear_pending(self, context, thread_id):
        del context, thread_id
        return None


def test_estimate_prompt_tokens_is_nonzero() -> None:
    assert estimate_prompt_tokens("") == 1
    assert estimate_prompt_tokens("安排明天上午十点开会") >= 1


@pytest.mark.parametrize(
    ("budget_type", "expected"),
    [
        ("request", "请求有点频繁，请稍等一分钟后再试。"),
        ("token", "今天的 AI 使用额度已用完，请明天再试。"),
    ],
)
def test_provider_budget_errors_are_user_friendly(budget_type: str, expected: str) -> None:
    assert _safe_error_message(ProviderBudgetExceeded(budget_type, "test-limit")) == expected


def test_upstream_rate_limit_is_user_friendly() -> None:
    class UpstreamRateLimitError(RuntimeError):
        status_code = 429

    assert (
        _safe_error_message(UpstreamRateLimitError("Token limit exceeded"))
        == "AI 服务当前有点繁忙，请稍等几分钟后再试。"
    )


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


def test_provider_budget_reconciles_actual_tokens_once_above_reservation(
    tenant_context: TenantContext,
) -> None:
    guard = ProviderBudgetGuard(
        Settings(
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
            DAYBOARD_PROVIDER_BUDGET_REQUEST_LIMIT="10/minute",
            DAYBOARD_PROVIDER_BUDGET_TOKEN_LIMIT="20/minute",
        )
    )
    estimate = guard.estimate(input_text="安排会议")
    guard.check(context=tenant_context, model_name="openai:gpt-test", estimate=estimate)

    charged = guard.reconcile_actual(
        context=tenant_context,
        model_name="openai:gpt-test",
        estimate=estimate,
        actual_tokens=20,
    )

    assert charged == 20 - estimate.token_units
    with pytest.raises(ProviderBudgetExceeded) as exc_info:
        guard.check(context=tenant_context, model_name="openai:gpt-test", estimate=estimate)
    assert exc_info.value.budget_type == "token"


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
                del context, input_message
                return SimpleNamespace(id="fake-run", thread_id=thread_id)

        async def get_run(self, context, run_id):
            del context
            return SimpleNamespace(id=run_id, thread_id=uuid4(), status="queued")

        async def mark_running(self, context, run):
            del context
            return run

        async def mark_needs_clarification(
            self, context, run, *, question, event_metadata=None
        ):
            result = run
            del context, question, run, event_metadata
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

        async def rollback(self) -> None:
            return None

    monkeypatch.setattr(
        "dayboard.app.commands.build_run_service",
        lambda session: FakeRunService(session),
    )

    service = CommandService(
        FakeSession(),
        settings=guard.settings,
        budget_guard=guard,
            executor_factory=fake_executor_factory(fake_invoker),
            conversation_service=FakeConversationService(),
    )

    first = CommandRequest(message="安排明天开会")
    first_run_id = await service.create_command_run(tenant_context, first)
    await service.execute_command_run(tenant_context, first, first_run_id)

    with pytest.raises(ProviderBudgetExceeded):
        second = CommandRequest(message="安排后天开会")
        second_run_id = await service.create_command_run(tenant_context, second)
        await service.execute_command_run(tenant_context, second, second_run_id)
