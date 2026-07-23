"""Dayboard scheduling clarification policy and presentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from agent_platform.application import ConversationService
from agent_platform.core import ConversationState
from agent_platform.core import TenantContext


class ClarificationStateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedClarificationChoice:
    agent_message: str
    display_message: str


def public_conversation_state(state: ConversationState | None) -> ConversationState | None:
    if state is None:
        return None
    public_state_data = {
        key: state.state_data[key]
        for key in ("source_run_id", "interaction")
        if key in state.state_data
    }
    return state.model_copy(update={"state_data": public_state_data})


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
        state_data: dict | None = None,
    ) -> ConversationState:
        return await self.conversations.set_pending(
            context,
            thread_id=thread_id,
            action="clarification",
            question=question,
            state_data={"source_run_id": str(run_id), **(state_data or {})},
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
        if state is None or state.pending_action != "clarification":
            raise ClarificationStateError("This clarification is no longer active")
        if state.version != state_version:
            raise ClarificationStateError("This clarification has changed; refresh and choose again")
        if state.expires_at is not None and state.expires_at <= now:
            raise ClarificationStateError("This clarification has expired")

        candidates = state.state_data.get("candidates")
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
