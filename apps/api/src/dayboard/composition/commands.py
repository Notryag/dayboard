"""Composition for the storage-free Dayboard command application service."""

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import RunExecutionFailure
from dayboard.agent.run_result_projection import project_run_failure
from dayboard.app.clarifications import ClarificationService
from dayboard.app.commands import CommandService
from dayboard.composition.platform import build_platform_services


def build_command_service(session: AsyncSession) -> CommandService:
    platform = build_platform_services(session)

    def project_failure(exc: Exception) -> RunExecutionFailure:
        return project_run_failure(exc, presentation_parts=[])

    return CommandService(
        submissions=platform.submissions,
        clarifications=ClarificationService(platform.conversations),
        execution=platform.execution,
        failure_projector=project_failure,
    )
