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

# When the primary provider is unresponsive (rate limit, 5xx, timeout), one
# retry goes through this model instead. DeepSeek is a different provider, so
# a Groq-wide outage doesn't take it down too. Empty string disables fallback.
FALLBACK_MODEL = os.getenv(
    "FALLBACK_MODEL",
    "deepseek:deepseek-chat" if os.getenv("DEEPSEEK_API_KEY") else "",
)
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "workspace")

# Models the API lets clients pick per request. Groq rate limits are per
# model, so every Groq entry is a separate daily token bucket on the free
# tier. OpenAI / DeepSeek entries are offered only when their key is set —
# a pickable model that can't authenticate would just be a runtime error.
_DEFAULT_MODELS = [
    "groq:llama-3.3-70b-versatile",
    "groq:llama-3.1-8b-instant",
    "groq:openai/gpt-oss-120b",
    "groq:openai/gpt-oss-20b",
    "groq:qwen/qwen3-32b",
    "groq:moonshotai/kimi-k2-instruct",
]
if os.getenv("OPENAI_API_KEY"):
    _DEFAULT_MODELS += ["openai:gpt-4o-mini", "openai:gpt-4.1-mini", "openai:gpt-4o"]
if os.getenv("DEEPSEEK_API_KEY"):
    _DEFAULT_MODELS += ["deepseek:deepseek-chat", "deepseek:deepseek-reasoner"]

_env_models = [m.strip() for m in os.getenv("AVAILABLE_MODELS", "").split(",") if m.strip()]
AVAILABLE_MODELS = _env_models or _DEFAULT_MODELS
if MODEL not in AVAILABLE_MODELS:
    AVAILABLE_MODELS.insert(0, MODEL)

# The three deepagents memory types (see core/backends.py).
AVAILABLE_BACKENDS = ["StateBackend", "FilesystemBackend", "StoreBackend"]
if BACKEND not in AVAILABLE_BACKENDS:
    AVAILABLE_BACKENDS.insert(0, BACKEND)

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
