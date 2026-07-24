from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fake_runtime import fake_executor_factory
from langchain_core.messages import AIMessage, ToolMessage

from dayboard.agent.factory import build_dayboard_agent
from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.app.run_execution import DayboardRunExecutionDriver
from dayboard.app.run_result_projection import extract_clarification_payload
from dayboard.config import Settings
from agent_platform.core import AgentRun, AgentRunStatus, TenantContext


def test_clarification_state_uses_real_search_tool_candidates() -> None:
    entry_id = uuid4()
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
                content="compact model receipt",
                artifact={
                    "type": "schedule_items_result",
                    "items": [
                        {
                            "kind": "calendar",
                            "value": {
                                "id": str(entry_id),
                                "row_version": 4,
                                "title": "产品会议",
                                "timing_kind": "timed",
                                "scheduled_date": None,
                                "start_time": "2026-07-11T00:00:00+00:00",
                                "end_time": "2026-07-11T01:00:00+00:00",
                                "timezone": "Asia/Shanghai",
                                "status": "scheduled",
                                "tenant_id": "must-not-persist",
                            },
                        }
                    ],
                },
            ),
        ]
    }

    payload = extract_clarification_payload(result)

    assert payload.response_kind == "calendar_choice"
    candidate = payload.candidates[0]
    assert candidate.kind == "calendar"
    assert candidate.id == entry_id
    assert candidate.row_version == 4
    assert payload.presentation is not None
    assert payload.presentation.type == "calendar_entry_choice"
    assert payload.presentation.options[0].title == "产品会议"
    assert not hasattr(candidate, "tenant_id")


def test_clarification_state_uses_agent_suggested_choices_without_search_results() -> None:
    payload = extract_clarification_payload(
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

    assert payload.response_kind == "single_choice"
    assert [candidate.value for candidate in payload.candidates] == [
        "09:00",
        "14:00",
        "其他时间",
    ]
    assert payload.presentation is not None
    assert payload.presentation.type == "suggested_choice"
    assert [option.label for option in payload.presentation.options] == [
        "09:00",
        "14:00",
        "其他时间",
    ]

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


async def test_dayboard_driver_maps_north_clarification_result_to_platform_outcome(
    tenant_context: TenantContext,
    monkeypatch,
) -> None:
    built = {}
    outcomes = []
    run_id = uuid4()
    now = datetime.now(UTC)
    run = AgentRun(
        id=run_id,
        tenant_id=tenant_context.tenant_id,
        owner_user_id=tenant_context.user_id,
        thread_id=uuid4(),
        status=AgentRunStatus.running,
        input_message="安排会议",
        result_message=None,
        created_at=now,
        updated_at=now,
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

    async def complete(outcome) -> None:
        outcomes.append(outcome)

    async def fail(failure) -> bool:
        del failure
        return True

    settings = Settings(
        APP_MODEL_NAME="openai:gpt-test",
        DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
    )
    monkeypatch.setattr("dayboard.app.run_execution.build_dayboard_agent", fake_build_dayboard_agent)
    driver = DayboardRunExecutionDriver(
        SimpleNamespace(),
        settings=settings,
        unit_of_work=SimpleNamespace(),
        conversations=SimpleNamespace(),
        runs=SimpleNamespace(),
        budget_guard=ProviderBudgetGuard(settings),
        provider_usage=SimpleNamespace(),
        executor_factory=fake_executor_factory(fake_invoker),
    )

    await driver.execute(tenant_context, run, on_completed=complete, on_failed=fail)

    assert built["context"] == tenant_context
    assert built["run_id"] == run_id
    assert outcomes[0].result_message == "几点开始？"
    assert outcomes[0].interaction is not None
    assert outcomes[0].interaction.source_run_id == run_id


async def test_dayboard_driver_logs_and_projects_failure(
    tenant_context: TenantContext,
    caplog,
) -> None:
    recorded_failures = []

    async def failing_invoker(**kwargs):
        del kwargs
        raise RuntimeError("provider unavailable")

    async def complete(outcome) -> None:
        del outcome

    async def fail(failure) -> bool:
        recorded_failures.append((failure.error_type, failure.error_message))
        return True

    now = datetime.now(UTC)
    run = AgentRun(
        id=uuid4(),
        tenant_id=tenant_context.tenant_id,
        owner_user_id=tenant_context.user_id,
        thread_id=uuid4(),
        status=AgentRunStatus.running,
        input_message="安排会议",
        result_message=None,
        created_at=now,
        updated_at=now,
    )
    settings = Settings(
        APP_MODEL_NAME="openai:gpt-test",
        DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
    )
    driver = DayboardRunExecutionDriver(
        SimpleNamespace(),
        settings=settings,
        unit_of_work=SimpleNamespace(),
        conversations=SimpleNamespace(),
        runs=SimpleNamespace(),
        budget_guard=ProviderBudgetGuard(settings),
        provider_usage=SimpleNamespace(),
        executor_factory=fake_executor_factory(failing_invoker),
    )

    with caplog.at_level(logging.ERROR, logger="dayboard.app.run_execution"):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await driver.execute(
                tenant_context,
                run,
                on_completed=complete,
                on_failed=fail,
            )

    assert recorded_failures == [("RuntimeError", "provider unavailable")]
    assert "dayboard.command.failed" in caplog.text
