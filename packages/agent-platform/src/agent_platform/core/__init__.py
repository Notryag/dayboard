"""Framework-independent contracts shared by platform use cases."""

from agent_platform.core.conversations import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from agent_platform.core.commands import CommandSubmission
from agent_platform.core.errors import (
    ActiveThreadRunError,
    ConversationNotFoundError,
    IdempotencyConflictError,
    IdempotencyTargetNotFoundError,
)
from agent_platform.core.identity import TenantContext, TenantIsolationMode
from agent_platform.core.idempotency import IdempotencyClaim, IdempotencyRecord
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
    "ConversationNotFoundError",
    "ConversationRole",
    "ConversationState",
    "ConversationThread",
    "CommandSubmission",
    "IdempotencyClaim",
    "IdempotencyConflictError",
    "IdempotencyRecord",
    "IdempotencyTargetNotFoundError",
    "TenantContext",
    "TenantIsolationMode",
]
