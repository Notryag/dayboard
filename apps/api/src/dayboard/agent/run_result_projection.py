"""Project North results into product-neutral Platform execution outcomes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from north import ClarificationRequest, RuntimeExecutionResult
from pydantic import ValidationError

from agent_platform.core import (
    RunExecutionFailure,
    RunExecutionOutcome,
    RunExecutionOutcomeKind,
)
from dayboard.agent.budget import ProviderBudgetExceeded
from dayboard.app.clarifications import ClarificationService
from dayboard.app.conversation_presentations import build_dayboard_presentation
from dayboard.domain.interactions import (
    CalendarEntryChoiceCandidate,
    CalendarEntryChoiceOption,
    CalendarEntryChoicePresentation,
    ClarificationPayload,
    SuggestedChoiceCandidate,
    SuggestedChoiceOption,
    SuggestedChoicePresentation,
)


def project_run_result(
    result: RuntimeExecutionResult,
    *,
    run_id: UUID,
    presentation_parts: list[dict[str, Any]],
) -> RunExecutionOutcome:
    presentation = build_dayboard_presentation(presentation_parts)
    clarification = result.clarification
    if clarification is None:
        return RunExecutionOutcome(
            kind=RunExecutionOutcomeKind.completed,
            result_message=extract_final_message(result.values),
            presentation=presentation,
        )

    pending = ClarificationService.build_pending(
        run_id=run_id,
        question=clarification.question,
        payload=extract_clarification_payload(clarification, presentation_parts),
    )
    return RunExecutionOutcome(
        kind=RunExecutionOutcomeKind.needs_interaction,
        result_message=clarification.question,
        presentation=presentation,
        interaction=pending.interaction,
        interaction_expires_at=pending.expires_at,
    )


def project_run_failure(
    exc: Exception,
    *,
    presentation_parts: list[dict[str, Any]],
) -> RunExecutionFailure:
    return RunExecutionFailure(
        error_type=type(exc).__name__,
        error_message=safe_error_message(exc),
        presentation=build_dayboard_presentation(presentation_parts),
    )


def merge_presentation_parts(
    current: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> bool:
    changed = False
    for part in candidates:
        key = _presentation_entity_key(part)
        if key is None:
            continue
        index = next(
            (
                index
                for index, existing in enumerate(current)
                if _presentation_entity_key(existing) == key
            ),
            None,
        )
        if index is None:
            current.append(part)
            changed = True
        elif current[index] != part:
            current[index] = part
            changed = True
    return changed


def safe_error_message(exc: Exception) -> str:
    if isinstance(exc, ProviderBudgetExceeded):
        if exc.budget_type == "request":
            return "请求有点频繁，请稍等一分钟后再试。"
        return "今天的 AI 使用额度已用完，请明天再试。"
    if getattr(exc, "status_code", None) == 429:
        return "AI 服务当前有点繁忙，请稍等几分钟后再试。"
    message = str(exc).strip() or type(exc).__name__
    return message[:4000]


def extract_clarification_payload(
    clarification: ClarificationRequest,
    presentation_parts: list[dict[str, Any]],
) -> ClarificationPayload:
    candidates = _calendar_candidates(presentation_parts)
    if not candidates:
        return _suggested_choice_payload(clarification) or ClarificationPayload(
            response_kind="free_text"
        )
    return ClarificationPayload(
        response_kind="calendar_choice",
        candidates=candidates,
        presentation=CalendarEntryChoicePresentation(
            options=[
                CalendarEntryChoiceOption.model_validate(
                    candidate.model_dump(exclude={"kind", "id", "row_version", "status"})
                )
                for candidate in candidates
            ]
        ),
    )


def extract_final_message(result: Any) -> str:
    if not isinstance(result, dict):
        return "Done."
    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        return "Done."
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(message, dict):
            dict_content = message.get("content")
            if isinstance(dict_content, str) and dict_content.strip():
                return dict_content.strip()
    return "Done."


def _presentation_entity_key(part: dict[str, Any]) -> tuple[str, str] | None:
    item = part.get("item")
    if not isinstance(item, dict):
        return None
    value = item.get("value")
    kind = item.get("kind")
    item_id = value.get("id") if isinstance(value, dict) else None
    if not isinstance(kind, str) or not isinstance(item_id, str):
        return None
    return kind, item_id


def _suggested_choice_payload(
    clarification: ClarificationRequest,
) -> ClarificationPayload | None:
    if clarification.response_kind != "single_choice":
        return None
    choices = [
        SuggestedChoiceCandidate(
            key=f"candidate_{index}",
            value=option,
            label=option,
        )
        for index, option in enumerate(
            clarification.options[:10],
            start=1,
        )
    ]
    if not choices:
        return None
    return ClarificationPayload(
        response_kind="single_choice",
        candidates=choices,
        presentation=SuggestedChoicePresentation(
            options=[
                SuggestedChoiceOption(key=choice.key, label=choice.label) for choice in choices
            ]
        ),
    )


def _calendar_candidates(
    presentation_parts: list[dict[str, Any]],
) -> list[CalendarEntryChoiceCandidate]:
    candidates: list[CalendarEntryChoiceCandidate] = []
    for part in presentation_parts:
        item = part.get("item") if isinstance(part, dict) else None
        if (
            not isinstance(item, dict)
            or item.get("kind") != "calendar"
            or not isinstance(item.get("value"), dict)
            or part.get("operation") != "calendar_entry_found"
        ):
            continue
        try:
            candidates.append(
                CalendarEntryChoiceCandidate.model_validate(
                    {
                        "kind": "calendar",
                        "key": f"candidate_{len(candidates) + 1}",
                        **item["value"],
                    }
                )
            )
        except ValidationError:
            continue
        if len(candidates) == 10:
            break
    return candidates
