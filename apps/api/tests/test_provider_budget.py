from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fake_runtime import fake_executor_factory

from dayboard.agent.budget import ProviderBudgetExceeded, ProviderBudgetGuard, estimate_prompt_tokens
from dayboard.app.run_execution import DayboardRunExecutionDriver
from dayboard.app.run_result_projection import safe_error_message
from dayboard.config import Settings
from agent_platform.core import AgentRun, AgentRunStatus, TenantContext


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
    assert safe_error_message(ProviderBudgetExceeded(budget_type, "test-limit")) == expected


def test_upstream_rate_limit_is_user_friendly() -> None:
    class UpstreamRateLimitError(RuntimeError):
        status_code = 429

    assert (
        safe_error_message(UpstreamRateLimitError("Token limit exceeded"))
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

    async def complete(outcome) -> None:
        del outcome

    async def fail(failure) -> bool:
        del failure
        return True

    def build_driver() -> DayboardRunExecutionDriver:
        return DayboardRunExecutionDriver(
            SimpleNamespace(),
            settings=guard.settings,
            unit_of_work=SimpleNamespace(),
            conversations=SimpleNamespace(),
            runs=SimpleNamespace(),
            budget_guard=guard,
            executor_factory=fake_executor_factory(fake_invoker),
        )

    def build_run(message: str) -> AgentRun:
        now = datetime.now(UTC)
        return AgentRun(
            id=uuid4(),
            tenant_id=tenant_context.tenant_id,
            owner_user_id=tenant_context.user_id,
            thread_id=uuid4(),
            status=AgentRunStatus.running,
            input_message=message,
            result_message=None,
            created_at=now,
            updated_at=now,
        )

    await build_driver().execute(
        tenant_context,
        build_run("安排明天开会"),
        on_completed=complete,
        on_failed=fail,
    )

    with pytest.raises(ProviderBudgetExceeded):
        await build_driver().execute(
            tenant_context,
            build_run("安排后天开会"),
            on_completed=complete,
            on_failed=fail,
        )
