import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from dayboard.agent.run_result_projection import extract_final_message


@pytest.mark.parametrize(
    "message",
    [
        AIMessage(content="已创建会议，体检改期未完成。"),
        {"type": "ai", "content": "已创建会议，体检改期未完成。"},
        {"role": "assistant", "content": "已创建会议，体检改期未完成。"},
    ],
)
def test_final_assistant_summary_is_preserved(message):
    assert extract_final_message({"messages": [message]}) == "已创建会议，体检改期未完成。"


@pytest.mark.parametrize(
    "tail",
    [
        HumanMessage(content="再创建两项任务"),
        ToolMessage(content='{"type":"task_item_created"}', tool_call_id="one"),
        AIMessage(content=""),
        AIMessage(
            content="准备创建", tool_calls=[{"name": "create_task_item", "id": "one", "args": {}}]
        ),
        {"role": "tool", "content": "raw receipt"},
        {"content": "untyped content"},
        {"role": "assistant", "content": "准备创建", "additional_kwargs": {"tool_calls": [{}]}},
    ],
)
def test_no_tool_receipt_user_text_or_earlier_summary_is_used(tail):
    result = extract_final_message(
        {
            "messages": [
                AIMessage(content="上一轮操作已全部完成"),
                HumanMessage(content="再创建两项任务"),
                tail,
            ]
        }
    )
    assert "未返回最终说明" in result
    assert "避免重复提交" in result


@pytest.mark.parametrize("values", [None, {}, {"messages": []}, {"messages": "invalid"}])
def test_missing_result_does_not_claim_success(values):
    assert "未返回最终说明" in extract_final_message(values)


def test_final_summary_uses_public_text_blocks_without_reasoning():
    message = AIMessage(
        content=[
            {"type": "reasoning", "text": "internal reasoning"},
            {"type": "text", "text": "会议已创建，另一项未完成。"},
        ]
    )
    assert extract_final_message({"messages": [message]}) == "会议已创建，另一项未完成。"
