from uuid import uuid4
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from north import ClarificationRequest
from north.agents.middlewares.clarification import ClarificationMiddleware
from langchain_core.messages import ToolMessage
from types import SimpleNamespace

from dayboard.agent.clarification_candidates import RunClarificationCandidates
from dayboard.agent.run_result_projection import extract_clarification_payload, project_run_result
from dayboard.app.clarifications import ClarificationService, public_conversation_state
from dayboard.domain.interactions import ClarificationPayload
from agent_platform.application import ConversationService
from agent_platform.core import UserContext


def snapshot(title):
    return {
        "id": str(uuid4()),
        "row_version": 3,
        "title": title,
        "timing_kind": "anytime",
        "scheduled_date": "2026-11-13",
        "timezone": "Asia/Shanghai",
        "status": "scheduled",
    }


def test_multiple_searches_bind_only_the_selected_set():
    binding = RunClarificationCandidates()
    binding.register([snapshot("产品评审"), snapshot("项目例会")], has_more=False, kind="calendar")
    medical = [snapshot("入职体检"), snapshot("年度体检")]
    key = binding.register(medical, has_more=False, kind="calendar")
    binding.ask(question="哪项体检？", candidate_set_key=key)
    payload = extract_clarification_payload(ClarificationRequest(question="哪项体检？"), binding)
    assert [candidate.title for candidate in payload.candidates] == ["入职体检", "年度体检"]
    assert [str(candidate.id) for candidate in payload.candidates] == [row["id"] for row in medical]
    assert all(candidate.row_version == 3 for candidate in payload.candidates)


def test_task_choice_uses_its_search_snapshot_after_other_searches():
    binding = RunClarificationCandidates()
    tasks = [
        {"id": str(uuid4()), "row_version": 4, "title": title, "status": "open"}
        for title in ["整理周报", "提交周报"]
    ]
    key = binding.register(tasks, has_more=False, kind="task")
    binding.register([snapshot("周报会议")], has_more=False, kind="calendar")
    binding.ask(question="哪个周报任务？", candidate_set_key=key)
    payload = extract_clarification_payload(ClarificationRequest(question="哪个周报任务？"), binding)
    assert payload.response_kind == "task_choice"
    assert [str(candidate.id) for candidate in payload.candidates] == [row["id"] for row in tasks]
    assert all(candidate.row_version == 4 for candidate in payload.candidates)
    assert payload.presentation.type == "task_item_choice"
    public_options = payload.presentation.model_dump(mode="json")["options"]
    assert public_options == [
        {"key": f"candidate_{index}", "title": row["title"], "status": "open"}
        for index, row in enumerate(tasks, start=1)
    ]
    binding.reset()
    with pytest.raises(ValueError, match="Unknown candidate set"):
        binding.ask(question="哪个任务？", candidate_set_key=key)


async def test_task_choice_restores_persisted_snapshot_without_run_local_state():
    binding = RunClarificationCandidates()
    task_id = uuid4()
    key = binding.register([
        {"id": str(task_id), "row_version": 7, "title": "整理周报", "status": "open"}
    ], has_more=False, kind="task")
    binding.ask(question="哪个任务？", candidate_set_key=key)
    payload = extract_clarification_payload(ClarificationRequest(question="哪个任务？"), binding)
    pending = ClarificationService.build_pending(run_id=uuid4(), question="哪个任务？", payload=payload)
    # Exercise the persisted JSON boundary, with the original Run scope discarded.
    persisted_payload = ClarificationPayload.model_validate_json(payload.model_dump_json())
    restored_interaction = pending.interaction.model_copy(update={
        "payload": persisted_payload.model_dump(mode="json")
    })
    binding.reset()
    thread_id = uuid4()
    state = SimpleNamespace(
        thread_id=thread_id, interaction=restored_interaction, version=3,
        expires_at=datetime.now(UTC) + timedelta(days=1), updated_at=datetime.now(UTC),
    )
    conversations = AsyncMock(spec=ConversationService)
    conversations.get_state.return_value = state
    context = UserContext(user_id=uuid4(), timezone="Asia/Shanghai", locale="zh-CN")
    public = public_conversation_state(state)
    assert public.interaction.payload.presentation.type == "task_item_choice"
    assert str(task_id) not in public.model_dump_json()
    resolved = await ClarificationService(conversations).resolve_choice(
        context, thread_id=thread_id, state_version=3, option_key="candidate_1",
    )
    assert str(task_id) in resolved.agent_message
    assert '"row_version": 7' in resolved.agent_message
    assert "server-validated task candidate" in resolved.agent_message
    assert resolved.display_message == "选择“整理周报”"


def test_free_text_and_suggested_choices_do_not_inherit_search_candidates():
    binding = RunClarificationCandidates()
    key = binding.register([snapshot("会议")], has_more=False, kind="calendar")
    binding.ask(question="哪场会议？", candidate_set_key=key)
    binding.ask(question="体检哪天？")
    payload = extract_clarification_payload(ClarificationRequest(question="体检哪天？"), binding)
    assert payload.response_kind == "free_text"
    assert payload.candidates == []
    binding.ask(question="几点？", response_kind="single_choice", options=["九点", "十点"])
    payload = extract_clarification_payload(
        ClarificationRequest(
            question="几点？", response_kind="single_choice", options=("九点", "十点")
        ),
        binding,
    )
    assert payload.response_kind == "single_choice"


