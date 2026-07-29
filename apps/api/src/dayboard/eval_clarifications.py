from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field, model_validator

from dayboard.eval_oracles import ExpectedScheduleItem, render_template


class ClarificationResumeExpectation(BaseModel):
    expected_tools: dict[str, int] = Field(default_factory=dict)
    expected_status: str = "completed"
    forbidden_tools: tuple[str, ...] = ()
    max_total_tokens: int | None = Field(default=None, gt=0)
    expected_schedule: tuple[ExpectedScheduleItem, ...] = ()


class ClarificationFlowExpectation(BaseModel):
    presentation_type: Literal["suggested_choice", "calendar_entry_choice"]
    option_count: int = Field(ge=1, le=10)
    option_titles: tuple[str, ...] | None = None
    option_local_starts: tuple[str, ...] | None = None
    select_index: int = Field(default=0, ge=0, le=9)
    resume: ClarificationResumeExpectation

    @model_validator(mode="after")
    def validate_option_expectations(self) -> ClarificationFlowExpectation:
        for values, name in (
            (self.option_titles, "option_titles"),
            (self.option_local_starts, "option_local_starts"),
        ):
            if values is not None and len(values) != self.option_count:
                raise ValueError(f"{name} must contain option_count values")
        if self.select_index >= self.option_count:
            raise ValueError("select_index must identify an expected option")
        if self.presentation_type != "calendar_entry_choice" and self.option_local_starts:
            raise ValueError("only calendar choices can assert option_local_starts")
        return self


def _local_minute(value: object, timezone: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError(f"clarification API returned a naive datetime: {value}")
    zone = ZoneInfo(timezone) if isinstance(timezone, str) else ZoneInfo("Asia/Shanghai")
    return parsed.astimezone(zone).replace(tzinfo=None).isoformat(timespec="minutes")


def _option_snapshot(option: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": option.get("key"),
        "title": option.get("title", option.get("label")),
        "timing_kind": option.get("timing_kind"),
        "scheduled_date": option.get("scheduled_date"),
        "local_start": _local_minute(option.get("start_time"), option.get("timezone")),
        "local_end": _local_minute(option.get("end_time"), option.get("timezone")),
    }


async def inspect_clarification(
    client: httpx.AsyncClient,
    *,
    thread_id: str,
    source_run_id: str,
    expectation: ClarificationFlowExpectation,
    variables: dict[str, str],
) -> dict[str, Any]:
    response = await client.get(f"/api/threads/{thread_id}/state")
    response.raise_for_status()
    state = response.json()
    if not isinstance(state, dict):
        return {"passed": False, "reason": "missing_state"}

    interaction = state.get("interaction")
    payload = interaction.get("payload") if isinstance(interaction, dict) else None
    presentation = payload.get("presentation") if isinstance(payload, dict) else None
    options = presentation.get("options") if isinstance(presentation, dict) else None
    snapshots = (
        [_option_snapshot(option) for option in options if isinstance(option, dict)]
        if isinstance(options, list)
        else []
    )
    expected_titles = (
        [render_template(value, variables) for value in expectation.option_titles]
        if expectation.option_titles is not None
        else None
    )
    expected_starts = (
        [render_template(value, variables) for value in expectation.option_local_starts]
        if expectation.option_local_starts is not None
        else None
    )
    checks = {
        "source_run": isinstance(interaction, dict)
        and interaction.get("source_run_id") == source_run_id,
        "presentation_type": isinstance(presentation, dict)
        and presentation.get("type") == expectation.presentation_type,
        "option_count": len(snapshots) == expectation.option_count,
        "option_titles": expected_titles is None
        or [option["title"] for option in snapshots] == expected_titles,
        "option_local_starts": expected_starts is None
        or [option["local_start"] for option in snapshots] == expected_starts,
    }
    selected = snapshots[expectation.select_index] if len(snapshots) > expectation.select_index else {}
    selected_key = selected.get("key")
    return {
        "passed": all(checks.values()) and isinstance(selected_key, str),
        "checks": checks,
        "state_version": state.get("version"),
        "selected_option_key": selected_key,
        "options": snapshots,
    }


async def clarification_is_consumed(client: httpx.AsyncClient, *, thread_id: str) -> bool:
    response = await client.get(f"/api/threads/{thread_id}/state")
    response.raise_for_status()
    return response.json() is None
