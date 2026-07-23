from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from agent_platform.application import CommandSubmissionService
from agent_platform.core import (
    AgentRun,
    AgentRunStatus,
    ConversationThread,
    IdempotencyClaim,
    IdempotencyConflictError,
    IdempotencyRecord,
    TenantContext,
)


def _context() -> TenantContext:
    return TenantContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )


def _thread(context: TenantContext) -> ConversationThread:
    now = datetime.now(UTC)
    return ConversationThread(
        id=uuid4(),
        tenant_id=context.tenant_id,
        owner_user_id=context.user_id,
        title="记录",
        status="active",
        summary=None,
        created_at=now,
        updated_at=now,
    )


def _run(context: TenantContext, thread_id, run_id=None) -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        id=run_id or uuid4(),
        tenant_id=context.tenant_id,
        owner_user_id=context.user_id,
        thread_id=thread_id,
        status=AgentRunStatus.queued,
        input_message="记录今天的数据",
        result_message=None,
        created_at=now,
        updated_at=now,
    )


def _claim(context: TenantContext, *, request_hash: str, created: bool) -> IdempotencyClaim:
    return IdempotencyClaim(
        record=IdempotencyRecord(
            id=uuid4(),
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            key="request-1",
            request_hash=request_hash,
            run_id=uuid4(),
            created_at=datetime.now(UTC),
        ),
        created=created,
    )


def _unit_of_work():
    return SimpleNamespace(
        threads=SimpleNamespace(
            create=AsyncMock(),
            get=AsyncMock(),
            get_or_create_primary=AsyncMock(),
            update_summary=AsyncMock(),
        ),
        messages=SimpleNamespace(
            append_once=AsyncMock(),
            upsert_assistant=AsyncMock(),
            get_assistant_for_run=AsyncMock(),
            list_for_thread=AsyncMock(),
            list_page_for_thread=AsyncMock(),
        ),
        states=SimpleNamespace(
            get=AsyncMock(),
            set_pending=AsyncMock(),
            clear_pending=AsyncMock(),
        ),
        runs=SimpleNamespace(
            create=AsyncMock(),
            transition_status=AsyncMock(),
            get=AsyncMock(),
            get_for_update=AsyncMock(),
            get_for_worker=AsyncMock(),
            get_active_for_thread=AsyncMock(),
            list_stale_running=AsyncMock(),
            list_stale_queued=AsyncMock(),
        ),
        events=SimpleNamespace(append=AsyncMock(), list_for_run=AsyncMock()),
        idempotency=SimpleNamespace(
            claim=AsyncMock(),
            delete_created_before=AsyncMock(),
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


def test_command_submission_commits_all_records_once() -> None:
    async def scenario() -> None:
        context = _context()
        unit_of_work = _unit_of_work()
        thread = _thread(context)
        claim = _claim(context, request_hash="unused-for-new-claim", created=True)
        run = _run(context, thread.id, claim.record.run_id)
        unit_of_work.idempotency.claim.return_value = claim
        unit_of_work.threads.create.return_value = thread
        unit_of_work.runs.create.return_value = run

        result = await CommandSubmissionService(unit_of_work).submit(
            context,
            input_message=run.input_message,
            thread_title=thread.title,
            idempotency_key=claim.record.key,
            request_identity="new:request",
        )

        assert result.created
        assert result.run_id == run.id
        unit_of_work.events.append.assert_awaited_once()
        unit_of_work.messages.append_once.assert_awaited_once()
        unit_of_work.commit.assert_awaited_once()
        unit_of_work.rollback.assert_not_awaited()

    asyncio.run(scenario())


def test_command_submission_reuses_matching_claim_without_new_records() -> None:
    async def scenario() -> None:
        context = _context()
        unit_of_work = _unit_of_work()
        request_identity = "thread:request"
        claim = _claim(
            context,
            request_hash=sha256(request_identity.encode("utf-8")).hexdigest(),
            created=False,
        )
        existing = _run(context, uuid4(), claim.record.run_id)
        unit_of_work.idempotency.claim.return_value = claim
        unit_of_work.runs.get.return_value = existing

        result = await CommandSubmissionService(unit_of_work).submit(
            context,
            input_message=existing.input_message,
            idempotency_key=claim.record.key,
            request_identity=request_identity,
        )

        assert not result.created
        assert result.run_id == existing.id
        unit_of_work.threads.create.assert_not_awaited()
        unit_of_work.runs.create.assert_not_awaited()
        unit_of_work.messages.append_once.assert_not_awaited()
        unit_of_work.commit.assert_awaited_once()
        unit_of_work.rollback.assert_not_awaited()

    asyncio.run(scenario())


def test_command_submission_rolls_back_conflicts_and_partial_writes() -> None:
    async def scenario() -> None:
        context = _context()
        conflict_uow = _unit_of_work()
        conflict_uow.idempotency.claim.return_value = _claim(
            context,
            request_hash="different-request",
            created=False,
        )
        with pytest.raises(IdempotencyConflictError):
            await CommandSubmissionService(conflict_uow).submit(
                context,
                input_message="记录今天的数据",
                idempotency_key="request-1",
                request_identity="current-request",
            )
        conflict_uow.commit.assert_not_awaited()
        conflict_uow.rollback.assert_awaited_once()

        failed_uow = _unit_of_work()
        thread = _thread(context)
        failed_uow.threads.create.return_value = thread
        failed_uow.runs.create.return_value = _run(context, thread.id)
        failed_uow.events.append.side_effect = RuntimeError("event append failed")
        with pytest.raises(RuntimeError, match="event append failed"):
            await CommandSubmissionService(failed_uow).submit(
                context,
                input_message="记录今天的数据",
            )
        failed_uow.commit.assert_not_awaited()
        failed_uow.rollback.assert_awaited_once()

    asyncio.run(scenario())
