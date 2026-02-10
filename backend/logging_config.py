"""
Structured logging configuration for LLMLab.

- Production: JSON formatted logs for machine parsing
- Development/Test: Human-readable colored logs
- Request ID middleware for distributed tracing
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

from pythonjsonlogger import jsonlogger

# Context variable for request ID — accessible from any async context
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Inject request_id into every log record."""

    def filter(self, record):
        record.request_id = request_id_var.get() or "-"
        return True


def setup_logging(environment: str = "development") -> None:
    """
    Configure logging for the application.

    Args:
        environment: One of 'production', 'development', 'test'.
    """
    root = logging.getLogger()

    # Remove existing handlers to avoid duplicates
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if environment == "production":
        # JSON structured logging for production
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        root.setLevel(logging.INFO)
    elif environment == "test":
        # Minimal logging for tests
        formatter = logging.Formatter(
            "%(levelname)-5s %(name)s: %(message)s"
        )
        root.setLevel(logging.WARNING)
    else:
        # Human-readable for development
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        root.setLevel(logging.INFO)

    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    root.addHandler(handler)

    # Quieten noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def generate_request_id() -> str:
    """Generate a short unique request ID."""
    return uuid.uuid4().hex[:12]
