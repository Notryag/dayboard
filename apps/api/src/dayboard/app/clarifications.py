"""Dayboard scheduling clarification policy and presentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from agent_platform.application import ConversationService
from agent_platform.core import ConversationState, PendingInteraction
from agent_platform.core import TenantContext
from dayboard.domain.interactions import (
    CLARIFICATION_INTERACTION_TYPE,
    CLARIFICATION_SCHEMA_VERSION,
    CalendarEntryChoiceCandidate,
    ClarificationConversationState,
    ClarificationInteractionView,
    ClarificationPayload,
    ClarificationPublicPayload,
    SuggestedChoiceCandidate,
)


class ClarificationStateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedClarificationChoice:
    agent_message: str
    display_message: str


def public_conversation_state(
    state: ConversationState | None,
) -> ClarificationConversationState | None:
    if state is None or state.interaction is None:
        return None
    interaction = state.interaction
    if (
        interaction.interaction_type != CLARIFICATION_INTERACTION_TYPE
        or interaction.schema_version != CLARIFICATION_SCHEMA_VERSION
    ):
        return None
    if state.expires_at is None:
        raise RuntimeError("Active clarification is missing its expiry")
    if state.expires_at <= datetime.now(UTC):
        return None
    payload = ClarificationPayload.model_validate(interaction.payload)
    return ClarificationConversationState(
        thread_id=state.thread_id,
        interaction=ClarificationInteractionView(
            source_run_id=interaction.source_run_id,
            prompt=interaction.prompt,
            payload=ClarificationPublicPayload(presentation=payload.presentation),
        ),
        version=state.version,
        expires_at=state.expires_at,
        updated_at=state.updated_at,
    )


class ClarificationService:
    def __init__(self, conversations: ConversationService) -> None:
        self.conversations = conversations

    async def set_pending(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        question: str,
        payload: ClarificationPayload,
    ) -> ConversationState:
        return await self.conversations.set_interaction(
            context,
            thread_id=thread_id,
            interaction=PendingInteraction(
                interaction_type=CLARIFICATION_INTERACTION_TYPE,
                schema_version=CLARIFICATION_SCHEMA_VERSION,
                source_run_id=run_id,
                prompt=question,
                payload=payload.model_dump(mode="json", exclude_none=True),
            ),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )

    async def resolve_choice(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        state_version: int,
        option_key: str,
    ) -> ResolvedClarificationChoice:
        state = await self.conversations.get_state(context, thread_id)
        now = datetime.now(UTC)
        if (
            state is None
            or state.interaction is None
            or state.interaction.interaction_type != CLARIFICATION_INTERACTION_TYPE
            or state.interaction.schema_version != CLARIFICATION_SCHEMA_VERSION
        ):
            raise ClarificationStateError("This clarification is no longer active")
        if state.version != state_version:
            raise ClarificationStateError("This clarification has changed; refresh and choose again")
        if state.expires_at is None or state.expires_at <= now:
            raise ClarificationStateError("This clarification has expired")

        payload = ClarificationPayload.model_validate(state.interaction.payload)
        if payload.response_kind == "free_text":
            raise ClarificationStateError("This clarification does not accept a choice")
        selected = next(
            (candidate for candidate in payload.candidates if candidate.key == option_key),
            None,
        )
        if selected is None:
            raise ClarificationStateError("The selected option is not available")

        if isinstance(selected, SuggestedChoiceCandidate):
            return ResolvedClarificationChoice(
                agent_message=(
                    "The user selected this server-validated answer for the pending "
                    f"clarification: {json.dumps(selected.value, ensure_ascii=False)}. "
                    "Continue the previous request using this answer."
                ),
                display_message=f"选择“{selected.label}”",
            )

        if not isinstance(selected, CalendarEntryChoiceCandidate):
            raise ClarificationStateError("The selected option is invalid")
        model_candidate = {
            "id": str(selected.id),
            "row_version": selected.row_version,
            "title": selected.title,
            "timing_kind": selected.timing_kind.value,
            "status": selected.status,
        }
        if selected.scheduled_date is not None:
            model_candidate["scheduled_date"] = selected.scheduled_date.isoformat()
        for value, target_key in (
            (selected.start_time, "local_start"),
            (selected.end_time, "local_end"),
        ):
            if value is not None:
                model_candidate[target_key] = (
                    value.astimezone(ZoneInfo(context.timezone))
                    .replace(tzinfo=None)
                    .isoformat(timespec="minutes")
                )

        display_message = f"选择“{selected.title}”"
        if selected.start_time is not None:
            display_time = selected.start_time.astimezone(
                ZoneInfo(selected.timezone)
            ).strftime("%m月%d日 %H:%M")
            display_message = f"选择“{selected.title} · {display_time}”"
        elif selected.scheduled_date is not None:
            display_message = f"选择“{selected.title} · {selected.scheduled_date} · 随时”"
        agent_message = (
            "The user selected this server-validated calendar candidate for the pending "
            f"clarification: {json.dumps(model_candidate, ensure_ascii=False)}. "
            "Continue the previous request using this exact candidate."
        )
        return ResolvedClarificationChoice(
            agent_message=agent_message,
            display_message=display_message,
        )
