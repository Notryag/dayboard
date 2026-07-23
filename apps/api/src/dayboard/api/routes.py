from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
import json
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile, status
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse
from north import RuntimeStreamEvent
from north.runtime import END_SENTINEL, HEARTBEAT_SENTINEL, REPLAY_GAP_EVENT, StreamBridge
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from uuid import UUID

from dayboard.app.command_dispatcher import RedisCommandDispatcher
from dayboard.agent.presentation import project_runtime_stream_event
from dayboard.app.clarifications import ClarificationStateError, public_conversation_state
from dayboard.app.command_schemas import CommandRequest, CommandRunResponse
from dayboard.app.commands import CommandService, get_command_service
from dayboard.app.conversation_presentations import (
    DayboardConversationMessagePage,
    build_dayboard_presentation,
    dayboard_presentation_parts,
    project_conversation_message_page,
)
from agent_platform.core import (
    ActiveThreadRunError,
    ConversationArchivedError,
    IdempotencyConflictError,
    InteractionConflictError,
)
from dayboard.app.voice import VoiceTranscriptionService
from dayboard.app.reminders import ReminderService
from dayboard.app.schedule_queries import (
    CalendarEntryView,
    InvalidScheduleCursor,
    SchedulePage,
    TaskItemView,
)
from dayboard.app.scheduling_services import (
    build_schedule_query_service,
    build_scheduling_services,
)
from dayboard.app.platform_services import (
    build_conversation_service,
    build_platform_services,
    build_run_service,
)
from dayboard.api.auth import get_tenant_context
from dayboard.api.errors import ApiProblem
from dayboard.api.rate_limit import limiter
from dayboard.config import Settings, get_settings
from agent_platform.core import TenantContext
from dayboard.db.session import get_session
from agent_platform.core import AgentRun, AgentRunEvent
from dayboard.domain.voice import VoiceCapabilities, VoiceTranscript
from dayboard.domain.reminders import ReminderDelivery, ReminderInboxItem
from dayboard.domain.tasks import TaskStatus
from dayboard.domain.calendar import CalendarTimingKind
from dayboard.integrations.speech import AudioInput, SpeechToTextProvider
from dayboard.integrations.audio_probe import (
    AudioMetadataProbe,
    AudioProbeUnavailableError,
    InvalidAudioError,
    PyavAudioMetadataProbe,
)
from dayboard.timezones import resolve_local_date_window
from dayboard.domain.interactions import (
    ClarificationChoiceRequest,
    ClarificationConversationState,
)
from agent_platform.core import ConversationThread
from pydantic import AwareDatetime, BaseModel, Field, model_validator

router = APIRouter()
logger = structlog.get_logger(__name__)

SUPPORTED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
}
MIN_AUDIO_DURATION_MS = 500
AUDIO_METADATA_PROBE = PyavAudioMetadataProbe()


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)


class ScheduleMutationRequest(BaseModel):
    expected_row_version: int = Field(ge=1)


class CalendarEntryUpdateRequest(ScheduleMutationRequest):
    title: str = Field(min_length=1, max_length=240)
    timing_kind: Literal["timed", "anytime"]
    scheduled_date: date | None = None
    start_time: AwareDatetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=10080)

    @model_validator(mode="after")
    def validate_timing(self) -> CalendarEntryUpdateRequest:
        if self.timing_kind == "anytime":
            if (
                self.scheduled_date is None
                or self.start_time is not None
                or self.duration_minutes is not None
            ):
                raise ValueError("anytime entries require only scheduled_date")
        elif (
            self.start_time is None
            or self.duration_minutes is None
            or self.scheduled_date is not None
        ):
            raise ValueError("timed entries require start_time and duration_minutes")
        return self


class TaskItemUpdateRequest(ScheduleMutationRequest):
    title: str = Field(min_length=1, max_length=240)
    due_at: AwareDatetime | None


TERMINAL_RUN_EVENTS = {
    "run_completed",
    "run_failed",
    "run_cancelled",
    "clarification_requested",
}
EXPOSED_RUN_EVENTS = TERMINAL_RUN_EVENTS | {
    "run_created",
    "run_started",
    "tool_call_started",
    "tool_call_completed",
    "tool_call_error",
}


