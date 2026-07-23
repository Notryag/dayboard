"""Project North results into product-neutral Platform execution outcomes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.messages import ToolMessage
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
    result: Any,
    *,
    run_id: UUID,
    presentation_parts: list[dict[str, Any]],
) -> RunExecutionOutcome:
    presentation = build_dayboard_presentation(presentation_parts)
    clarification_question = extract_clarification_question(result)
    if clarification_question is None:
        return RunExecutionOutcome(
            kind=RunExecutionOutcomeKind.completed,
            result_message=extract_final_message(result),
            presentation=presentation,
        )

    pending = ClarificationService.build_pending(
        run_id=run_id,
        question=clarification_question,
        payload=extract_clarification_payload(result),
    )
    return RunExecutionOutcome(
        kind=RunExecutionOutcomeKind.needs_interaction,
        result_message=clarification_question,
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


def extract_clarification_question(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    thread_data = result.get("thread_data")
    if not isinstance(thread_data, dict):
        return None
    clarification = thread_data.get("clarification")
    if not isinstance(clarification, dict):
        return None
    question = clarification.get("question")
    return question if isinstance(question, str) and question else None


def extract_clarification_payload(result: Any) -> ClarificationPayload:
    fallback = ClarificationPayload(response_kind="free_text")
    if not isinstance(result, dict):
        return fallback

    payload = _suggested_choice_payload(result) or fallback
    messages = result.get("messages")
    if not isinstance(messages, list):
        return payload

    artifact = _latest_calendar_search_artifact(messages)
    if artifact is None:
        return payload
    candidates = _calendar_candidates(artifact)
    if not candidates:
        return payload
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


def _suggested_choice_payload(result: dict[str, Any]) -> ClarificationPayload | None:
    thread_data = result.get("thread_data")
    clarification = thread_data.get("clarification") if isinstance(thread_data, dict) else None
    if not isinstance(clarification, dict) or clarification.get("response_kind") != "single_choice":
        return None
    options = clarification.get("options")
    if not isinstance(options, list):
        return None
    choices = [
        SuggestedChoiceCandidate(
            key=f"candidate_{index}",
            value=option,
            label=option,
        )
        for index, option in enumerate(
            (option for option in options[:10] if isinstance(option, str) and option.strip()),
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


def _latest_calendar_search_artifact(messages: list[Any]) -> dict[str, Any] | None:
    search_call_ids: set[str] = set()
    latest: dict[str, Any] | None = None
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None)
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls", tool_calls)
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("name") != "search_calendar_entries":
                    continue
                call_id = call.get("id")
                if isinstance(call_id, str) and isinstance(call.get("args"), dict):
                    search_call_ids.add(call_id)

        if isinstance(message, ToolMessage):
            call_id = message.tool_call_id
            artifact = message.artifact
        elif isinstance(message, dict) and message.get("type") == "tool":
            call_id = message.get("tool_call_id")
            artifact = message.get("artifact")
        else:
            continue
        if (
            isinstance(call_id, str)
            and call_id in search_call_ids
            and isinstance(artifact, dict)
        ):
            latest = artifact
    return latest


def _calendar_candidates(artifact: dict[str, Any]) -> list[CalendarEntryChoiceCandidate]:
    if artifact.get("type") != "schedule_items_result":
        return []
    artifact_items = artifact.get("items")
    if not isinstance(artifact_items, list):
        return []
    candidates: list[CalendarEntryChoiceCandidate] = []
    for index, item in enumerate(artifact_items[:10], start=1):
        if (
            not isinstance(item, dict)
            or item.get("kind") != "calendar"
            or not isinstance(item.get("value"), dict)
        ):
            continue
        try:
            candidates.append(
                CalendarEntryChoiceCandidate.model_validate(
                    {
                        "kind": "calendar",
                        "key": f"candidate_{index}",
                        **item["value"],
                    }
                )
            )
        except ValidationError:
            continue
    return candidates
