from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fake_runtime import fake_executor_factory
from langchain_core.messages import AIMessage, ToolMessage

from dayboard.agent.factory import build_dayboard_agent
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService, _extract_clarification_state_data
from dayboard.config import Settings
from agent_platform.core import TenantContext


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


def test_clarification_state_uses_real_search_tool_candidates() -> None:
    result = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "search-1",
                        "name": "search_calendar_entries",
                        "args": {"title_query": "产品会议"},
                    }
                ],
            ),
            ToolMessage(
                name="search_calendar_entries",
                tool_call_id="search-1",
                content='[{"id":"entry-1","title":"产品会议","local_start":"2026-07-11T08:00"}]',
                artifact={
                    "type": "schedule_items_result",
                    "items": [
                        {
                            "kind": "calendar",
                            "value": {
                                "id": "entry-1",
                                "row_version": 4,
                                "title": "产品会议",
                                "start_time": "2026-07-11T00:00:00+00:00",
                                "timezone": "Asia/Shanghai",
                                "tenant_id": "must-not-persist",
                            },
                        }
                    ],
                },
            ),
        ]
    }

    state_data = _extract_clarification_state_data(result)

    assert state_data == {
        "intent": "select",
        "candidates": [
            {
                "key": "candidate_1",
                "id": "entry-1",
                "row_version": 4,
                "title": "产品会议",
                "start_time": "2026-07-11T00:00:00+00:00",
                "timezone": "Asia/Shanghai",
            }
        ],
        "interaction": {
            "type": "calendar_entry_choice",
            "options": [
                {
                    "key": "candidate_1",
                    "title": "产品会议",
                    "start_time": "2026-07-11T00:00:00+00:00",
                    "timezone": "Asia/Shanghai",
                }
            ],
        },
    }


def test_clarification_state_uses_agent_suggested_choices_without_search_results() -> None:
    state_data = _extract_clarification_state_data(
        {
            "thread_data": {
                "clarification": {
                    "status": "pending",
                    "question": "会议几点开始？",
                    "response_kind": "single_choice",
                    "options": ["09:00", "14:00", "其他时间"],
                }
            },
            "messages": [],
        }
    )

    assert state_data == {
        "candidates": [
            {"key": "candidate_1", "value": "09:00", "label": "09:00"},
            {"key": "candidate_2", "value": "14:00", "label": "14:00"},
            {"key": "candidate_3", "value": "其他时间", "label": "其他时间"},
        ],
        "interaction": {
            "type": "suggested_choice",
            "options": [
                {"key": "candidate_1", "label": "09:00"},
                {"key": "candidate_2", "label": "14:00"},
                {"key": "candidate_3", "label": "其他时间"},
            ],
        },
    }

def test_build_dayboard_agent_uses_configured_model_name(monkeypatch) -> None:
    captured = {}

    def fake_build_agent(
        config,
        *,
        tools=None,
        checkpointer=None,
        compaction_hooks=None,
        additional_middlewares=None,
    ):
        del checkpointer, compaction_hooks
        captured["model_name"] = config.model_name
        captured["model_headers"] = config.model_headers
        captured["model_options"] = config.model_options
        captured["system_prompt"] = config.system_prompt
        captured["tools"] = tools
        captured["additional_middlewares"] = additional_middlewares
        captured["summarization_enabled"] = config.summarization_enabled
        captured["summarization_summary_prompt"] = config.summarization_summary_prompt
        captured["summarization_normal_trigger_tokens"] = (
            config.summarization_normal_trigger_tokens
        )
        captured["summarization_emergency_trigger_tokens"] = (
            config.summarization_emergency_trigger_tokens
        )
        captured["summarization_message_ceiling"] = config.summarization_message_ceiling
        captured["summarization_target_tokens"] = config.summarization_target_tokens
        captured["summarization_min_growth_tokens"] = config.summarization_min_growth_tokens
        captured["summarization_max_emergency_compactions"] = (
            config.summarization_max_emergency_compactions
        )
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)

    agent = build_dayboard_agent(Settings(APP_MODEL_NAME="openai:gpt-test"), tools=["tool"])

    assert agent == {"agent": "fake"}
    assert captured["model_name"] == "openai:gpt-test"
    assert captured["model_headers"] == {}
    assert captured["model_options"] == {}
    assert "scheduling assistant" in captured["system_prompt"]
    assert captured["tools"][0] == "tool"
    assert captured["tools"][1].name == "ask_clarification"
    assert type(captured["additional_middlewares"][0]).__name__ == (
        "SchedulingToolBindingMiddleware"
    )
    assert captured["summarization_enabled"] is True
    assert captured["summarization_normal_trigger_tokens"] == 6000
    assert captured["summarization_emergency_trigger_tokens"] == 12000
    assert captured["summarization_message_ceiling"] == 60
    assert captured["summarization_target_tokens"] == 2000
    assert captured["summarization_min_growth_tokens"] == 3000
    assert captured["summarization_max_emergency_compactions"] == 2
    assert "{messages}" in captured["summarization_summary_prompt"]
    assert "no more than 250 words" in captured["summarization_summary_prompt"]
    assert len(captured["summarization_summary_prompt"]) < 800


