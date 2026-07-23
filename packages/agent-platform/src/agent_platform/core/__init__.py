"""Framework-independent contracts shared by platform use cases."""

from agent_platform.core.conversations import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    ConversationState,
    ConversationThread,
    ConversationThreadStatus,
)
from agent_platform.core.commands import CommandSubmission
from agent_platform.core.errors import (
    ActiveThreadRunError,
    ConversationArchivedError,
    ConversationNotFoundError,
    IdempotencyConflictError,
    IdempotencyTargetNotFoundError,
    InteractionConflictError,
)
from agent_platform.core.identity import TenantContext, TenantIsolationMode
from agent_platform.core.idempotency import IdempotencyClaim, IdempotencyRecord
from agent_platform.core.interactions import PendingInteraction
from agent_platform.core.presentations import PresentationEnvelope
from agent_platform.core.runs import (
    AgentRun,
    AgentRunEvent,
    AgentRunEventCategory,
    AgentRunStatus,
)

__all__ = [
    "ActiveThreadRunError",
    "AgentRun",
    "AgentRunEvent",
    "AgentRunEventCategory",
    "AgentRunStatus",
    "ConversationMessage",
    "ConversationMessagePage",
    "ConversationArchivedError",
    "ConversationNotFoundError",
    "ConversationRole",
    "ConversationState",
    "ConversationThread",
    "ConversationThreadStatus",
    "CommandSubmission",
    "IdempotencyClaim",
    "IdempotencyConflictError",
    "IdempotencyRecord",
    "IdempotencyTargetNotFoundError",
    "InteractionConflictError",
    "PendingInteraction",
    "PresentationEnvelope",
    "TenantContext",
    "TenantIsolationMode",
]
