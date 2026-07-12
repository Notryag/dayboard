from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile, status
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from dayboard.app.command_dispatcher import RedisCommandDispatcher
from dayboard.app.conversations import (
    ClarificationStateError,
    ConversationService,
    conversation_thread_from_row,
)
from dayboard.app.command_schemas import CommandRequest, CommandRunResponse
from dayboard.app.commands import CommandService, IdempotencyConflictError, get_command_service
from dayboard.app.runs import ActiveThreadRunError, AgentRunService
from dayboard.app.voice import VoiceTranscriptionService
from dayboard.app.reminders import ReminderService
from dayboard.app.schedule_queries import (
    CalendarEntryView,
    InvalidScheduleCursor,
    SchedulePage,
    ScheduleQueryService,
    TaskItemView,
)
from dayboard.api.auth import get_tenant_context
from dayboard.api.errors import ApiProblem
from dayboard.api.rate_limit import limiter
from dayboard.config import Settings, get_settings
from dayboard.context import TenantContext
from dayboard.db.session import get_session
from dayboard.domain.runs import AgentRun, AgentRunEvent
from dayboard.domain.voice import VoiceTranscript
from dayboard.domain.reminders import ReminderDelivery
from dayboard.domain.tasks import TaskStatus
from dayboard.integrations.speech import AudioInput, SpeechToTextProvider
from dayboard.domain.interactions import ClarificationChoiceRequest
from dayboard.domain.conversations import (
    ConversationMessage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from pydantic import BaseModel, Field

router = APIRouter()

SUPPORTED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
}


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)


TERMINAL_RUN_EVENTS = {
    "run_completed",
    "run_failed",
    "run_cancelled",
    "clarification_requested",
}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "needs_clarification"}


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


def get_speech_provider(request: Request) -> SpeechToTextProvider:
    provider = getattr(request.app.state, "speech_provider", None)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech recognition provider is not configured",
        )
    return provider


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


