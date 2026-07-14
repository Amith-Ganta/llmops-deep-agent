from __future__ import annotations

import os
from typing import Any, Literal

from tavily import TavilyClient


def build_web_search() -> tuple[Any | None, str]:
    """Return a ready-to-use web_search tool and a status message."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return None, "TAVILY_API_KEY not set — web search disabled."

    client = TavilyClient(api_key=api_key)

    def web_search(
        query: str,
        max_results: int = 5,
        topic: Literal["general", "news", "finance", "sports"] = "general",
        include_raw_content: bool = False,
    ) -> dict[str, Any]:
        """Search the web using Tavily and return results."""
        return client.search(
            query,
            max_results=max_results,
            topic=topic,
            include_raw_content=include_raw_content,
        )

    return web_search, "Tavily web search enabled."