def test_build_dayboard_agent_attaches_trusted_northgate_metadata(
    monkeypatch,
    tenant_context: TenantContext,
) -> None:
    captured = {}
    run_id = UUID("00000000-0000-0000-0000-000000000401")

    def fake_build_agent(
        config,
        *,
        tools=None,
        checkpointer=None,
        compaction_hooks=None,
        additional_middlewares=None,
    ):
        del tools, checkpointer, compaction_hooks
        captured["model_headers"] = config.model_headers
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)

    build_dayboard_agent(
        Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_NORTHGATE_METADATA_ENABLED=True,
        ),
        tools=[],
        context=tenant_context,
        run_id=run_id,
    )

    assert captured["model_headers"] == {
        "Northgate-Metadata": (
            f'{{"tenant_id":"{tenant_context.tenant_id}",'
            f'"user_id":"{tenant_context.user_id}","run_id":"{run_id}"}}'
        )
    }


def test_build_dayboard_agent_requires_trusted_context_for_northgate_metadata() -> None:
    with pytest.raises(ValueError, match="trusted tenant context and run ID"):
        build_dayboard_agent(
            Settings(
                APP_MODEL_NAME="openai:gpt-test",
                DAYBOARD_NORTHGATE_METADATA_ENABLED=True,
            ),
            tools=[],
        )


def test_build_dayboard_agent_selects_northgate_for_canary_tenant(
    monkeypatch,
    tenant_context: TenantContext,
) -> None:
    captured = {}
    run_id = UUID("00000000-0000-0000-0000-000000000402")

    def fake_build_agent(
        config,
        *,
        tools=None,
        checkpointer=None,
        compaction_hooks=None,
        additional_middlewares=None,
    ):
        del tools, checkpointer, compaction_hooks
        captured["model_headers"] = config.model_headers
        captured["model_options"] = config.model_options
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)
    settings = Settings(
        APP_MODEL_NAME="openai:gpt-test",
        DAYBOARD_NORTHGATE_BASE_URL="http://northgate:8080/v1/gateways/dayboard/openai",
        DAYBOARD_NORTHGATE_APPLICATION_KEY="northgate-key",
        DAYBOARD_NORTHGATE_CANARY_TENANT_IDS=str(tenant_context.tenant_id),
    )

    build_dayboard_agent(
        settings,
        tools=[],
        context=tenant_context,
        run_id=run_id,
    )

    assert captured["model_options"]["base_url"] == (
        "http://northgate:8080/v1/gateways/dayboard/openai"
    )
    assert captured["model_options"]["api_key"].get_secret_value() == "northgate-key"
    assert captured["model_options"]["model_kwargs"]["prompt_cache_key"].startswith(
        "dayboard-scheduling-v1-"
    )
    assert "Northgate-Metadata" in captured["model_headers"]


def test_build_dayboard_agent_keeps_non_canary_tenant_on_default_connection(
    monkeypatch,
    tenant_context: TenantContext,
) -> None:
    captured = {}

    def fake_build_agent(
        config,
        *,
        tools=None,
        checkpointer=None,
        compaction_hooks=None,
        additional_middlewares=None,
    ):
        del tools, checkpointer, compaction_hooks
        captured["model_headers"] = config.model_headers
        captured["model_options"] = config.model_options
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)
    settings = Settings(
        APP_MODEL_NAME="openai:gpt-test",
        DAYBOARD_NORTHGATE_BASE_URL="http://northgate:8080/v1/gateways/dayboard/openai",
        DAYBOARD_NORTHGATE_APPLICATION_KEY="northgate-key",
        DAYBOARD_NORTHGATE_CANARY_TENANT_IDS=(
            "00000000-0000-0000-0000-000000000099"
        ),
    )

    build_dayboard_agent(
        settings,
        tools=[],
        context=tenant_context,
        run_id=UUID("00000000-0000-0000-0000-000000000403"),
    )

    assert captured["model_options"]["model_kwargs"]["prompt_cache_key"].startswith(
        "dayboard-scheduling-v1-"
    )
    assert "base_url" not in captured["model_options"]
    assert "api_key" not in captured["model_options"]
    assert captured["model_headers"] == {}