@router.get("/api/reminders", response_model=list[ReminderDelivery])
async def list_reminders(
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> list[ReminderDelivery]:
    return await ReminderService(session).list_for_user(tenant_context)


@router.get("/api/calendar-entries", response_model=SchedulePage[CalendarEntryView])
async def list_calendar_entries(
    period: Literal["today", "tomorrow"] | None = Query(default=None),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    cursor: str | None = Query(default=None, min_length=1, max_length=1000),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> SchedulePage[CalendarEntryView]:
    if period is not None:
        if from_time is not None or to_time is not None:
            raise HTTPException(status_code=422, detail="period cannot be combined with from or to")
        local_now = datetime.now(ZoneInfo(tenant_context.timezone))
        day_offset = 0 if period == "today" else 1
        from_time = (local_now + timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        to_time = from_time + timedelta(days=1)
    _validate_aware_range(from_time, to_time, "from", "to")
    try:
        return await ScheduleQueryService(session).list_calendar_entries(
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
    due_from: datetime | None = Query(default=None),
    due_to: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None, min_length=1, max_length=1000),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> SchedulePage[TaskItemView]:
    _validate_aware_range(due_from, due_to, "due_from", "due_to")
    resolved_status = None if task_status == "all" else TaskStatus(task_status)
    try:
        return await ScheduleQueryService(session).list_task_items(
            tenant_context,
            status=resolved_status,
            due_from=due_from,
            due_to=due_to,
            cursor=cursor,
            limit=limit,
        )
    except InvalidScheduleCursor as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        await dispatcher.enqueue(creation.run_id, tenant_context, body)
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
    row = await ConversationService(session).create_thread(tenant_context, title=body.title)
    await session.commit()
    await session.refresh(row)
    return conversation_thread_from_row(row)


@router.get("/api/threads/{thread_id}/messages", response_model=list[ConversationMessage])
async def get_thread_messages(
    thread_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> list[ConversationMessage]:
    try:
        return await ConversationService(session).list_messages(tenant_context, thread_id)
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc


@router.get("/api/threads/{thread_id}/state", response_model=ConversationState | None)
async def get_thread_state(
    thread_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> ConversationState | None:
    try:
        return await ConversationService(session).get_state(tenant_context, thread_id)
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
    settings: Settings = Depends(get_settings),
) -> VoiceTranscript:
    del request
    content_type = (audio.content_type or "").lower()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    content = await audio.read(settings.asr_max_upload_bytes + 1)
    await audio.close()
    if not content:
        raise HTTPException(status_code=422, detail="Audio file is empty")
    if len(content) > settings.asr_max_upload_bytes:
        raise HTTPException(status_code=413, detail="Audio file is too large")
    try:
        return await VoiceTranscriptionService(session).transcribe(
            tenant_context,
            provider,
            AudioInput(
                content=content,
                content_type=content_type,
                filename=audio.filename,
            ),
            language=language,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Speech transcription failed") from exc


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
            await dispatcher.enqueue(creation.run_id, tenant_context, body)
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
        choice = await service.conversations.resolve_clarification_choice(
            tenant_context,
            thread_id=thread_id,
            state_version=body.state_version,
            option_key=body.option_key,
        )
        request = CommandRequest(message=choice.agent_message)
        creation = await service.create_or_get_command_run(
            tenant_context,
            request,
            idempotency_key=idempotency_key,
            thread_id=thread_id,
            conversation_message=choice.display_message,
        )
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc
    except (ClarificationStateError, IdempotencyConflictError, ActiveThreadRunError) as exc:
        raise ApiProblem(
            status_code=409,
            code="CLARIFICATION_CONFLICT",
            message=str(exc),
        ) from exc

    if creation.created:
        try:
            await dispatcher.enqueue(creation.run_id, tenant_context, request)
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
    run = await AgentRunService(session).get_run(tenant_context, run_id)
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
        await ConversationService(session).require_thread(tenant_context, thread_id)
    except LookupError as exc:
        raise ApiProblem(
            status_code=404,
            code="THREAD_NOT_FOUND",
            message="Conversation thread not found",
        ) from exc
    return await AgentRunService(session).get_active_thread_run(tenant_context, thread_id)


@router.post("/api/runs/{run_id}/cancel", response_model=AgentRun)
async def cancel_run(
    run_id: UUID,
    dispatcher: RedisCommandDispatcher = Depends(get_command_dispatcher),
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> AgentRun:
    service = AgentRunService(session)
    run = await service.get_run_row(tenant_context, run_id)
    if run is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")
    transitioned = await service.mark_cancelled(tenant_context, run)
    if transitioned:
        await ConversationService(session).append_message(
            tenant_context,
            thread_id=run.thread_id,
            run_id=run.id,
            role=ConversationRole.assistant,
            content=run.result_message or "请求已取消",
            message_metadata={"status": "cancelled"},
        )
    await session.commit()
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
    service = AgentRunService(session)
    if await service.get_run(tenant_context, run_id) is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")
    return await service.list_events(tenant_context, run_id)


@router.get("/api/runs/{run_id}/events/stream")
async def stream_run_events(
    run_id: UUID,
    request: Request,
    after_seq: int = 0,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_tenant_context),
) -> StreamingResponse:
    service = AgentRunService(session)
    run = await service.get_run(tenant_context, run_id)
    if run is None:
        raise ApiProblem(status_code=404, code="RUN_NOT_FOUND", message="Run not found")

    async def event_stream() -> AsyncIterator[str]:
        cursor = max(after_seq, 0)
        idle_polls = 0
        while not await request.is_disconnected():
            events = await service.list_events(tenant_context, run_id, after_seq=cursor)
            if events:
                idle_polls = 0
                for event in events:
                    cursor = event.seq
                    yield (
                        f"id: {event.seq}\n"
                        f"event: {event.event_type}\n"
                        f"data: {event.model_dump_json()}\n\n"
                    )
                    if event.event_type in TERMINAL_RUN_EVENTS:
                        return
            else:
                if run.status.value in TERMINAL_RUN_STATUSES:
                    return
                idle_polls += 1
                if idle_polls >= 30:
                    yield ": keep-alive\n\n"
                    idle_polls = 0
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
