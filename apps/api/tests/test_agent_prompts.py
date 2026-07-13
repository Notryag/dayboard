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
    assert "new_end_time when the user changes the ending time or duration" in prompt
    assert "Never state a date, start time, end time, or status" in prompt
