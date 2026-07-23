from __future__ import annotations

from pydantic import ValidationError
import pytest

from agent_platform.core import PresentationEnvelope
from dayboard.app.conversation_presentations import (
    build_dayboard_presentation,
    dayboard_presentation_parts,
    project_dayboard_presentation,
)


def _task_part(*, task_id: str = "11111111-1111-4111-8111-111111111111") -> dict:
    return {
        "tool_call_id": "call-1",
        "operation": "task_item_created",
        "item": {
            "kind": "task",
            "value": {
                "id": task_id,
                "row_version": 1,
                "title": "提交周报",
                "due_at": None,
                "timezone": "Asia/Shanghai",
                "reminder": None,
                "status": "open",
                "created_by_run_id": None,
                "created_at": "2026-07-20T10:00:00Z",
                "updated_at": "2026-07-20T10:00:00Z",
            },
        },
    }


def test_dayboard_presentation_round_trips_a_typed_schedule_result() -> None:
    presentation = build_dayboard_presentation([_task_part()])

    assert presentation.kind == "dayboard.schedule-results"
    assert presentation.schema_version == 1
    assert dayboard_presentation_parts(presentation) == [_task_part()]


def test_unknown_product_presentation_is_not_interpreted_as_dayboard_data() -> None:
    presentation = PresentationEnvelope(
        kind="another-product.results",
        schema_version=3,
        payload={"parts": [{"untrusted": True}]},
    )

    assert project_dayboard_presentation(presentation) is None
    assert dayboard_presentation_parts(presentation) == []


def test_malformed_known_dayboard_presentation_fails_loudly() -> None:
    presentation = PresentationEnvelope(
        kind="dayboard.schedule-results",
        schema_version=1,
        payload={"parts": [{"operation": "task_item_created"}]},
    )

    with pytest.raises(ValidationError):
        project_dayboard_presentation(presentation)
