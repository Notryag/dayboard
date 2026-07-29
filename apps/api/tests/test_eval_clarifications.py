from __future__ import annotations

from datetime import datetime

import httpx

from dayboard import eval_runner
from dayboard.eval_clarifications import ClarificationFlowExpectation, inspect_clarification
from dayboard.eval_oracles import BEIJING_TIMEZONE, EvalTemplateContext, ExpectedScheduleItem


async def test_clarification_oracle_validates_source_and_calendar_options() -> None:
    templates = EvalTemplateContext.capture(
        now=datetime(2026, 7, 29, 12, 0, tzinfo=BEIJING_TIMEZONE)
    )
    expectation = ClarificationFlowExpectation.model_validate(
        {
            "presentation_type": "calendar_entry_choice",
            "option_count": 2,
            "option_titles": ["同步{tag}", "同步{tag}"],
            "option_local_starts": [
                "{tomorrow}T09:00",
                "{day_after_tomorrow}T09:00",
            ],
            "select_index": 0,
            "resume": {"expected_tools": {"cancel_calendar_entry": 1}},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/threads/thread-1/state"
        return httpx.Response(
            200,
            json={
                "version": 3,
                "interaction": {
                    "source_run_id": "source-run-1",
                    "payload": {
                        "presentation": {
                            "type": "calendar_entry_choice",
                            "options": [
                                {
                                    "key": "candidate_1",
                                    "title": "同步abc123",
                                    "timing_kind": "timed",
                                    "start_time": "2026-07-30T01:00:00+00:00",
                                    "end_time": "2026-07-30T02:00:00+00:00",
                                    "timezone": "Asia/Shanghai",
                                },
                                {
                                    "key": "candidate_2",
                                    "title": "同步abc123",
                                    "timing_kind": "timed",
                                    "start_time": "2026-07-31T01:00:00+00:00",
                                    "end_time": "2026-07-31T02:00:00+00:00",
                                    "timezone": "Asia/Shanghai",
                                },
                            ],
                        }
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await inspect_clarification(
            client,
            thread_id="thread-1",
            source_run_id="source-run-1",
            expectation=expectation,
            variables=templates.variables(tag="abc123"),
        )

    assert result["passed"] is True
    assert result["state_version"] == 3
    assert result["selected_option_key"] == "candidate_1"
    assert result["options"][1]["local_start"] == "2026-07-31T09:00"


async def test_clarification_flow_resumes_run_and_consumes_interaction() -> None:
    templates = EvalTemplateContext.capture(
        now=datetime(2026, 7, 29, 12, 0, tzinfo=BEIJING_TIMEZONE)
    )
    flow = ClarificationFlowExpectation(
        presentation_type="calendar_entry_choice",
        option_count=1,
        option_titles=("同步{tag}",),
        option_local_starts=("{tomorrow}T09:00",),
        select_index=0,
        resume={
            "expected_tools": {"cancel_calendar_entry": 1},
            "expected_schedule": (
                ExpectedScheduleItem(
                    kind="calendar",
                    title="同步{tag}",
                    status="cancelled",
                    timing_kind="timed",
                    local_start="{tomorrow}T09:00",
                    local_end="{tomorrow}T10:00",
                ),
            ),
        },
    )
    state_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal state_reads
        if request.url.path == "/api/threads/thread-1/state":
            state_reads += 1
            if state_reads > 1:
                return httpx.Response(
                    200,
                    content=b"null",
                    headers={"content-type": "application/json"},
                )
            return httpx.Response(
                200,
                json={
                    "version": 4,
                    "interaction": {
                        "source_run_id": "source-run-1",
                        "payload": {
                            "presentation": {
                                "type": "calendar_entry_choice",
                                "options": [
                                    {
                                        "key": "candidate_1",
                                        "title": "同步abc123",
                                        "timing_kind": "timed",
                                        "start_time": "2026-07-30T01:00:00+00:00",
                                        "end_time": "2026-07-30T02:00:00+00:00",
                                        "timezone": "Asia/Shanghai",
                                    }
                                ],
                            }
                        },
                    },
                },
            )
        if request.url.path == "/api/threads/thread-1/clarification-responses":
            assert request.method == "POST"
            assert request.headers["Idempotency-Key"] == (
                "eval:execution-1:case-1:clarification:1"
            )
            return httpx.Response(202, json={"run_id": "resume-run-1"})
        if request.url.path == "/api/runs/resume-run-1":
            return httpx.Response(200, json={"id": "resume-run-1", "status": "completed"})
        if request.url.path == "/api/runs/resume-run-1/events":
            return httpx.Response(
                200,
                json=[
                    {
                        "event_type": "tool_call_completed",
                        "extension": {
                            "kind": "north.tool-call",
                            "schema_version": 1,
                            "payload": {"tool_name": "cancel_calendar_entry"},
                        },
                    }
                ],
            )
        if request.url.path == "/api/calendar-entries":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "entry-1",
                            "title": "同步abc123",
                            "status": "cancelled",
                            "timing_kind": "timed",
                            "scheduled_date": None,
                            "start_time": "2026-07-30T01:00:00+00:00",
                            "end_time": "2026-07-30T02:00:00+00:00",
                            "timezone": "Asia/Shanghai",
                            "created_by_run_id": "setup-run-1",
                        }
                    ],
                    "next_cursor": None,
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await eval_runner._run_clarification_flow(
            client,
            thread_id="thread-1",
            source_run_id="source-run-1",
            flow=flow,
            variables=templates.variables(tag="abc123"),
            execution_id="execution-1",
            case_id="case-1",
            turn_index=1,
            timeout=1,
        )

    assert result["passed"] is True
    assert result["interaction_consumed"] is True
    assert result["resume"]["run_id"] == "resume-run-1"
    assert result["resume"]["schedule_match"] is True
