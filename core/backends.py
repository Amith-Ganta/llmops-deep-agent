from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents.backends import StateBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.store import StoreBackend
from deepagents.backends.utils import create_file_data
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

AGENTS_MD = Path("config/AGENTS.md")


def load_agents_md() -> str:
    return AGENTS_MD.read_text(encoding="utf-8") if AGENTS_MD.exists() else ""


def create_backend(backend_name: str, workspace_root: Path) -> tuple[Any, dict[str, Any]]:
    """
    Return (backend, kwargs) to pass directly into create_deep_agent.

    backend_name options:
        "StateBackend"      — in-memory, lost on process exit
        "FilesystemBackend" — real disk under workspace_root
        "StoreBackend"      — LangGraph InMemoryStore, cross-thread
    """
    if backend_name == "StateBackend":
        return StateBackend(), {"checkpointer": MemorySaver()}

    if backend_name == "FilesystemBackend":
        return (
            FilesystemBackend(root_dir=str(workspace_root), virtual_mode=True),
            {
                "checkpointer": MemorySaver(),
                "memory": ["config/AGENTS.md"],
            },
        )

    # StoreBackend — seed AGENTS.md into the store once at build time
    store = InMemoryStore()
    agents_md = load_agents_md()
    if agents_md:
        store.put(("memories",), "AGENTS.md", create_file_data(agents_md))

    return (
        StoreBackend(store=store, namespace=lambda _: ("memories",)),
        {
            "checkpointer": MemorySaver(),
            "store": store,
            "memory": ["/AGENTS.md"],
        },
    )
