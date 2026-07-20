from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from dayboard.agent.prompts import build_dayboard_system_prompt
from dayboard.context import TenantContext


def test_system_prompt_exposes_relative_dates_and_end_time_edit_contract() -> None:
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
    assert "a reminder at its start (PT0M)" in prompt
    assert "pass reminder=null only when the user explicitly requests no reminder" in prompt
    assert "Never append Z, +08:00, or any timezone offset" in prompt
    assert "Explicit foreign timezones are not supported" in prompt
    assert "new_local_end changes end/duration" in prompt
    assert "the original entry's date range (not its requested destination date)" in prompt
    assert "a task tracks an action/outcome with no scheduled date/time" in prompt
    assert '"明天早上 8 点吃药" schedules the activity at 08:00 and is a calendar entry' in prompt
    assert '"明天早上 8 点前吃药" sets a deadline and is a task with due_local' in prompt
    assert '"明天早上吃药" is a calendar entry at the deterministic 08:00 morning default' in prompt
    assert "a calendar entry schedules an activity with any resolvable date or time" in prompt
    assert "date only defaults to 09:00" in prompt
    assert "早上 08:00" in prompt
    assert "晚上 20:00" in prompt
    assert "Create undated tasks for those actions and never invent a clock time" in prompt
    assert "Never ask for a due time merely because an ordinary task is undated" in prompt
    assert "never state a date, start time, end time, or status" in prompt
    assert "Use plain text only: do not use Markdown" in prompt
    assert "separate cards" in prompt
    assert prompt.index("Rules:") < prompt.index("Runtime scheduling context:")
    assert prompt.index("Runtime scheduling context:") < prompt.index("Current local datetime:")


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
