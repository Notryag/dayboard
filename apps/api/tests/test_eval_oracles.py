from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from dayboard.eval_oracles import (
    BEIJING_TIMEZONE,
    EvalTemplateContext,
    ExpectedScheduleItem,
    evaluate_schedule_expectation,
    render_expectation,
    render_template,
)


def test_eval_template_context_is_stable_and_renders_future_dates() -> None:
    context = EvalTemplateContext.capture(
        now=datetime(2026, 7, 29, 23, 59, tzinfo=BEIJING_TIMEZONE)
    )
    variables = context.variables(tag="abc123")

    assert context.today == "2026-07-29"
    assert context.tomorrow == "2026-07-30"
    assert context.future_date == "2026-08-28"
    assert render_template("{future_month_day_zh}体检-{tag}", variables) == "8月28号体检-abc123"

    expectation = render_expectation(
        ExpectedScheduleItem(
            kind="calendar",
            title="会议{tag}",
            timing_kind="timed",
            local_start="{tomorrow}T09:00",
        ),
        variables,
    )
    assert expectation.title == "会议abc123"
    assert expectation.local_start == "2026-07-30T09:00"


def test_eval_template_rejects_unknown_variables() -> None:
    with pytest.raises(ValueError, match="unknown Eval template variable"):
        render_template("{missing}", {"tag": "abc123"})


async def test_calendar_oracle_compares_authoritative_local_projection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/calendar-entries"
        assert request.url.params["date"] == "2026-07-30"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "entry-1",
                        "title": "会议abc123",
                        "status": "scheduled",
                        "timing_kind": "timed",
                        "scheduled_date": None,
                        "start_time": "2026-07-30T01:00:00+00:00",
                        "end_time": "2026-07-30T02:00:00+00:00",
                        "timezone": "Asia/Shanghai",
                        "created_by_run_id": "run-1",
                    }
                ],
                "next_cursor": None,
            },
        )

    expectation = ExpectedScheduleItem(
        kind="calendar",
        title="会议abc123",
        status="scheduled",
        timing_kind="timed",
        local_start="2026-07-30T09:00",
        local_end="2026-07-30T10:00",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await evaluate_schedule_expectation(client, expectation)

    assert result["passed"] is True
    assert result["matched_count"] == 1
    assert result["actual"][0]["local_start"] == "2026-07-30T09:00"


async def test_task_oracle_reports_semantic_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/task-items"
        assert request.url.params["due_kind"] == "all"
        assert request.url.params["status"] == "all"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "task-1",
                        "title": "整理资料",
                        "status": "completed",
                        "due_at": None,
                        "timezone": "Asia/Shanghai",
                        "created_by_run_id": "run-1",
                    }
                ],
                "next_cursor": None,
            },
        )

    expectation = ExpectedScheduleItem(
        kind="task",
        title="整理资料",
        status="open",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await evaluate_schedule_expectation(client, expectation)

    assert result["passed"] is False
    assert result["title_match_count"] == 1
    assert result["matched_count"] == 0
