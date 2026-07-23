"""Framework-independent contracts shared by platform use cases."""

from agent_platform.core.conversations import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from agent_platform.core.errors import ActiveThreadRunError, ConversationNotFoundError
from agent_platform.core.identity import TenantContext, TenantIsolationMode
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
    "TenantContext",
    "TenantIsolationMode",
]
