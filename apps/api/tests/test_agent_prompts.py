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
    assert "Every calendar entry defaults to a reminder at its start (PT0M)" in prompt
    assert "pass reminder=null only when the user explicitly requests no reminder" in prompt
    assert "Never append Z, +08:00, or any timezone offset" in prompt
    assert "Explicit foreign timezones are not supported" in prompt
    assert "new_local_end when the user changes the ending time or duration" in prompt
    assert "a calendar entry reserves a concrete time block" in prompt
    assert "A date or broad daypart by itself does not reserve a calendar block" in prompt
    assert "Create undated tasks for those actions and never invent a clock time" in prompt
    assert "Never ask for a due time merely because an ordinary task is undated" in prompt
    assert "Never state a date, start time, end time, or status" in prompt
    assert "Use plain text only: do not use Markdown" in prompt
    assert "separate cards" in prompt