def test_build_dayboard_agent_uses_stable_partitioned_prompt_cache_key(
    monkeypatch,
    tenant_context: TenantContext,
) -> None:
    captured = []

    def fake_build_agent(
        config,
        *,
        tools=None,
        checkpointer=None,
        compaction_hooks=None,
        additional_middlewares=None,
    ):
        del tools, checkpointer, compaction_hooks
        captured.append(config.model_options["model_kwargs"]["prompt_cache_key"])
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)
    settings = Settings(APP_MODEL_NAME="openai:gpt-test")

    build_dayboard_agent(settings, tools=[], context=tenant_context)
    build_dayboard_agent(settings, tools=[], context=tenant_context)

    assert captured[0] == captured[1]
    assert captured[0].startswith("dayboard-scheduling-v1-")
    assert captured[0].rsplit("-", 1)[1].isdigit()


def test_build_dayboard_agent_does_not_send_openai_cache_key_to_other_providers(
    monkeypatch,
    tenant_context: TenantContext,
) -> None:
    captured = {}

    def fake_build_agent(
        config,
        *,
        tools=None,
        checkpointer=None,
        compaction_hooks=None,
        additional_middlewares=None,
    ):
        del tools, checkpointer, compaction_hooks
        captured.update(config.model_options)
        return {"agent": "fake"}

    monkeypatch.setattr("dayboard.agent.factory.build_agent", fake_build_agent)

    build_dayboard_agent(
        Settings(APP_MODEL_NAME="anthropic:claude-test"),
        tools=[],
        context=tenant_context,
    )

    assert captured == {}


def test_build_dayboard_agent_does_not_duplicate_clarification_tool(monkeypatch) -> None:
    captured = {}

    def fake_build_agent(
        config,
        *,
        tools=None,
        checkpointer=None,
        compaction_hooks=None,
        additional_middlewares=None,
    ):
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


def test_build_dayboard_agent_rejects_trusted_context_in_tool_schema() -> None:
    class UnsafeTool:
        name = "search_knowledge"
        args = {"query": {"type": "string"}, "tenant_id": {"type": "string"}}

    with pytest.raises(
        ValueError,
        match="search_knowledge.*trusted server context.*tenant_id",
    ):
        build_dayboard_agent(
            Settings(APP_MODEL_NAME="openai:gpt-test"),
            tools=[UnsafeTool()],
        )


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
            del context, run, event_metadata
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

    monkeypatch.setattr(
        "dayboard.app.commands.build_run_service",
        lambda session: FakeRunService(session),
    )

    def fake_build_dayboard_agent(*args, **kwargs):
        built["run_id"] = kwargs["run_id"]
        built["context"] = kwargs["context"]
        built["compaction_hooks"] = kwargs["compaction_hooks"]
        return {"agent": "fake"}

    async def fake_invoker(**kwargs):
        assert kwargs["agent_factory"]() == {"agent": "fake"}
        assert kwargs["config"]["configurable"]["thread_id"] != str(run_id)
        assert kwargs["config"]["configurable"]["checkpoint_ns"] == "dayboard-time-v2"
        assert kwargs["context"]["run_id"] == str(run_id)
        assert len(built["compaction_hooks"]) == 1
        return {"thread_data": {"clarification": {"question": "几点开始？"}}, "messages": []}

    monkeypatch.setattr("dayboard.app.commands.build_dayboard_agent", fake_build_dayboard_agent)
    service = CommandService(
        FakeSession(),
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
            executor_factory=fake_executor_factory(fake_invoker),
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

    monkeypatch.setattr(
        "dayboard.app.commands.build_run_service",
        lambda session: FakeRunService(session),
    )
    service = CommandService(
        FakeSession(),
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
            executor_factory=fake_executor_factory(failing_invoker),
            conversation_service=FakeConversationService(),
    )

    with caplog.at_level(logging.ERROR, logger="dayboard.app.commands"):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            request = CommandRequest(message="安排会议")
            run_id = await service.create_command_run(tenant_context, request)
            await service.execute_command_run(tenant_context, request, run_id)

    assert recorded_failures == [("RuntimeError", "provider unavailable")]
    assert "dayboard.command.failed" in caplog.text
