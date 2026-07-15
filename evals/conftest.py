"""Eval-suite fixtures: run the real agent in-process, deterministically.

Web search and subagents are disabled so evals cost zero Tavily calls and the
answer comes from a single model pass. Requires GROQ_API_KEY (agent + judge).
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# config/AGENTS.md and skills/ are resolved relative to CWD in core/
os.chdir(ROOT)

# Deterministic, key-light agent configuration — must be set before app imports
os.environ["ENABLE_WEB_SEARCH"] = "false"
os.environ["ENABLE_SUBAGENTS"] = "false"
os.environ["DEEPAGENT_BACKEND"] = "StateBackend"
os.environ["EAGER_INIT"] = "false"
# With search disabled, llama models sometimes hallucinate a search tool call
# (Groq rejects it with 400 tool_use_failed) — forbid tool use outright.
os.environ["SYSTEM_PROMPT"] = (
    "You are a helpful assistant. Answer every question directly from your own "
    "knowledge in plain text. Do NOT call any tools: no web search, no todo "
    "lists, no file operations. Just write the answer."
)
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")


@pytest.fixture(scope="session")
def agent_answer():
    """Session-scoped callable: question -> agent answer (one build per run)."""
    from app.agent_runtime import get_agent, run_agent

    agent, status = get_agent()
    if agent is None:
        pytest.fail(f"agent failed to build: {status}")

    def _ask(question: str) -> str:
        last_err = None
        for attempt in range(3):  # Groq tool_use_failed is transient; retry
            try:
                answer, _model = run_agent(
                    question, thread_id=f"eval-{abs(hash(question)) % 10**8}-{attempt}"
                )
                return answer
            except Exception as err:  # noqa: BLE001
                last_err = err
        raise last_err

    return _ask
