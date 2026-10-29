import logging

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """Structured logs: pretty console in dev, JSON lines in prod (for log shippers)."""
    settings = get_settings()
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.env == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
