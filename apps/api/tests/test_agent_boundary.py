from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest

from dayboard.agent.factory import build_dayboard_agent
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.config import Settings
from dayboard.context import TenantContext


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

    async def update_summary(self, context, thread_id, summary):
        del context, thread_id, summary
        return None


def test_build_dayboard_agent_uses_configured_model_name(monkeypatch) -> None:
    captured = {}

    def fake_build_agent(config, *, tools=None, checkpointer=None, compaction_hooks=None):
        del checkpointer, compaction_hooks
        captured["model_name"] = config.model_name
        captured["system_prompt"] = config.system_prompt
        captured["tools"] = tools
        captured["summarization_enabled"] = config.summarization_enabled
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)

    agent = build_dayboard_agent(Settings(APP_MODEL_NAME="openai:gpt-test"), tools=["tool"])

    assert agent == {"agent": "fake"}
    assert captured["model_name"] == "openai:gpt-test"
    assert "scheduling assistant" in captured["system_prompt"]
    assert captured["tools"][0] == "tool"
    assert captured["tools"][1].name == "ask_clarification"
    assert captured["summarization_enabled"] is True


def test_build_dayboard_agent_does_not_duplicate_clarification_tool(monkeypatch) -> None:
    captured = {}

    def fake_build_agent(config, *, tools=None, checkpointer=None, compaction_hooks=None):
        del checkpointer, compaction_hooks
        del config
        captured["tools"] = tools
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)
    from north.tools.builtin import ask_clarification

    build_dayboard_agent(
        Settings(APP_MODEL_NAME="openai:gpt-test"),
        tools=[ask_clarification],
    )

    assert [tool.name for tool in captured["tools"]] == ["ask_clarification"]


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
                del context, input_message
                return SimpleNamespace(id=uuid4(), thread_id=thread_id)

        async def get_run_row(self, context, run_id):
            del context
            return SimpleNamespace(id=run_id, thread_id=uuid4(), status="queued")

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

        async def rollback(self) -> None:
            return None

    monkeypatch.setattr("dayboard.app.commands.AgentRunService", FakeRunService)

    def fake_build_dayboard_agent(*args, **kwargs):
        built["run_id"] = kwargs["run_id"]
        built["context"] = kwargs["context"]
        built["compaction_hooks"] = kwargs["compaction_hooks"]
        return {"agent": "fake"}

    async def fake_invoker(**kwargs):
        assert kwargs["agent_factory"]() == {"agent": "fake"}
        assert kwargs["config"]["configurable"]["thread_id"] != str(run_id)
        assert kwargs["config"]["configurable"]["checkpoint_ns"] == "dayboard"
        assert len(built["compaction_hooks"]) == 1
        return {"thread_data": {"clarification": {"question": "几点开始？"}}, "messages": []}

    monkeypatch.setattr("dayboard.app.commands.build_dayboard_agent", fake_build_dayboard_agent)
    service = CommandService(
        FakeSession(),
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
            invoker=fake_invoker,
            conversation_service=FakeConversationService(),
    )

    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, request, run_id)

    assert built["context"] == tenant_context
    assert built["run_id"] == run_id
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
                del context, input_message
                return SimpleNamespace(id=uuid4(), thread_id=thread_id)

        async def get_run_row(self, context, run_id):
            del context
            return SimpleNamespace(id=run_id, thread_id=uuid4(), status="queued")

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

        async def rollback(self) -> None:
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
            conversation_service=FakeConversationService(),
    )

    with caplog.at_level(logging.ERROR, logger="dayboard.app.commands"):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            request = CommandRequest(message="安排会议")
            run_id = await service.create_command_run(tenant_context, request)
            await service.execute_command_run(tenant_context, request, run_id)

    assert recorded_failures == [("RuntimeError", "provider unavailable")]
    assert "dayboard.command.failed" in caplog.text
