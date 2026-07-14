from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from pydantic import BaseModel, Field

from core.backends import create_backend, load_agents_md
from core.tools import build_web_search

SKILLS_ROOT = Path("skills")


class ResearchFinding(BaseModel):
    summary: str = Field(description="Short research summary")
    confidence: float = Field(description="Confidence score 0–1")
    sources: list[str] = Field(description="Source URLs")


def _skills_hint() -> str:
    if not SKILLS_ROOT.exists():
        return ""
    names = [d.name for d in sorted(SKILLS_ROOT.iterdir()) if d.is_dir()]
    if not names:
        return ""
    return (
        f"\n\nYou have access to these on-demand skills: {', '.join(names)}. "
        "Load the relevant SKILL.md only when the user's request matches that domain."
    )


def _build_subagents(
    web_search: Any | None,
    use_structured_output: bool,
    subagent_model: str,
) -> list[dict[str, Any]]:
    subagent: dict[str, Any] = {
        "name": "research-agent",
        "description": "Use for deep research, fact-finding, and source collection.",
        "system_prompt": (
            "You are a careful researcher. Search thoroughly, cite sources, "
            "and return concise, well-structured findings."
        ),
        "tools": [web_search] if web_search is not None else [],
        "model": subagent_model,
    }
    if use_structured_output:
        subagent["response_format"] = ResearchFinding
    return [subagent]


def build_agent(
    model: str,
    backend_name: str,
    workspace_root: str,
    system_prompt: str,
    enable_web_search: bool,
    enable_subagents: bool,
    use_structured_output: bool,
    subagent_model: str,
) -> tuple[Any, str]:
    """
    Build and return (agent, status_message).
    All parameters are plain strings/bools so the result is safely cacheable.
    """
    web_search, search_status = (
        build_web_search() if enable_web_search else (None, "Web search disabled.")
    )
    backend, backend_kwargs = create_backend(backend_name, Path(workspace_root))

    agents_md = load_agents_md()
    prompt_parts = [p for p in [system_prompt.strip(), agents_md.strip()] if p]
    full_prompt = ("\n\n---\n\n".join(prompt_parts) + _skills_hint()) or None

    subagents = (
        _build_subagents(web_search, use_structured_output, subagent_model)
        if enable_subagents
        else []
    )

    agent = create_deep_agent(
        model=model,
        tools=[web_search] if web_search is not None else [],
        backend=backend,
        subagents=subagents or None,
        system_prompt=full_prompt,
        **backend_kwargs,
    )
    return agent, search_status
