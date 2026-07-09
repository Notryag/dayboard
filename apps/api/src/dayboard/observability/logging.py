from __future__ import annotations

import logging

import structlog


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=_coerce_log_level(level),
        format="%(message)s",
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _coerce_log_level(level: str) -> int:
    resolved = getattr(logging, level.upper(), None)
    return resolved if isinstance(resolved, int) else logging.INFO

