"""Langfuse tracing — optional: the service runs fine without keys."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_HANDLER: Any | None = None
_TRIED = False


def langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def get_langfuse_handler() -> Any | None:
    """Return a cached LangChain callback handler, or None if not configured."""
    global _HANDLER, _TRIED
    if _TRIED:
        return _HANDLER
    _TRIED = True
    if not langfuse_enabled():
        logger.info("Langfuse keys not set — tracing disabled.")
        return None
    try:
        from langfuse.langchain import CallbackHandler

        _HANDLER = CallbackHandler()
        logger.info("Langfuse tracing enabled (%s).", os.getenv("LANGFUSE_HOST", "cloud"))
    except Exception:  # pragma: no cover - import/config errors must never kill the API
        logger.exception("Langfuse init failed — tracing disabled.")
        _HANDLER = None
    return _HANDLER


def current_trace_id() -> str | None:
    """Best-effort trace id of the most recent run (for surfacing in responses)."""
    handler = get_langfuse_handler()
    if handler is None:
        return None
    for attr in ("last_trace_id", "trace_id"):
        value = getattr(handler, attr, None)
        if value:
            return str(value)
    try:
        from langfuse import get_client

        return get_client().get_current_trace_id()
    except Exception:
        return None
