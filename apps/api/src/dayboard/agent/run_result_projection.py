"""Project North results into product-neutral Platform execution outcomes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from north import ClarificationRequest, RuntimeExecutionResult

from agent_platform.core import (
    RunExecutionFailure,
    RunExecutionOutcome,
    RunExecutionOutcomeKind,
)
from dayboard.agent.budget import ProviderBudgetExceeded
from dayboard.agent.clarification_candidates import RunClarificationCandidates
from dayboard.agent.presentation import public_text
from dayboard.app.clarifications import ClarificationService
from dayboard.app.conversation_presentations import build_dayboard_presentation
from dayboard.domain.interactions import (
    CalendarEntryChoiceOption,
    CalendarEntryChoicePresentation,
    ClarificationPayload,
    SuggestedChoiceCandidate,
    SuggestedChoiceOption,
    SuggestedChoicePresentation,
    TaskItemChoiceCandidate,
    TaskItemChoiceOption,
    TaskItemChoicePresentation,
)


def project_run_result(
    result: RuntimeExecutionResult,
    *,
    run_id: UUID,
    presentation_parts: list[dict[str, Any]],
    clarification_candidates: RunClarificationCandidates | None = None,
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
        payload=extract_clarification_payload(clarification, clarification_candidates),
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
        if exc.budget_type in {"run_requests", "run_tokens"}:
            return "本次操作已达到 AI 执行上限，请查看已完成的安排，并将剩余操作分开提交。"
        if exc.budget_type == "request":
            return "请求有点频繁，请稍等一分钟后再试。"
        return "今天的 AI 使用额度已用完，请明天再试。"
    if getattr(exc, "status_code", None) == 429:
        return "AI 服务当前有点繁忙，请稍等几分钟后再试。"
    message = str(exc).strip() or type(exc).__name__
    return message[:4000]


def extract_clarification_payload(
    clarification: ClarificationRequest,
    binding: RunClarificationCandidates | None = None,
) -> ClarificationPayload:
    if binding is not None and binding.error is not None:
        raise ValueError(binding.error)
    candidates = list(binding.selected) if binding is not None else []
    if binding is not None and candidates and binding.question != clarification.question:
        raise ValueError("Clarification question does not match the selected candidate set")
    if not candidates:
        return _suggested_choice_payload(clarification) or ClarificationPayload(
            response_kind="free_text"
        )
    if isinstance(candidates[0], TaskItemChoiceCandidate):
        return ClarificationPayload(
            response_kind="task_choice",
            candidates=[candidate for candidate in candidates],
            presentation=TaskItemChoicePresentation(
                options=[
                    TaskItemChoiceOption.model_validate(candidate.model_dump())
                    for candidate in candidates
                ]
            ),
        )
    return ClarificationPayload(
        response_kind="calendar_choice",
        candidates=[candidate for candidate in candidates],
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
    # Earlier assistant text may describe an intermediate step or a previous turn.
    # Only a final assistant message without pending tool calls can summarize a Run.
    fallback = "本次执行未返回最终说明，请先查看操作结果，核实后再继续，避免重复提交。"
    messages = result.get("messages") if isinstance(result, dict) else None
    if not isinstance(messages, list) or not messages:
        return fallback
    message = messages[-1]
    if isinstance(message, dict):
        kind = message.get("type") or message.get("role")
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        additional = message.get("additional_kwargs") or {}
    else:
        kind = getattr(message, "type", None)
        content = getattr(message, "content", None)
        tool_calls = getattr(message, "tool_calls", None)
        additional = getattr(message, "additional_kwargs", {})
    if kind not in {"ai", "assistant", "AIMessageChunk"} or tool_calls:
        return fallback
    if isinstance(additional, dict) and additional.get("tool_calls"):
        return fallback
    return public_text(content).strip() or fallback


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
        candidates=[choice for choice in choices],
        presentation=SuggestedChoicePresentation(
            options=[
                SuggestedChoiceOption(key=choice.key, label=choice.label) for choice in choices
            ]
        ),
    )
