from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from dayboard.agent.prompts import build_dayboard_system_prompt
from agent_platform.identity import TenantContext


def test_system_prompt_exposes_relative_dates_and_anytime_contract() -> None:
    context = TenantContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )

    prompt = build_dayboard_system_prompt(
        context,
        now=datetime(2026, 7, 13, 15, 57, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert "today: 2026-07-13" in prompt
    assert "tomorrow: 2026-07-14" in prompt
    assert "day after tomorrow: 2026-07-15" in prompt
    assert "Local date/time fields never include an offset" in prompt
    assert "Explicit foreign timezones are not supported" in prompt
    assert "new_date preserves the existing timing mode" in prompt
    assert "the original entry's local interval (not its requested destination interval)" in prompt
    assert "Only actions without a concrete temporal anchor are tasks" in prompt
    assert '"明天提交报告" uses tomorrow\'s local_date' in prompt
    assert "Date without a clock or daypart is an anytime calendar entry" in prompt
    assert "Any concrete date, clock, or daypart makes the action a calendar entry" in prompt
    assert "search the referenced calendar entry first" in prompt
    assert "anchor_entry_id and its row_version" in prompt
    assert "Never include the referenced action in the new title" in prompt
    assert "starts at the anchor's end" in prompt
    assert "do not invent a clock" in prompt
    assert "早上 08:00" in prompt
    assert "晚上 20:00" in prompt
    assert "Create an undated task and never invent a date" in prompt
    assert "never state a date, start time, end time, or status" in prompt
    assert "Use plain text only: do not use Markdown" in prompt
    assert "separate cards" in prompt
    assert prompt.index("Rules:") < prompt.index("Runtime scheduling context:")
    assert prompt.index("Runtime scheduling context:") < prompt.index(
        "Current Beijing datetime:"
    )


def test_system_prompt_keeps_runtime_values_after_the_stable_prefix() -> None:
    context = TenantContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )
    first = build_dayboard_system_prompt(
        context,
        now=datetime(2026, 7, 13, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    second = build_dayboard_system_prompt(
        context,
        now=datetime(2026, 7, 14, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    marker = "Runtime scheduling context:"
    assert first.partition(marker)[0] == second.partition(marker)[0]
    assert first.partition(marker)[2] != second.partition(marker)[2]
