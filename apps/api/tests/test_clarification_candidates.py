from uuid import uuid4

import pytest
from north import ClarificationRequest
from north.agents.middlewares.clarification import ClarificationMiddleware
from langchain_core.messages import ToolMessage
from types import SimpleNamespace

from dayboard.agent.clarification_candidates import RunClarificationCandidates
from dayboard.agent.run_result_projection import extract_clarification_payload, project_run_result


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
    binding.register([snapshot("产品评审"), snapshot("项目例会")], has_more=False)
    medical = [snapshot("入职体检"), snapshot("年度体检")]
    key = binding.register(medical, has_more=False)
    binding.ask(question="哪项体检？", candidate_set_key=key)
    payload = extract_clarification_payload(ClarificationRequest(question="哪项体检？"), binding)
    assert [candidate.title for candidate in payload.candidates] == ["入职体检", "年度体检"]
    assert [str(candidate.id) for candidate in payload.candidates] == [row["id"] for row in medical]
    assert all(candidate.row_version == 3 for candidate in payload.candidates)


def test_free_text_and_suggested_choices_do_not_inherit_search_candidates():
    binding = RunClarificationCandidates()
    key = binding.register([snapshot("会议")], has_more=False)
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
    key = first.register([snapshot("会议")], has_more=False)
    second = RunClarificationCandidates()
    with pytest.raises(ValueError, match="Unknown candidate set"):
        second.ask(question="哪场？", candidate_set_key=key)
    with pytest.raises(ValueError, match="Unknown candidate set"):
        extract_clarification_payload(ClarificationRequest(question="哪场？"), second)
    key = second.register([snapshot("体检")], has_more=False)
    second.ask(question="哪项？", candidate_set_key=key)
    assert extract_clarification_payload(ClarificationRequest(question="哪项？"), second).candidates


@pytest.mark.parametrize("count,has_more", [(0, False), (11, False), (2, True)])
def test_incomplete_or_oversized_sets_are_not_selectable(count, has_more):
    binding = RunClarificationCandidates()
    assert binding.register([snapshot(str(i)) for i in range(count)], has_more=has_more) is None


def test_north_tracks_custom_tool_and_projection_persists_selected_candidates():
    binding = RunClarificationCandidates()
    key = binding.register([snapshot("体检")], has_more=False)
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
    key = binding.register([snapshot("体检")], has_more=False)
    binding.ask(question="哪项体检？", candidate_set_key=key)
    with pytest.raises(ValueError, match="does not match"):
        extract_clarification_payload(ClarificationRequest(question="几点？"), binding)


def test_reused_scope_cannot_resolve_a_previous_runs_key():
    binding = RunClarificationCandidates()
    key = binding.register([snapshot("体检")], has_more=False)
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
    key = binding.register([snapshot("体检")], has_more=False)
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
