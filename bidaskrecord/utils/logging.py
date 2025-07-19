"""Logging configuration for the application."""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from structlog.types import EventDict, Processor

from bidaskrecord.config.settings import get_settings

settings = get_settings()


def drop_color_message_key(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Remove the color message key from the event dict."""
    event_dict.pop("color_message", None)
    return event_dict


def add_service_info(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Add service information to the log event."""
    event_dict["service"] = "bidaskrecord"
    return event_dict


def configure_logging() -> None:
    """Configure logging for the application."""
    # Configure logging level
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure file handler if LOG_FILE is set
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if settings.LOG_FILE:
        # Ensure log directory exists
        log_file = Path(settings.LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=handlers,
    )

    # Configure structlog
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        drop_color_message_key,
        add_service_info,
    ]

    if settings.ENVIRONMENT == "development":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance.

    Args:
        name: The name of the logger. If None, the root logger is used.

    Returns:
        A configured logger instance.
    """
    return structlog.get_logger(name or "bidaskrecord")


# Configure logging when module is imported
configure_logging()
