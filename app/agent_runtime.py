"""Builds and runs the deep agent for the API layer.

Kept separate from app.main so tests can monkeypatch `run_agent` without
touching FastAPI, and so the eval suite can call the agent in-process.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app import settings
from app.observability import get_langfuse_handler
from core.agent import build_agent

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# One agent per (model, memory backend) combo — each has its own
# checkpointer, so conversation history lives inside its combo.
_AGENTS: dict[tuple[str, str], tuple[Any, str]] = {}


def get_agent(model: str | None = None, backend: str | None = None) -> tuple[Any, str]:
    """Build the deep agent for a (model, backend) combo once and cache it."""
    key = (model or settings.MODEL, backend or settings.BACKEND)
    if key not in _AGENTS:
        with _LOCK:
            if key not in _AGENTS:
                agent, status = build_agent(
                    model=key[0],
                    backend_name=key[1],
                    workspace_root=settings.WORKSPACE_ROOT,
                    system_prompt=settings.SYSTEM_PROMPT,
                    enable_web_search=settings.ENABLE_WEB_SEARCH,
                    enable_subagents=settings.ENABLE_SUBAGENTS,
                    use_structured_output=settings.USE_STRUCTURED_OUTPUT,
                    subagent_model=settings.SUBAGENT_MODEL,
                )
                _AGENTS[key] = (agent, status)
                logger.info("Deep agent ready: model=%s backend=%s | %s",
                            key[0], key[1], status)
    return _AGENTS[key]


def extract_answer(result: dict[str, Any]) -> str:
    """Pull the final assistant text out of a LangGraph result."""
    messages = result.get("messages", [])
    if not messages:
        return ""
    content = getattr(messages[-1], "content", messages[-1])
    if isinstance(content, dict):
        content = content.get("content", "")
    if isinstance(content, list):  # content-block format
        content = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


# Groq's llama occasionally emits a syntactically broken tool call
# ("tool_use_failed" 400) — a transient generation glitch, not a config error.
_TRANSIENT_MARKER = "tool_use_failed"
_MAX_ATTEMPTS = 2  # each attempt costs real tokens; retry once, then surface

# Error-string markers that mean the *provider* is unresponsive (as opposed to
# a bad request from us) — these justify rerouting to FALLBACK_MODEL.
_OUTAGE_MARKERS = (
    "rate_limit", "rate limit", "error code: 429",
    "error code: 500", "error code: 502", "error code: 503",
    "internal server error", "service unavailable", "overloaded",
    "timeout", "timed out", "connection error", "connection refused",
)


def _provider_outage(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _OUTAGE_MARKERS)


def _invoke(agent: Any, message: str, config: dict[str, Any], thread_id: str) -> str:
    """One agent turn, retrying once on Groq's transient tool_use_failed 400."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": message}]},
                config=config,
            )
            return extract_answer(result)
        except Exception as exc:
            if _TRANSIENT_MARKER not in str(exc) or attempt == _MAX_ATTEMPTS:
                raise
            logger.warning(
                "Malformed tool call from the model (thread=%s, attempt %d/%d) — retrying.",
                thread_id, attempt, _MAX_ATTEMPTS,
            )
    raise RuntimeError("unreachable")  # for the type checker


def run_agent(
    message: str,
    thread_id: str,
    model: str | None = None,
    backend: str | None = None,
) -> tuple[str, str]:
    """One user message on a conversation thread -> (answer, model that answered).

    If the primary provider is unresponsive (429/5xx/timeout) and
    FALLBACK_MODEL is configured, the turn is retried once on the fallback.
    Each (model, backend) agent has its own checkpointer, so a fallback turn
    starts without the thread's prior history — degraded but alive.
    """
    primary = model or settings.MODEL
    agent, _ = get_agent(primary, backend)
    callbacks = [h for h in [get_langfuse_handler()] if h is not None]
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.RECURSION_LIMIT,
        "callbacks": callbacks,
        "metadata": {"langfuse_session_id": thread_id},
    }
    try:
        return _invoke(agent, message, config, thread_id), primary
    except Exception as exc:
        fallback = settings.FALLBACK_MODEL
        if not fallback or fallback == primary or not _provider_outage(exc):
            raise
        logger.warning(
            "Primary model %s unresponsive (%s) — falling back to %s (thread=%s).",
            primary, exc, fallback, thread_id,
        )
        fallback_agent, _ = get_agent(fallback, backend)
        return _invoke(fallback_agent, message, config, thread_id), fallback
