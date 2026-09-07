from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from north import NorthSummarizationMiddleware

from dayboard.agent.budget import ProviderBudgetExceeded, ProviderBudgetGuard, RunModelBudget
from dayboard.config import Settings


def budget(context, **overrides):
    settings = Settings(
        DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        DAYBOARD_PROVIDER_BUDGET_TOKEN_LIMIT="1000000/day",
        **overrides,
    )
    guard = ProviderBudgetGuard(settings)
    admission = guard.estimate(input_text="hello")
    guard.check(context=context, model_name="openai:test", estimate=admission)
    return RunModelBudget(guard, context, "openai:test", admission)


async def test_callback_rejects_before_provider_execution_and_resets_per_run(user_context):
    handler = budget(user_context, DAYBOARD_AGENT_MAX_MODEL_CALLS=1)
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="first"), AIMessage(content="second")]
    )
    assert (await model.ainvoke("hello", config={"callbacks": [handler]})).content == "first"
    with pytest.raises(ProviderBudgetExceeded, match="run_requests"):
        await model.ainvoke("again", config={"callbacks": [handler]})
    assert model.i == 1  # The denied call never reaches the model.
    other = budget(user_context, DAYBOARD_AGENT_MAX_MODEL_CALLS=1)
    assert (await model.ainvoke("again", config={"callbacks": [other]})).content == "second"


def test_reservation_includes_history_tools_and_output(user_context):
    handler = budget(user_context, DAYBOARD_AGENT_MAX_RUN_TOKENS=3000)
    with pytest.raises(ProviderBudgetExceeded, match="run_tokens"):
        handler.on_chat_model_start(
            {},
            [[SystemMessage(content="历史" * 300), HumanMessage(content="好")]],
            run_id=uuid4(),
            invocation_params={"tools": [{"description": "x" * 1000}]},
        )
    assert handler.calls == 0


def test_each_call_checks_shared_request_budget(user_context):
    handler = budget(user_context, DAYBOARD_PROVIDER_BUDGET_REQUEST_LIMIT="1/minute")
    handler.on_chat_model_start({}, [[HumanMessage(content="first")]], run_id=uuid4())
    with pytest.raises(ProviderBudgetExceeded) as error:
        handler.on_chat_model_start({}, [[HumanMessage(content="second")]], run_id=uuid4())
    assert error.value.budget_type == "request"


def test_actual_usage_replaces_run_estimate_without_double_settlement(user_context):
    handler = budget(user_context)
    call_id = uuid4()
    handler.on_chat_model_start({}, [[HumanMessage(content="hello")]], run_id=call_id)
    reserved = handler.reservation
    result = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="ok",
                        usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
                    )
                )
            ]
        ]
    )
    handler.on_llm_end(result, run_id=call_id)
    handler.on_llm_end(result, run_id=call_id)
    assert handler.tokens == 12
    assert handler.reservation == reserved


def test_provider_response_usage_is_counted_without_message_usage(user_context):
    handler = budget(user_context)
    call_id = uuid4()
    handler.on_chat_model_start({}, [[HumanMessage(content="hello")]], run_id=call_id)
    result = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="ok"))]],
        llm_output={
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        },
    )
    handler.on_llm_end(result, run_id=call_id)
    assert handler.tokens == 12


async def test_denied_summary_does_not_overwrite_persisted_memory(user_context):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fake_runtime import fake_executor_factory
    from north.runtime import MemoryStreamBridge
    from agent_platform.core import AgentRun, AgentRunStatus
    from dayboard.agent.run_execution import DayboardRunExecutionDriver

    guard = budget(user_context, DAYBOARD_AGENT_MAX_RUN_TOKENS=1).guard
    conversations = SimpleNamespace(update_summary=AsyncMock())
    failure = AsyncMock(return_value=True)
    completed = AsyncMock()
    compaction_hooks = []

    def agent_factory(context, run_id, hooks):
        compaction_hooks.extend(hooks)
        return object()

    async def invoke(**kwargs):
        kwargs["agent_factory"]()
        handler = kwargs["config"]["callbacks"][0]
        try:
            handler.on_chat_model_start({}, [[HumanMessage(content="summary")]], run_id=uuid4())
        except ProviderBudgetExceeded:
            pass  # Simulate the summary helper's exception-to-text behavior.
        await compaction_hooks[0](SimpleNamespace(summary_text="Error generating summary"))

    driver = DayboardRunExecutionDriver(
        unit_of_work=SimpleNamespace(),
        conversations=conversations,
        runs=SimpleNamespace(),
        budget_guard=guard,
        provider_usage=SimpleNamespace(),
        runtime_event_uow_factory=lambda: None,
        agent_factory=agent_factory,
        model_name="openai:test",
        stream_bridge=MemoryStreamBridge(),
        executor_factory=fake_executor_factory(invoke),
    )
    now = datetime.now(UTC)
    run = AgentRun(
        id=uuid4(),
        user_id=user_context.user_id,
        thread_id=uuid4(),
        status=AgentRunStatus.running,
        message_count=1,
        first_human_message="hi",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ProviderBudgetExceeded):
        await driver.execute(user_context, run, "hi", on_completed=completed, on_failed=failure)
    conversations.update_summary.assert_not_awaited()
    completed.assert_not_awaited()
    failure.assert_awaited_once()


async def test_summary_model_is_charged_and_cannot_bypass_denial(user_context):
    handler = budget(user_context, DAYBOARD_AGENT_MAX_MODEL_CALLS=1)
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="summary"), AIMessage(content="unused")]
    )
    middleware = NorthSummarizationMiddleware(model=model.with_config(callbacks=[handler]))
    await middleware._acreate_summary([HumanMessage(content="old history")])
    assert handler.calls == 1
    # Summary helpers may catch exceptions, but the rejection stays sticky for the lead model.
    await middleware._acreate_summary([HumanMessage(content="more history")])
    assert handler.rejected is not None
    with pytest.raises(ProviderBudgetExceeded):
        await model.ainvoke("continue", config={"callbacks": [handler]})
    assert model.i == 1


async def test_north_propagates_run_budget_to_separate_summary_model(monkeypatch, user_context):
    from north import AppConfig, build_agent

    handler = budget(user_context, DAYBOARD_AGENT_MAX_MODEL_CALLS=1)
    lead = FakeMessagesListChatModel(responses=[AIMessage(content="should not be called")])
    summary = FakeMessagesListChatModel(
        responses=[AIMessage(content="summary"), AIMessage(content="unused")]
    )
    monkeypatch.setattr(
        "north.agent.create_chat_model",
        lambda name, **kwargs: summary if name == "summary" else lead,
    )
    agent = build_agent(
        AppConfig(
            model_name="lead",
            summarization_enabled=True,
            summarization_model_name="summary",
            summarization_normal_trigger_tokens=20,
            summarization_emergency_trigger_tokens=10000,
            summarization_target_tokens=10,
        ),
        checkpointer=False,
    )
    history = [
        HumanMessage(content="old history " * 30),
        AIMessage(content="old answer " * 30),
        HumanMessage(content="next"),
    ]
    with pytest.raises(ProviderBudgetExceeded, match="run_requests"):
        await agent.ainvoke(
            {"messages": history}, config={"callbacks": [handler]}, context={"run_id": "test"}
        )
    assert summary.i == 1
    assert handler.calls == 1