def _terminal_stream_event(
    run: AgentRun,
    *,
    parts: list[dict] | None = None,
) -> tuple[str, dict] | None:
    event_type = {
        "completed": "run_completed",
        "needs_clarification": "clarification_requested",
        "failed": "run_failed",
        "cancelled": "run_cancelled",
    }.get(run.status.value)
    return (
        (event_type, {"content": run.result_message, "parts": parts or []}) if event_type else None
    )


def _validate_aware_range(
    start: datetime | None,
    end: datetime | None,
    start_name: str,
    end_name: str,
) -> None:
    for value, name in ((start, start_name), (end, end_name)):
        if value is not None and value.utcoffset() is None:
            raise HTTPException(status_code=422, detail=f"{name} must include a timezone offset")
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=422, detail=f"{start_name} must be before {end_name}")


def get_command_dispatcher(request: Request) -> RedisCommandDispatcher:
    return request.app.state.command_dispatcher


def get_stream_bridge(request: Request) -> StreamBridge:
    return request.app.state.stream_bridge


def get_speech_provider(request: Request) -> SpeechToTextProvider:
    provider = getattr(request.app.state, "speech_provider", None)
    if provider is None:
        raise ApiProblem(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="VOICE_UNAVAILABLE",
            message="Speech recognition is not configured",
        )
    return provider


def get_audio_metadata_probe() -> AudioMetadataProbe:
    return AUDIO_METADATA_PROBE


@router.get("/health")
async def health(
    session: AsyncSession = Depends(get_session),
    dispatcher: RedisCommandDispatcher = Depends(get_command_dispatcher),
) -> dict[str, str]:
    await session.execute(text("select 1"))
    infrastructure = await dispatcher.health()
    if not all(infrastructure.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", **infrastructure},
        )
    return {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
        "worker": "ok",
    }


