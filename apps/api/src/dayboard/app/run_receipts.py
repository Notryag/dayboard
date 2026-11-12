"""Dayboard's durable scheduling receipts, committed with each Agent mutation."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

from agent_platform.application import ConversationService
from agent_platform.core import AgentRun, AgentRunEventCategory, EventExtensionEnvelope, UserContext
from agent_platform.ports import PlatformUnitOfWork, RunUnitOfWork
from dayboard.app.conversation_presentations import (
    ScheduleResultPart,
    build_dayboard_presentation,
    dayboard_presentation_parts,
)


RECEIPT_KIND = "dayboard.schedule-receipt"
RECEIPT_EVENT = "dayboard.schedule_committed"


class ScheduleReceipt(BaseModel):
    operation_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: dict[str, JsonValue]
    part: ScheduleResultPart


async def load_run_receipts(
    unit_of_work: RunUnitOfWork,
    context: UserContext,
    run_id: UUID,
) -> list[ScheduleReceipt]:
    receipts = []
    for event in await unit_of_work.events.list_for_run(context, run_id):
        extension = event.extension
        if (
            event.event_type == RECEIPT_EVENT
            and extension is not None
            and extension.kind == RECEIPT_KIND
            and extension.schema_version == 1
        ):
            receipts.append(ScheduleReceipt.model_validate(extension.payload))
    return receipts


def merge_receipt_parts(existing: list[dict], receipts: list[ScheduleReceipt]) -> list[dict]:
    parts = {(part["item"]["kind"], part["item"]["value"]["id"]): part for part in existing}
    for receipt in receipts:
        part = receipt.part.model_dump(mode="json")
        parts[(part["item"]["kind"], part["item"]["value"]["id"])] = part
    return list(parts.values())


async def save_run_receipt(
    unit_of_work: PlatformUnitOfWork,
    context: UserContext,
    run: AgentRun,
    receipt: ScheduleReceipt,
) -> None:
    """Caller holds the Run lock and owns the shared scheduling transaction."""
    await unit_of_work.events.append(
        context,
        thread_id=run.thread_id,
        run_id=run.id,
        event_type=RECEIPT_EVENT,
        category=AgentRunEventCategory.outputs,
        extension=EventExtensionEnvelope(
            kind=RECEIPT_KIND,
            schema_version=1,
            payload=receipt.model_dump(mode="json"),
        ),
    )
    conversations = ConversationService(unit_of_work)
    existing = await conversations.get_assistant_message_for_run(context, run.id)
    parts = merge_receipt_parts(
        dayboard_presentation_parts(existing.presentation if existing else None),
        [receipt],
    )
    await conversations.upsert_assistant_message(
        context,
        thread_id=run.thread_id,
        run_id=run.id,
        content="",
        presentation=build_dayboard_presentation(parts),
    )
