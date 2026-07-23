"""Product-neutral application errors."""


class ActiveThreadRunError(RuntimeError):
    """Raised when a conversation already has an active Run."""


class ConversationNotFoundError(LookupError):
    """Raised when a conversation is outside the caller's trusted scope or missing."""


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused for a different request."""


class IdempotencyTargetNotFoundError(RuntimeError):
    """Raised when a persisted idempotency claim references a missing target."""
