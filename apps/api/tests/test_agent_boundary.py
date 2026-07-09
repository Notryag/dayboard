from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest

from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.app.commands import CommandService
from dayboard.config import Settings
from dayboard.context import TenantContext
from dayboard.agent.factory import build_dayboard_agent


class FakeCommandService:
    async def handle_command(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        del context
        return CommandResponse(
            run_id="fake-run",
            status="needs_clarification",
            message=request.message,
            clarification_question="fake question",
        )


async def test_command_route_can_override_service_for_tests(
    tenant_context: TenantContext,
) -> None:
    service = FakeCommandService()

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


async def test_command_service_maps_north_clarification_result_to_run(
    tenant_context: TenantContext,
    monkeypatch,
) -> None:
    built = {}
    recorded_events = []

    class FakeRunService:
        def __init__(self, session) -> None:
            self.session = session

        async def create_run(self, context, *, input_message, thread_id=None):
            del context, input_message, thread_id
            return SimpleNamespace(id=uuid4())

        async def mark_running(self, context, run):
            del context
            return run

        async def mark_needs_clarification(self, context, run, *, question):
            result = run
            del context, run
            recorded_events.append(("clarification_requested", question))
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

    def fake_build_dayboard_agent(*args, **kwargs):
        built["run_id"] = kwargs["run_id"]
        built["context"] = kwargs["context"]
        return {"agent": "fake"}

    async def fake_invoker(**kwargs):
        assert kwargs["agent_factory"]() == {"agent": "fake"}
        return {"thread_data": {"clarification": {"question": "几点开始？"}}, "messages": []}

    monkeypatch.setattr("dayboard.app.commands.build_dayboard_agent", fake_build_dayboard_agent)
    service = CommandService(
        FakeSession(),
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        invoker=fake_invoker,
    )

    response = await service.handle_command(tenant_context, CommandRequest(message="安排会议"))

    assert response.status == "needs_clarification"
    assert response.clarification_question == "几点开始？"
    assert built["context"] == tenant_context
    assert str(built["run_id"]) == response.run_id
    assert recorded_events[-1] == ("clarification_requested", "几点开始？")


async def test_command_service_logs_and_marks_failed_run(
    tenant_context: TenantContext,
    monkeypatch,
    caplog,
) -> None:
    recorded_failures = []

    class FakeRunService:
        def __init__(self, session) -> None:
            self.session = session

        async def create_run(self, context, *, input_message, thread_id=None):
            del context, input_message, thread_id
            return SimpleNamespace(id=uuid4())

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
            del context, run
            recorded_failures.append((error_type, error_message))
            return result

    class FakeSession:
        async def commit(self) -> None:
            return None

    async def failing_invoker(**kwargs):
        del kwargs
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("dayboard.app.commands.AgentRunService", FakeRunService)
    service = CommandService(
        FakeSession(),
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        invoker=failing_invoker,
    )

    with caplog.at_level(logging.ERROR, logger="dayboard.app.commands"):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await service.handle_command(tenant_context, CommandRequest(message="安排会议"))

    assert recorded_failures == [("RuntimeError", "provider unavailable")]
    assert "dayboard.command.failed" in caplog.text
