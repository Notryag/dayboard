"""Real agent-loop orchestration with deterministic model and tool seams."""

import json

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool

from dayboard.agent.middleware import SchedulingToolBindingMiddleware


class ScriptedModel(FakeMessagesListChatModel):
    bound_names: list[list[str]] = []

    def bind_tools(self, tools, **kwargs):
        self.bound_names.append([tool.name for tool in tools])
        return self.bind(tools=tools, **kwargs)


async def test_dependent_and_cross_domain_steps_survive_successful_writes():
    names = ["create_calendar_entry", "search_calendar_entries", "update_task_item"]
    results = {
        names[0]: {"type": "calendar_entry_created"},
        names[1]: {"items": [{"id": "anchor", "row_version": 1}], "has_more": False},
        names[2]: {"type": "task_item_updated"},
    }
    executed = []

    def make_tool(name):
        def run():
            executed.append(name)
            return json.dumps(results[name])

        return StructuredTool.from_function(run, name=name, description=name)

    # The second creation depends on a search of the first creation's anchor.
    calls = [names[0], names[1], names[0], names[2]]
    model = ScriptedModel(
        responses=[
            *[
                AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": str(i)}])
                for i, name in enumerate(calls)
            ],
            AIMessage(content="已完成"),
        ]
    )
    agent = create_agent(
        model=model,
        tools=[make_tool(name) for name in names],
        middleware=[SchedulingToolBindingMiddleware()],
    )
    result = await agent.ainvoke({"messages": [HumanMessage(content="先跳舞再唱歌，完成买菜待办")]})
    assert executed == calls
    assert result["messages"][-1].content == "已完成"
    assert all(set(bound) == set(names) for bound in model.bound_names)
