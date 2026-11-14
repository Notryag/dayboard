"""Run-local search snapshots explicitly selected by a clarification tool call."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from dayboard.domain.interactions import CalendarEntryChoiceCandidate, TaskItemChoiceCandidate


class ClarificationInput(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    response_kind: Literal["free_text", "single_choice"] = "free_text"
    options: list[str] | None = None
    candidate_set_key: str | None = Field(
        default=None,
        description="Key from the relevant calendar or task search; omit for other questions.",
    )


class RunClarificationCandidates:
    """Own the search-to-interaction binding for exactly one Run, never UI state."""

    def __init__(self) -> None:
        self._sets: dict[
            str, tuple[CalendarEntryChoiceCandidate | TaskItemChoiceCandidate, ...]
        ] = {}
        self.selected: tuple[CalendarEntryChoiceCandidate | TaskItemChoiceCandidate, ...] = ()
        self.question: str | None = None
        self.error: str | None = None

    def reset(self) -> None:
        self._sets.clear()
        self.selected = ()
        self.question = None
        self.error = None

    def register(
        self,
        snapshots: list[dict],
        *,
        has_more: bool,
        kind: Literal["calendar", "task"],
    ) -> str | None:
        # A choice must be complete and fit the existing persisted interaction contract.
        if has_more or not 1 <= len(snapshots) <= 10:
            return None
        candidate_type = (
            CalendarEntryChoiceCandidate if kind == "calendar" else TaskItemChoiceCandidate
        )
        candidates = tuple(
            candidate_type.model_validate({**snapshot, "key": f"candidate_{index}"})
            for index, snapshot in enumerate(snapshots, start=1)
        )
        key = uuid4().hex
        self._sets[key] = candidates
        return key

    def ask(self, **kwargs) -> str:
        self.selected = ()
        self.question = None
        self.error = "Invalid clarification request"
        data = ClarificationInput.model_validate(kwargs)
        if data.candidate_set_key is not None:
            candidates = self._sets.get(data.candidate_set_key)
            if candidates is None:
                self.error = "Unknown candidate set; search again before asking for a choice"
                raise ValueError(self.error)
            if data.options or data.response_kind != "free_text":
                self.error = "Candidate sets cannot be combined with text options"
                raise ValueError(self.error)
            self.selected = candidates
        self.question = data.question.strip()
        self.error = None
        return f"Clarification needed: {self.question}"

    def build_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.ask,
            name="ask_clarification",
            description=(
                "Ask for missing information. For a calendar or task target choice, provide the "
                "candidate_set_key from that search, without options or response_kind. "
                "Otherwise use free_text or single_choice with text options."
            ),
            args_schema=ClarificationInput,
        )