@router.get("/api/reminders", response_model=list[ReminderInboxItem])
async def list_reminders(
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> list[ReminderInboxItem]:
    return await ReminderService(session).list_inbox(tenant_context)


@router.post("/api/reminders/{delivery_id}/read", response_model=ReminderDelivery)
async def mark_reminder_read(
    delivery_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> ReminderDelivery:
    reminder, changed = await ReminderService(session).mark_read(tenant_context, delivery_id)
    if reminder is None:
        raise ApiProblem(status_code=404, code="REMINDER_NOT_FOUND", message="Reminder not found")
    if not changed:
        raise ApiProblem(
            status_code=409,
            code="REMINDER_STATE_CONFLICT",
            message="Only delivered reminders can be marked read",
        )
    return reminder


@router.post("/api/reminders/{delivery_id}/retry", response_model=ReminderDelivery)
async def retry_failed_reminder(
    delivery_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> ReminderDelivery:
    reminder, changed = await ReminderService(session).retry_failed(tenant_context, delivery_id)
    if reminder is None:
        raise ApiProblem(status_code=404, code="REMINDER_NOT_FOUND", message="Reminder not found")
    if not changed:
        raise ApiProblem(
            status_code=409,
            code="REMINDER_STATE_CONFLICT",
            message="Only failed reminders can be retried",
        )
    return reminder


@router.get("/api/calendar-entries", response_model=SchedulePage[CalendarEntryView])
async def list_calendar_entries(
    period: Literal["today", "tomorrow"] | None = Query(default=None),
    selected_date: date | None = Query(default=None, alias="date"),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    cursor: str | None = Query(default=None, min_length=1, max_length=1000),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> SchedulePage[CalendarEntryView]:
    if period is not None and selected_date is not None:
        raise HTTPException(status_code=422, detail="period cannot be combined with date")
    if (period is not None or selected_date is not None) and (
        from_time is not None or to_time is not None
    ):
        parameter = "period" if period is not None else "date"
        raise HTTPException(
            status_code=422,
            detail=f"{parameter} cannot be combined with from or to",
        )
    if period is not None:
        local_today = datetime.now(ZoneInfo(tenant_context.timezone)).date()
        selected_date = local_today + timedelta(days=0 if period == "today" else 1)
    if selected_date is not None:
        from_time, to_time = resolve_local_date_window(
            selected_date,
            selected_date,
            tenant_context.timezone,
        )
    _validate_aware_range(from_time, to_time, "from", "to")
    try:
        return await build_schedule_query_service(session).list_calendar_entries(
            tenant_context,
            start_time=from_time,
            end_time=to_time,
            cursor=cursor,
            limit=limit,
        )
    except InvalidScheduleCursor as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/task-items", response_model=SchedulePage[TaskItemView])
async def list_task_items(
    task_status: str = Query(
        default="open",
        alias="status",
        pattern="^(open|completed|cancelled|all)$",
    ),
    due_kind: Literal["all", "dated", "undated"] = Query(default="all"),
    selected_date: date | None = Query(default=None, alias="date"),
    due_from: datetime | None = Query(default=None),
    due_to: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None, min_length=1, max_length=1000),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> SchedulePage[TaskItemView]:
    if selected_date is not None and (due_from is not None or due_to is not None):
        raise HTTPException(
            status_code=422,
            detail="date cannot be combined with due_from or due_to",
        )
    if selected_date is not None and due_kind == "undated":
        raise HTTPException(
            status_code=422,
            detail="date cannot be combined with due_kind=undated",
        )
    if due_kind == "undated" and (due_from is not None or due_to is not None):
        raise HTTPException(
            status_code=422,
            detail="due_kind=undated cannot be combined with due_from or due_to",
        )
    if selected_date is not None:
        due_from, due_to = resolve_local_date_window(
            selected_date,
            selected_date,
            tenant_context.timezone,
        )
        due_kind = "dated"
    _validate_aware_range(due_from, due_to, "due_from", "due_to")
    resolved_status = None if task_status == "all" else TaskStatus(task_status)
    try:
        return await build_schedule_query_service(session).list_task_items(
            tenant_context,
            status=resolved_status,
            due_kind=due_kind,
            due_from=due_from,
            due_to=due_to,
            cursor=cursor,
            limit=limit,
        )
    except InvalidScheduleCursor as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/calendar-entries/{entry_id}/cancel", response_model=CalendarEntryView)
async def cancel_calendar_entry_from_ui(
    entry_id: UUID,
    body: ScheduleMutationRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> CalendarEntryView:
    scope = build_scheduling_services(session)
    service = scope.scheduling
    current = await service.get_calendar_entry(tenant_context, entry_id)
    if current is None:
        raise ApiProblem(
            status_code=404,
            code="CALENDAR_ENTRY_NOT_FOUND",
            message="Calendar entry not found",
        )
    entry = await service.cancel_calendar_entry_from_ui(
        tenant_context,
        entry_id=entry_id,
        expected_row_version=body.expected_row_version,
    )
    if entry is None:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Calendar entry changed before this operation",
        )
    await scope.unit_of_work.commit()
    return CalendarEntryView.from_domain(entry)


@router.post("/api/calendar-entries/{entry_id}/complete", response_model=CalendarEntryView)
async def complete_calendar_entry_from_ui(
    entry_id: UUID,
    body: ScheduleMutationRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> CalendarEntryView:
    scope = build_scheduling_services(session)
    service = scope.scheduling
    current = await service.get_calendar_entry(tenant_context, entry_id)
    if current is None:
        raise ApiProblem(
            status_code=404,
            code="CALENDAR_ENTRY_NOT_FOUND",
            message="Calendar entry not found",
        )
    if current.completed_at is not None:
        return CalendarEntryView.from_domain(current)
    entry = await service.complete_calendar_entry_from_ui(
        tenant_context,
        entry_id=entry_id,
        expected_row_version=body.expected_row_version,
    )
    if entry is None:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Calendar entry changed before this operation",
        )
    await scope.unit_of_work.commit()
    return CalendarEntryView.from_domain(entry)


@router.post("/api/calendar-entries/{entry_id}/reopen", response_model=CalendarEntryView)
async def reopen_calendar_entry_from_ui(
    entry_id: UUID,
    body: ScheduleMutationRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> CalendarEntryView:
    scope = build_scheduling_services(session)
    service = scope.scheduling
    current = await service.get_calendar_entry(tenant_context, entry_id)
    if current is None:
        raise ApiProblem(
            status_code=404,
            code="CALENDAR_ENTRY_NOT_FOUND",
            message="Calendar entry not found",
        )
    if current.completed_at is None:
        return CalendarEntryView.from_domain(current)
    entry = await service.reopen_calendar_entry_from_ui(
        tenant_context,
        entry_id=entry_id,
        expected_row_version=body.expected_row_version,
    )
    if entry is None:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Calendar entry changed before this operation",
        )
    await scope.unit_of_work.commit()
    return CalendarEntryView.from_domain(entry)


@router.put("/api/calendar-entries/{entry_id}", response_model=CalendarEntryView)
async def update_calendar_entry_from_ui(
    entry_id: UUID,
    body: CalendarEntryUpdateRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> CalendarEntryView:
    scope = build_scheduling_services(session)
    service = scope.scheduling
    current = await service.get_calendar_entry(tenant_context, entry_id)
    if current is None:
        raise ApiProblem(
            status_code=404,
            code="CALENDAR_ENTRY_NOT_FOUND",
            message="Calendar entry not found",
        )
    entry = await service.update_calendar_entry_from_ui(
        tenant_context,
        entry_id=entry_id,
        title=body.title,
        timing_kind=CalendarTimingKind(body.timing_kind),
        scheduled_date=body.scheduled_date,
        start_time=body.start_time,
        end_time=(
            body.start_time + timedelta(minutes=body.duration_minutes)
            if body.start_time is not None and body.duration_minutes is not None
            else None
        ),
        expected_row_version=body.expected_row_version,
    )
    if entry is None:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Calendar entry changed before this operation",
        )
    await scope.unit_of_work.commit()
    return CalendarEntryView.from_domain(entry)


async def _set_task_status_from_ui(
    task_id: UUID,
    body: ScheduleMutationRequest,
    target_status: TaskStatus,
    session: AsyncSession,
    tenant_context: TenantContext,
) -> TaskItemView:
    scope = build_scheduling_services(session)
    service = scope.scheduling
    current = await service.get_task_item(tenant_context, task_id)
    if current is None:
        raise ApiProblem(
            status_code=404,
            code="TASK_ITEM_NOT_FOUND",
            message="Task item not found",
        )
    if current.status == target_status:
        return TaskItemView.from_domain(current)
    task = await service.set_task_status_from_ui(
        tenant_context,
        task_id=task_id,
        status=target_status,
        expected_row_version=body.expected_row_version,
    )
    if task is None:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Task item changed before this operation",
        )
    await scope.unit_of_work.commit()
    return TaskItemView.from_domain(task)


@router.post("/api/task-items/{task_id}/complete", response_model=TaskItemView)
async def complete_task_item_from_ui(
    task_id: UUID,
    body: ScheduleMutationRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> TaskItemView:
    return await _set_task_status_from_ui(
        task_id,
        body,
        TaskStatus.completed,
        session,
        tenant_context,
    )


@router.post("/api/task-items/{task_id}/reopen", response_model=TaskItemView)
async def reopen_task_item_from_ui(
    task_id: UUID,
    body: ScheduleMutationRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> TaskItemView:
    scope = build_scheduling_services(session)
    service = scope.scheduling
    current = await service.get_task_item(tenant_context, task_id)
    if current is None:
        raise ApiProblem(
            status_code=404,
            code="TASK_ITEM_NOT_FOUND",
            message="Task item not found",
        )
    if current.status == TaskStatus.open:
        return TaskItemView.from_domain(current)
    if current.status != TaskStatus.completed:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Only completed task items can be reopened",
        )
    task = await service.set_task_status_from_ui(
        tenant_context,
        task_id=task_id,
        status=TaskStatus.open,
        expected_row_version=body.expected_row_version,
    )
    if task is None:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Task item changed before this operation",
        )
    await scope.unit_of_work.commit()
    return TaskItemView.from_domain(task)


@router.put("/api/task-items/{task_id}", response_model=TaskItemView)
async def update_task_item_from_ui(
    task_id: UUID,
    body: TaskItemUpdateRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> TaskItemView:
    scope = build_scheduling_services(session)
    service = scope.scheduling
    current = await service.get_task_item(tenant_context, task_id)
    if current is None:
        raise ApiProblem(
            status_code=404,
            code="TASK_ITEM_NOT_FOUND",
            message="Task item not found",
        )
    task = await service.update_task_item_from_ui(
        tenant_context,
        task_id=task_id,
        title=body.title,
        due_at=body.due_at,
        expected_row_version=body.expected_row_version,
    )
    if task is None:
        raise ApiProblem(
            status_code=409,
            code="SCHEDULE_ITEM_CONFLICT",
            message="Task item changed before this operation",
        )
    await scope.unit_of_work.commit()
    return TaskItemView.from_domain(task)


@router.post("/api/task-items/{task_id}/cancel", response_model=TaskItemView)
async def cancel_task_item_from_ui(
    task_id: UUID,
    body: ScheduleMutationRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> TaskItemView:
    return await _set_task_status_from_ui(
        task_id,
        body,
        TaskStatus.cancelled,
        session,
        tenant_context,
    )


@router.post(
    "/api/command-runs",
    response_model=CommandRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(lambda: get_settings().rate_limit_command)
async def create_command_run(
    request: Request,
    body: CommandRequest,
    tenant_context: TenantContext = Depends(get_tenant_context),
    service: CommandService = Depends(get_command_service),
    dispatcher: RedisCommandDispatcher = Depends(get_command_dispatcher),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
    ),
) -> CommandRunResponse:
    del request
    try:
        creation = await service.create_or_get_command_run(
            tenant_context,
            body,
            idempotency_key=idempotency_key,
        )
    except IdempotencyConflictError as exc:
        raise ApiProblem(
            status_code=status.HTTP_409_CONFLICT,
            code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
        ) from exc
    except ActiveThreadRunError as exc:
        raise ApiProblem(
            status_code=status.HTTP_409_CONFLICT,
            code="COMMAND_ALREADY_IN_PROGRESS",
            message=str(exc),
        ) from exc
    if not creation.created:
        return CommandRunResponse(
            run_id=str(creation.run_id), status=creation.status, thread_id=str(creation.thread_id)
        )
    try:
        await dispatcher.enqueue(creation.run_id)
    except Exception as exc:
        await service.fail_command_run(tenant_context, creation.run_id, exc)
        raise ApiProblem(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="COMMAND_QUEUE_UNAVAILABLE",
            message="Command queue unavailable",
            details={"run_id": str(creation.run_id)},
        ) from exc
    return CommandRunResponse(
        run_id=str(creation.run_id), status=creation.status, thread_id=str(creation.thread_id)
    )


@router.post("/api/threads", response_model=ConversationThread, status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: ThreadCreateRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> ConversationThread:
    platform = build_platform_services(session)
    thread = await platform.conversations.create_thread(
        tenant_context,
        title=body.title,
    )
    await platform.unit_of_work.commit()
    return thread


@router.put("/api/conversation", response_model=ConversationThread)
async def get_or_create_primary_conversation(
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> ConversationThread:
    platform = build_platform_services(session)
    thread = await platform.conversations.get_or_create_primary_thread(tenant_context)
    await platform.unit_of_work.commit()
    return thread


@router.get(
    "/api/threads/{thread_id}/messages",
    response_model=DayboardConversationMessagePage,
)
async def get_thread_messages(
    thread_id: UUID,
    before: UUID | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> DayboardConversationMessagePage:
    try:
        return project_conversation_message_page(
            await build_conversation_service(session).list_message_page(
                tenant_context,
                thread_id,
                before=before,
                limit=limit,
            )
        )
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc


@router.get(
    "/api/threads/{thread_id}/state",
    response_model=ClarificationConversationState | None,
)
async def get_thread_state(
    thread_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> ClarificationConversationState | None:
    try:
        state = await build_conversation_service(session).get_state(tenant_context, thread_id)
        return public_conversation_state(state)
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc


@router.post(
    "/api/voice/transcriptions",
    response_model=VoiceTranscript,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(lambda: get_settings().rate_limit_voice)
async def create_voice_transcription(
    request: Request,
    audio: UploadFile = File(...),
    language: str | None = Form(default="zh"),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
    provider: SpeechToTextProvider = Depends(get_speech_provider),
    audio_probe: AudioMetadataProbe = Depends(get_audio_metadata_probe),
    settings: Settings = Depends(get_settings),
) -> VoiceTranscript:
    del request
    content_type = (audio.content_type or "").partition(";")[0].strip().lower()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise ApiProblem(
            status_code=415,
            code="VOICE_FORMAT_UNSUPPORTED",
            message="Unsupported audio format",
        )
    content = await audio.read(settings.asr_max_upload_bytes + 1)
    await audio.close()
    if not content:
        raise ApiProblem(
            status_code=422,
            code="VOICE_EMPTY",
            message="Audio file is empty",
        )
    if len(content) > settings.asr_max_upload_bytes:
        raise ApiProblem(
            status_code=413,
            code="VOICE_TOO_LARGE",
            message="Audio file is too large",
            details={"max_upload_bytes": settings.asr_max_upload_bytes},
        )
    try:
        metadata = await audio_probe.inspect(content, content_type=content_type)
    except InvalidAudioError as exc:
        raise ApiProblem(
            status_code=422,
            code="VOICE_INVALID_AUDIO",
            message="Audio file could not be read",
        ) from exc
    except AudioProbeUnavailableError as exc:
        raise ApiProblem(
            status_code=503,
            code="VOICE_VALIDATION_UNAVAILABLE",
            message="Audio validation is temporarily unavailable",
        ) from exc
    if metadata.duration_ms < MIN_AUDIO_DURATION_MS:
        raise ApiProblem(
            status_code=422,
            code="VOICE_TOO_SHORT",
            message="Audio recording is too short",
            details={"min_duration_ms": MIN_AUDIO_DURATION_MS},
        )
    if metadata.duration_ms > settings.asr_max_audio_seconds * 1000:
        raise ApiProblem(
            status_code=413,
            code="VOICE_TOO_LONG",
            message="Audio recording is too long",
            details={"max_duration_seconds": settings.asr_max_audio_seconds},
        )
    try:
        return await VoiceTranscriptionService(session).transcribe(
            tenant_context,
            provider,
            AudioInput(
                content=content,
                content_type=content_type,
                filename=audio.filename,
                duration_ms=metadata.duration_ms,
            ),
            language=language,
        )
    except Exception as exc:
        raise ApiProblem(
            status_code=502,
            code="VOICE_TRANSCRIPTION_FAILED",
            message="Speech transcription failed",
        ) from exc


@router.get("/api/voice/capabilities", response_model=VoiceCapabilities)
async def get_voice_capabilities(
    request: Request,
    tenant_context: TenantContext = Depends(get_tenant_context),
    settings: Settings = Depends(get_settings),
) -> VoiceCapabilities:
    del tenant_context
    return VoiceCapabilities(
        available=getattr(request.app.state, "speech_provider", None) is not None,
        max_duration_seconds=settings.asr_max_audio_seconds,
        max_upload_bytes=settings.asr_max_upload_bytes,
        supported_content_types=sorted(SUPPORTED_AUDIO_TYPES),
    )


@router.get(
    "/api/voice/transcriptions/{transcript_id}",
    response_model=VoiceTranscript,
)
async def get_voice_transcription(
    transcript_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> VoiceTranscript:
    transcript = await VoiceTranscriptionService(session).get(tenant_context, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="Voice transcript not found")
    return transcript


@router.post(
    "/api/threads/{thread_id}/command-runs",
    response_model=CommandRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(lambda: get_settings().rate_limit_command)
async def create_thread_command_run(
    request: Request,
    thread_id: UUID,
    body: CommandRequest,
    tenant_context: TenantContext = Depends(get_tenant_context),
    service: CommandService = Depends(get_command_service),
    dispatcher: RedisCommandDispatcher = Depends(get_command_dispatcher),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CommandRunResponse:
    del request
    try:
        creation = await service.create_or_get_command_run(
            tenant_context,
            body,
            idempotency_key=idempotency_key,
            thread_id=thread_id,
        )
    except ConversationArchivedError as exc:
        raise ApiProblem(
            status_code=409,
            code="THREAD_ARCHIVED",
            message=str(exc),
        ) from exc
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc
    except IdempotencyConflictError as exc:
        raise ApiProblem(
            status_code=409,
            code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
        ) from exc
    except ActiveThreadRunError as exc:
        raise ApiProblem(
            status_code=409,
            code="COMMAND_ALREADY_IN_PROGRESS",
            message=str(exc),
        ) from exc
    if creation.created:
        try:
            await dispatcher.enqueue(creation.run_id)
        except Exception as exc:
            await service.fail_command_run(tenant_context, creation.run_id, exc)
            raise ApiProblem(
                status_code=503,
                code="COMMAND_QUEUE_UNAVAILABLE",
                message="Command queue unavailable",
                details={"run_id": str(creation.run_id)},
            ) from exc
    return CommandRunResponse(
        run_id=str(creation.run_id),
        status=creation.status,
        thread_id=str(creation.thread_id),
    )


@router.post(
    "/api/threads/{thread_id}/clarification-responses",
    response_model=CommandRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(lambda: get_settings().rate_limit_command)
async def respond_to_clarification(
    request: Request,
    thread_id: UUID,
    body: ClarificationChoiceRequest,
    tenant_context: TenantContext = Depends(get_tenant_context),
    service: CommandService = Depends(get_command_service),
    dispatcher: RedisCommandDispatcher = Depends(get_command_dispatcher),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CommandRunResponse:
    del request
    try:
        creation = await service.create_or_get_clarification_run(
            tenant_context,
            thread_id=thread_id,
            state_version=body.state_version,
            option_key=body.option_key,
            idempotency_key=idempotency_key,
        )
    except ConversationArchivedError as exc:
        raise ApiProblem(
            status_code=409,
            code="THREAD_ARCHIVED",
            message=str(exc),
        ) from exc
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc
    except (
        ClarificationStateError,
        IdempotencyConflictError,
        InteractionConflictError,
        ActiveThreadRunError,
    ) as exc:
        raise ApiProblem(
            status_code=409,
            code="CLARIFICATION_CONFLICT",
            message=str(exc),
        ) from exc

    if creation.created:
        try:
            await dispatcher.enqueue(creation.run_id)
        except Exception as exc:
            await service.fail_command_run(tenant_context, creation.run_id, exc)
            raise ApiProblem(
                status_code=503,
                code="COMMAND_QUEUE_UNAVAILABLE",
                message="Command queue unavailable",
                details={"run_id": str(creation.run_id)},
            ) from exc
    return CommandRunResponse(
        run_id=str(creation.run_id),
        status=creation.status,
        thread_id=str(creation.thread_id),
    )


@router.get("/api/runs/{run_id}", response_model=AgentRun)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> AgentRun:
    run = await build_run_service(session).get_run(tenant_context, run_id)
    if run is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")
    return run


@router.get("/api/threads/{thread_id}/active-run", response_model=AgentRun | None)
async def get_active_thread_run(
    thread_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> AgentRun | None:
    try:
        await build_conversation_service(session).require_thread(tenant_context, thread_id)
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc
    return await build_run_service(session).get_active_thread_run(tenant_context, thread_id)


@router.post("/api/runs/{run_id}/cancel", response_model=AgentRun)
async def cancel_run(
    run_id: UUID,
    dispatcher: RedisCommandDispatcher = Depends(get_command_dispatcher),
    stream_bridge: StreamBridge = Depends(get_stream_bridge),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> AgentRun:
    platform = build_platform_services(session)
    service = platform.runs
    run = await service.get_run_for_update(tenant_context, run_id)
    if run is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")
    transitioned = await service.mark_cancelled(
        tenant_context,
        run,
        event_content="请求已取消",
    )
    if transitioned:
        conversations = platform.conversations
        existing_message = await conversations.get_assistant_message_for_run(tenant_context, run.id)
        parts = dayboard_presentation_parts(
            existing_message.presentation if existing_message is not None else None
        )
        await conversations.upsert_assistant_message(
            tenant_context,
            thread_id=run.thread_id,
            run_id=run.id,
            content=run.result_message or "请求已取消",
            presentation=build_dayboard_presentation(parts),
        )
    await platform.unit_of_work.commit()
    if transitioned:
        try:
            await stream_bridge.publish(
                str(run.id),
                "run_cancelled",
                {
                    "content": run.result_message or "请求已取消",
                    "parts": parts,
                },
            )
        except Exception:
            logger.warning(
                "dayboard.run_stream.cancel_publish_failed",
                run_id=str(run.id),
                exc_info=True,
            )
    try:
        await dispatcher.cancel(run_id)
    except Exception:
        pass
    cancelled = await service.get_run(tenant_context, run_id)
    if cancelled is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")
    return cancelled


@router.get("/api/runs/{run_id}/events", response_model=list[AgentRunEvent])
async def get_run_events(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> list[AgentRunEvent]:
    service = build_run_service(session)
    if await service.get_run(tenant_context, run_id) is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")
    return await service.list_events(tenant_context, run_id)


@router.get("/api/runs/{run_id}/events/stream")
async def stream_run_events(
    run_id: UUID,
    request: Request,
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
        pattern=r"^\d{1,20}-\d{1,20}$",
        max_length=41,
    ),
    stream_bridge: StreamBridge = Depends(get_stream_bridge),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> StreamingResponse:
    service = build_run_service(session)
    run = await service.get_run(tenant_context, run_id)
    if run is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")

    async def event_stream() -> AsyncIterator[str]:
        async def terminal_event(current_run: AgentRun) -> tuple[str, dict] | None:
            if current_run.status.value not in {
                "completed",
                "needs_clarification",
                "failed",
                "cancelled",
            }:
                return None
            assistant = await build_conversation_service(session).get_assistant_message_for_run(
                tenant_context, run_id
            )
            parts = dayboard_presentation_parts(
                assistant.presentation if assistant is not None else None
            )
            return _terminal_stream_event(current_run, parts=parts)

        terminal = await terminal_event(run)
        if terminal is not None:
            event_type, data = terminal
            yield (f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n")
            return

        async for entry in stream_bridge.subscribe(
            str(run_id),
            last_event_id=last_event_id,
        ):
            if await request.is_disconnected():
                return
            if entry == HEARTBEAT_SENTINEL:
                session.expire_all()
                latest = await service.get_run(tenant_context, run_id)
                terminal = await terminal_event(latest) if latest is not None else None
                if terminal is not None:
                    event_type, data = terminal
                    yield (f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n")
                    return
                yield ": keep-alive\n\n"
                continue
            if entry == END_SENTINEL:
                yield "event: end\ndata: {}\n\n"
                return
            if entry.event == REPLAY_GAP_EVENT:
                logger.warning(
                    "dayboard.run_stream.replay_gap",
                    run_id=str(run_id),
                    first_available_event_id=entry.data.get("first_available_event_id"),
                )
                yield "event: stream_replay_gap\ndata: {}\n\n"
                continue

            projected = None
            if entry.event == "messages-tuple":
                projected = project_runtime_stream_event(
                    RuntimeStreamEvent(
                        mode="messages",
                        data=entry.data,
                        namespace=entry.namespace,
                    )
                )
                if projected is None:
                    continue
                yield (
                    f"id: {entry.id}\n"
                    f"event: {projected.event_type}\n"
                    "data: "
                    f"{json.dumps(projected.data, ensure_ascii=False, separators=(',', ':'))}\n\n"
                )
                continue
            if entry.event not in EXPOSED_RUN_EVENTS:
                continue
            yield (
                f"id: {entry.id}\n"
                f"event: {entry.event}\n"
                "data: "
                f"{json.dumps(entry.data, ensure_ascii=False, separators=(',', ':'))}\n\n"
            )
            if entry.event in TERMINAL_RUN_EVENTS:
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