def test_foreign_run_keys_fail_closed_and_can_recover_with_new_search():
    first = RunClarificationCandidates()
    key = first.register([snapshot("会议")], has_more=False, kind="calendar")
    second = RunClarificationCandidates()
    with pytest.raises(ValueError, match="Unknown candidate set"):
        second.ask(question="哪场？", candidate_set_key=key)
    with pytest.raises(ValueError, match="Unknown candidate set"):
        extract_clarification_payload(ClarificationRequest(question="哪场？"), second)
    key = second.register([snapshot("体检")], has_more=False, kind="calendar")
    second.ask(question="哪项？", candidate_set_key=key)
    assert extract_clarification_payload(ClarificationRequest(question="哪项？"), second).candidates


@pytest.mark.parametrize("count,has_more", [(0, False), (11, False), (2, True)])
def test_incomplete_or_oversized_sets_are_not_selectable(count, has_more):
    binding = RunClarificationCandidates()
    assert binding.register(
        [snapshot(str(i)) for i in range(count)], has_more=has_more, kind="calendar"
    ) is None


def test_north_tracks_custom_tool_and_projection_persists_selected_candidates():
    binding = RunClarificationCandidates()
    key = binding.register([snapshot("体检")], has_more=False, kind="calendar")
    args = {"question": "哪项体检？", "candidate_set_key": key}
    tool = binding.build_tool()
    call = {"name": tool.name, "args": args, "id": "ask-1", "type": "tool_call"}
    message = tool.invoke(call)
    assert isinstance(message, ToolMessage)
    command = ClarificationMiddleware()._track_clarification(
        SimpleNamespace(tool_call=call), message
    )
    clarification = ClarificationRequest(**command.update["clarification_request"])
    result = SimpleNamespace(clarification=clarification)
    outcome = project_run_result(
        result, run_id=uuid4(), presentation_parts=[], clarification_candidates=binding
    )
    assert outcome.interaction.payload["candidates"][0]["title"] == "体检"


def test_unrelated_presentation_cannot_create_choices():
    item = {
        **snapshot("会议"),
        "start_time": None,
        "end_time": None,
        "participants": [],
        "reminder": None,
        "created_by_run_id": None,
        "created_at": "2026-11-11T00:00:00Z",
        "updated_at": "2026-11-11T00:00:00Z",
    }
    outcome = project_run_result(
        SimpleNamespace(clarification=ClarificationRequest(question="几点？")),
        run_id=uuid4(),
        presentation_parts=[
            {
                "tool_call_id": "search-meetings",
                "operation": "calendar_entry_found",
                "item": {"kind": "calendar", "value": item},
            }
        ],
    )
    assert outcome.interaction.payload["response_kind"] == "free_text"


def test_selected_set_cannot_be_attached_to_a_different_question():
    binding = RunClarificationCandidates()
    key = binding.register([snapshot("体检")], has_more=False, kind="calendar")
    binding.ask(question="哪项体检？", candidate_set_key=key)
    with pytest.raises(ValueError, match="does not match"):
        extract_clarification_payload(ClarificationRequest(question="几点？"), binding)


def test_reused_scope_cannot_resolve_a_previous_runs_key():
    binding = RunClarificationCandidates()
    key = binding.register([snapshot("体检")], has_more=False, kind="calendar")
    binding.ask(question="哪项？", candidate_set_key=key)
    binding.reset()
    assert not binding.selected
    with pytest.raises(ValueError, match="Unknown candidate set"):
        binding.ask(question="哪项？", candidate_set_key=key)


async def test_real_agent_uses_extended_tool_schema_and_north_signal(monkeypatch):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from dayboard.agent.factory import build_dayboard_agent
    from dayboard.config import Settings

    binding = RunClarificationCandidates()
    key = binding.register([snapshot("体检")], has_more=False, kind="calendar")
    captured = []

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            captured.extend(tools)
            return self

    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_clarification",
                        "id": "ask-1",
                        "args": {"question": "哪项体检？", "candidate_set_key": key},
                    }
                ],
            ),
            AIMessage(content="请选择体检。"),
        ]
    )
    monkeypatch.setattr("north.agent.create_chat_model", lambda *args, **kwargs: model)
    agent = build_dayboard_agent(
        Settings(APP_MODEL_NAME="openai:test", NORTH_SUMMARIZATION_ENABLED=False),
        tools=[],
        checkpointer=False,
        clarification_candidates=binding,
    )
    result = await agent.ainvoke({"messages": [HumanMessage(content="改期体检")]})
    assert result["clarification_request"]["question"] == "哪项体检？"
    assert binding.selected[0].title == "体检"
    ask_tools = [tool for tool in captured if getattr(tool, "name", None) == "ask_clarification"]
    assert ask_tools
    assert all("candidate_set_key" in tool.args for tool in ask_tools)
