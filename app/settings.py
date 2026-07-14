"""Environment-driven configuration (12-factor: all knobs via env vars)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Langfuse v3 reads LANGFUSE_HOST; accept LANGFUSE_BASE_URL as an alias.
if os.getenv("LANGFUSE_BASE_URL") and not os.getenv("LANGFUSE_HOST"):
    os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

MODEL = os.getenv("DEEPAGENT_MODEL", "groq:llama-3.3-70b-versatile")
SUBAGENT_MODEL = os.getenv("SUBAGENT_MODEL", "groq:llama-3.1-8b-instant")
BACKEND = os.getenv("DEEPAGENT_BACKEND", "StateBackend")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "workspace")

ENABLE_WEB_SEARCH = _bool("ENABLE_WEB_SEARCH", True)
ENABLE_SUBAGENTS = _bool("ENABLE_SUBAGENTS", True)
USE_STRUCTURED_OUTPUT = _bool("USE_STRUCTURED_OUTPUT", False)
EAGER_INIT = _bool("EAGER_INIT", True)

RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", "50"))

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful deep research assistant. Be concise and cite sources "
    "when you used web search.",
)
