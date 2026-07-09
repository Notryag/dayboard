from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.app.commands import CommandService
from dayboard.config import Settings
from dayboard.context import TenantContext
from dayboard.agent.factory import build_dayboard_agent


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
