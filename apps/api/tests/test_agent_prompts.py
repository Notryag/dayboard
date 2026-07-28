from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from dayboard.agent.prompts import (
    build_dayboard_system_prompt,
    build_runtime_scheduling_context,
)
from agent_platform.core import TenantContext


def test_system_prompt_exposes_relative_dates_and_anytime_contract() -> None:
    context = TenantContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )

    prompt = build_runtime_scheduling_context(
        context,
        now=datetime(2026, 7, 13, 15, 57, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    system_prompt = build_dayboard_system_prompt()

    assert "today: 2026-07-13" in prompt
    assert "tomorrow: 2026-07-14" in prompt
    assert "day after tomorrow: 2026-07-15" in prompt
    assert "Local date/time fields never include an offset" in system_prompt
    assert "Explicit foreign timezones are not supported" in system_prompt
    assert "new_date preserves the existing timing mode" in system_prompt
    assert (
        "the original entry's local interval (not its requested destination interval)"
        in system_prompt
    )
    assert "Only actions without a concrete temporal anchor are tasks" in system_prompt
    assert '"明天提交报告" uses tomorrow\'s local_date' in system_prompt
    assert "Date without a clock or daypart is an anytime calendar entry" in system_prompt
    assert "Any concrete date, clock, or daypart makes the action a calendar entry" in system_prompt
    assert "search the referenced calendar entry first" in system_prompt
    assert "anchor_entry_id and its row_version" in system_prompt
    assert "Never include the referenced action in the new title" in system_prompt
    assert "starts at the anchor's end" in system_prompt
    assert "do not invent a clock" in system_prompt
    assert "早上 08:00" in system_prompt
    assert "晚上 20:00" in system_prompt
    assert "Create an undated task and never invent a date" in system_prompt
    assert "never state a date, start time, end time, or status" in system_prompt
    assert "Use plain text only: do not use Markdown" in system_prompt
    assert "separate cards" in system_prompt
    assert "Current Beijing datetime:" not in system_prompt


def test_system_prompt_is_stable_across_runtime_values() -> None:
    first = build_dayboard_system_prompt()
    second = build_dayboard_system_prompt()

    assert first == second


def test_runtime_context_converts_to_beijing_time() -> None:
    context = TenantContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )

    runtime_context = build_runtime_scheduling_context(
        context,
        now=datetime(2026, 7, 13, 7, 57, tzinfo=ZoneInfo("UTC")),
    )

    assert "Current Beijing datetime: 2026-07-13T15:57" in runtime_context
