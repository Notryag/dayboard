from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.app.commands import CommandService
from dayboard.config import Settings
from dayboard.context import TenantContext
from dayboard.agent.executor import NorthCommandExecutor
from dayboard.agent.factory import build_dayboard_agent
from dayboard.app.runs import AgentRunService


class FakeExecutor:
    async def execute(
        self,
        session: AsyncSession,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        del session, context
        return CommandResponse(
            run_id="fake-run",
            status="needs_clarification",
            message=request.message,
            clarification_question="fake question",
        )


async def test_command_service_accepts_replaceable_executor(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = CommandService(db_session, executor=FakeExecutor())

    response = await service.handle_command(
        tenant_context,
        CommandRequest(message="安排明天上午的事情"),
    )

    assert response.run_id == "fake-run"
    assert response.clarification_question == "fake question"


def test_command_service_defaults_to_north_executor(db_session: AsyncSession) -> None:
    service = CommandService(db_session)

    assert isinstance(service.executor, NorthCommandExecutor)


def test_build_dayboard_agent_uses_configured_model_name(monkeypatch) -> None:
    captured = {}

    def fake_build_agent(config, *, tools=None):
        captured["model_name"] = config.model_name
        captured["system_prompt"] = config.system_prompt
        captured["tools"] = tools
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)

    agent = build_dayboard_agent(Settings(APP_MODEL_NAME="openai:gpt-test"), tools=["tool"])

    assert agent == {"agent": "fake"}
    assert captured["model_name"] == "openai:gpt-test"
    assert "scheduling assistant" in captured["system_prompt"]
    assert captured["tools"] == ["tool"]


async def test_north_executor_maps_clarification_result_to_run(
    db_session: AsyncSession,
    tenant_context: TenantContext,
    monkeypatch,
) -> None:
    built = {}

    def fake_build_dayboard_agent(*args, **kwargs):
        built["run_id"] = kwargs["run_id"]
        built["context"] = kwargs["context"]
        built["session"] = kwargs["session"]
        return {"agent": "fake"}

    async def fake_invoker(**kwargs):
        assert kwargs["agent_factory"]() == {"agent": "fake"}
        return {"thread_data": {"clarification": {"question": "几点开始？"}}, "messages": []}

    monkeypatch.setattr("dayboard.agent.executor.build_dayboard_agent", fake_build_dayboard_agent)
    executor = NorthCommandExecutor(
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        invoker=fake_invoker,
    )

    response = await executor.execute(db_session, tenant_context, CommandRequest(message="安排会议"))

    assert response.status == "needs_clarification"
    assert response.clarification_question == "几点开始？"
    assert built["context"] == tenant_context
    assert built["session"] is db_session
    assert str(built["run_id"]) == response.run_id

    runs = AgentRunService(db_session)
    events = await runs.list_events(tenant_context, response.run_id)
    assert events[-1].event_type == "clarification_requested"
