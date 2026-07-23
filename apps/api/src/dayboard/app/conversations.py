from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.identity import TenantContext
from dayboard.db.conversation_repositories import (
    ConversationMessageRepository,
    ConversationStateRepository,
    ConversationThreadRepository,
)
from dayboard.db.models import ConversationMessageRow, ConversationStateRow, ConversationThreadRow
from agent_platform.conversations import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)


def conversation_thread_from_row(row: ConversationThreadRow) -> ConversationThread:
    return ConversationThread(
        id=row.id,
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
        title=row.title,
        status=row.status,
        summary=row.summary,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def conversation_message_from_row(row: ConversationMessageRow) -> ConversationMessage:
    return ConversationMessage(
        id=row.id,
        thread_id=row.thread_id,
        run_id=row.run_id,
        role=ConversationRole(row.role),
        content=row.content,
        message_metadata=row.message_metadata,
        created_at=row.created_at,
    )


def conversation_state_from_row(row: ConversationStateRow) -> ConversationState:
    public_state_data = {
        key: row.state_data[key]
        for key in ("source_run_id", "interaction")
        if key in row.state_data
    }
    return ConversationState(
        thread_id=row.thread_id,
        pending_action=row.pending_action,
        pending_question=row.pending_question,
        state_data=public_state_data,
        version=row.version,
        expires_at=row.expires_at,
        updated_at=row.updated_at,
    )


class ClarificationStateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedClarificationChoice:
    agent_message: str
    display_message: str


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.threads = ConversationThreadRepository(session)
        self.messages = ConversationMessageRepository(session)
        self.states = ConversationStateRepository(session)

    async def create_thread(
        self,
        context: TenantContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThreadRow:
        return await self.threads.create(context, thread_id=thread_id, title=title)

    async def require_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThreadRow:
        thread = await self.threads.get(context, thread_id)
        if thread is None:
            raise LookupError("Conversation thread not found")
        return thread

    async def get_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThread | None:
        row = await self.threads.get(context, thread_id)
        return conversation_thread_from_row(row) if row else None

    async def get_or_create_primary_thread(self, context: TenantContext) -> ConversationThreadRow:
        return await self.threads.get_or_create_primary(context)

    async def append_message(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        message_metadata: dict | None = None,
    ) -> ConversationMessage:
        row = await self.messages.append_once(
            context,
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            content=content,
            message_metadata=message_metadata,
        )
        return conversation_message_from_row(row)

    async def list_messages(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> list[ConversationMessage]:
        await self.require_thread(context, thread_id)
        rows = await self.messages.list_for_thread(context, thread_id)
        return [conversation_message_from_row(row) for row in rows]

    async def list_message_page(
        self,
        context: TenantContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> ConversationMessagePage:
        await self.require_thread(context, thread_id)
        rows, next_cursor = await self.messages.list_page_for_thread(
            context,
            thread_id,
            before=before,
            limit=limit,
        )
        return ConversationMessagePage(
            items=[conversation_message_from_row(row) for row in rows],
            next_cursor=next_cursor,
        )

    async def upsert_assistant_message(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
        message_metadata: dict,
    ) -> ConversationMessage:
        row = await self.messages.upsert_assistant(
            context,
            thread_id=thread_id,
            run_id=run_id,
            content=content,
            message_metadata=message_metadata,
        )
        return conversation_message_from_row(row)

    async def get_assistant_message_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> ConversationMessage | None:
        row = await self.messages.get_assistant_for_run(context, run_id)
        return conversation_message_from_row(row) if row else None

    async def update_summary(
        self,
        context: TenantContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread:
        row = await self.threads.update_summary(context, thread_id, summary)
        if row is None:
            raise LookupError("Conversation thread not found")
        return conversation_thread_from_row(row)

    async def get_state(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        await self.require_thread(context, thread_id)
        row = await self.states.get(context, thread_id)
        return conversation_state_from_row(row) if row else None

    async def set_pending_clarification(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        question: str,
        state_data: dict | None = None,
    ) -> ConversationState:
        row = await self.states.set_pending(
            context,
            thread_id=thread_id,
            action="clarification",
            question=question,
            state_data={"source_run_id": str(run_id), **(state_data or {})},
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        return conversation_state_from_row(row)

    async def clear_pending(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        row = await self.states.clear_pending(context, thread_id)
        return conversation_state_from_row(row) if row else None

    async def resolve_clarification_choice(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        state_version: int,
        option_key: str,
    ) -> ResolvedClarificationChoice:
        await self.require_thread(context, thread_id)
        row = await self.states.get(context, thread_id)
        now = datetime.now(UTC)
        if row is None or row.pending_action != "clarification":
            raise ClarificationStateError("This clarification is no longer active")
        if row.version != state_version:
            raise ClarificationStateError("This clarification has changed; refresh and choose again")
        if row.expires_at is not None and row.expires_at <= now:
            raise ClarificationStateError("This clarification has expired")

        candidates = row.state_data.get("candidates")
        if not isinstance(candidates, list):
            raise ClarificationStateError("This clarification does not accept a choice")
        selected = next(
            (
                candidate
                for candidate in candidates
                if isinstance(candidate, dict) and candidate.get("key") == option_key
            ),
            None,
        )
        if selected is None:
            raise ClarificationStateError("The selected option is not available")

        if "value" in selected:
            value = str(selected["value"])
            label = str(selected.get("label") or value)
            return ResolvedClarificationChoice(
                agent_message=(
                    "The user selected this server-validated answer for the pending "
                    f"clarification: {json.dumps(value, ensure_ascii=False)}. "
                    "Continue the previous request using this answer."
                ),
                display_message=f"选择“{label}”",
            )

        presentation_candidate = {
            key: selected[key]
            for key in (
                "id",
                "row_version",
                "title",
                "timing_kind",
                "scheduled_date",
                "start_time",
                "end_time",
                "timezone",
            )
            if key in selected
        }
        model_candidate = {
            key: presentation_candidate[key]
            for key in ("id", "row_version", "title", "timing_kind", "scheduled_date")
            if key in presentation_candidate
        }
        for source_key, target_key in (("start_time", "local_start"), ("end_time", "local_end")):
            value = presentation_candidate.get(source_key)
            if not isinstance(value, str):
                continue
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ClarificationStateError(
                    "The selected calendar time is invalid"
                ) from exc
            if parsed.tzinfo is None:
                raise ClarificationStateError("The selected calendar time is invalid")
            model_candidate[target_key] = (
                parsed.astimezone(ZoneInfo(context.timezone))
                .replace(tzinfo=None)
                .isoformat(timespec="minutes")
            )

        title = str(presentation_candidate.get("title") or "所选日程")
        start_time = presentation_candidate.get("start_time")
        display_message = f"选择“{title}”"
        if isinstance(start_time, str):
            try:
                parsed_start = datetime.fromisoformat(start_time)
                timezone_name = presentation_candidate.get("timezone")
                if isinstance(timezone_name, str):
                    parsed_start = parsed_start.astimezone(ZoneInfo(timezone_name))
                display_time = parsed_start.strftime("%m月%d日 %H:%M")
            except (ValueError, TypeError):
                display_time = start_time
            display_message = f"选择“{title} · {display_time}”"
        elif isinstance(presentation_candidate.get("scheduled_date"), str):
            display_message = f"选择“{title} · {presentation_candidate['scheduled_date']} · 随时”"
        agent_message = (
            "The user selected this server-validated calendar candidate for the pending "
            f"clarification: {json.dumps(model_candidate, ensure_ascii=False)}. "
            "Continue the previous request using this exact candidate."
        )
        return ResolvedClarificationChoice(
            agent_message=agent_message,
            display_message=display_message,
        )
