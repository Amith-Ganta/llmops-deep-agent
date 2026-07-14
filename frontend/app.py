"""Streamlit frontend for the deep-agent service.

Talks to the FastAPI service over HTTP — run the API first (locally, in
Docker, or through a kind/K8s port-forward), then point this UI at it:

    streamlit run frontend/app.py
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import requests
import streamlit as st

APP_TITLE = "LLMOps Deep Agent"
APP_ICON = "🤖"
DEFAULT_API_URL = os.environ.get("DEEPAGENT_API_URL", "http://localhost:8000")
CHAT_TIMEOUT_S = 300  # a deep-agent turn can take a while


# ── API client ───────────────────────────────────────────────────────────────
def api_get(base_url: str, path: str) -> tuple[dict | None, str | None]:
    """GET a JSON endpoint. Returns (payload, error)."""
    try:
        resp = requests.get(f"{base_url.rstrip('/')}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json(), None
    except requests.ConnectionError:
        return None, "connection refused — is the API running?"
    except requests.HTTPError as exc:
        return None, f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except requests.RequestException as exc:
        return None, str(exc)


def api_chat(base_url: str, message: str, thread_id: str) -> tuple[dict | None, str | None]:
    """POST /chat. Returns (payload, error)."""
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat",
            json={"message": message, "thread_id": thread_id},
            timeout=CHAT_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json(), None
    except requests.ConnectionError:
        return None, "Connection refused — is the API running at this URL?"
    except requests.Timeout:
        return None, f"The agent did not answer within {CHAT_TIMEOUT_S}s."
    except requests.HTTPError as exc:
        detail = exc.response.text[:500]
        if exc.response.status_code == 429 or "rate_limit" in detail:
            return None, "The LLM provider rate-limited the request (Groq free tier). Try again later."
        return None, f"HTTP {exc.response.status_code}: {detail}"
    except requests.RequestException as exc:
        return None, str(exc)


# ── Session state ────────────────────────────────────────────────────────────
def init_state() -> None:
    st.session_state.setdefault(
        "messages",
        [{"role": "assistant", "content": "Ask me to plan, research, or explain something.", "meta": None}],
    )
    st.session_state.setdefault("thread_id", f"ui-{uuid.uuid4().hex[:8]}")


# ── Sidebar ──────────────────────────────────────────────────────────────────
def render_sidebar() -> str:
    with st.sidebar:
        st.title("⚙️ Service")

        api_url = st.text_input("API URL", value=DEFAULT_API_URL,
                                help="Where the FastAPI service is listening")

        health, health_err = api_get(api_url, "/health")
        ready, ready_err = api_get(api_url, "/ready")
        if health and ready:
            st.success(f"API up · agent ready · v{health.get('version', '?')}", icon="✅")
        elif health:
            st.warning(f"API up, agent not ready: {ready_err}", icon="⚠️")
        else:
            st.error(f"API unreachable: {health_err}", icon="❌")

        info, _ = api_get(api_url, "/info")
        if info:
            st.subheader("🛰️ Live config")
            st.markdown(
                f"- **Model:** `{info.get('model')}`\n"
                f"- **Subagent:** `{info.get('subagent_model')}`\n"
                f"- **Backend:** `{info.get('backend')}`\n"
                f"- **Web search:** {'on' if info.get('web_search') else 'off'}\n"
                f"- **Subagents:** {'on' if info.get('subagents') else 'off'}\n"
                f"- **Langfuse tracing:** {'on' if info.get('langfuse_tracing') else 'off'}"
            )

        st.divider()
        st.subheader("🧵 Thread")
        st.code(st.session_state.thread_id, language=None)
        st.caption("Messages in one thread share the agent's conversation memory.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 New Thread", use_container_width=True):
                st.session_state.thread_id = f"ui-{uuid.uuid4().hex[:8]}"
                st.session_state.messages = [
                    {"role": "assistant", "content": "New thread started. Ask me anything.", "meta": None}
                ]
                st.rerun()
        with col2:
            if st.button("🗑️ Clear Chat", use_container_width=True):
                st.session_state.messages = [
                    {"role": "assistant", "content": "Chat cleared.", "meta": None}
                ]
                st.rerun()

        st.divider()
        st.caption(
            "Frontend → FastAPI → deep agent (Groq) → Langfuse traces. "
            "[Repo](https://github.com/Amith-Ganta/llmops-deep-agent)"
        )
    return api_url


# ── Feature cards ─────────────────────────────────────────────────────────────
def render_feature_cards() -> None:
    cols = st.columns(5)
    cards = [
        ("🚀 FastAPI service", "The agent runs behind /chat with health & readiness probes."),
        ("🔍 Langfuse tracing", "Every turn is traced — trace ID shown under each answer."),
        ("✅ Eval gate", "DeepEval LLM-as-judge blocks the Docker publish in CI."),
        ("📦 Docker + GHCR", "398 MB non-root image, published by GitHub Actions."),
        ("☸️ Kubernetes", "Helm chart with HPA — this UI works through a port-forward too."),
    ]
    for col, (title, desc) in zip(cols, cards, strict=True):
        with col:
            st.markdown(f"**{title}**")
            st.caption(desc)


# ── Chat ──────────────────────────────────────────────────────────────────────
def render_meta(meta: dict[str, Any] | None) -> None:
    if not meta:
        return
    parts = [f"⏱️ {meta['latency_ms']:,} ms"] if meta.get("latency_ms") is not None else []
    if meta.get("trace_id"):
        parts.append(f"🔍 trace `{meta['trace_id']}`")
    if parts:
        st.caption(" · ".join(parts))


def render_chat(api_url: str) -> None:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            render_meta(msg.get("meta"))

    prompt = st.chat_input("Ask the deep agent…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt, "meta": None})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Agent thinking…"):
            payload, err = api_chat(api_url, prompt, st.session_state.thread_id)

        if err:
            st.error(err)
            st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {err}", "meta": None})
            return

        meta = {"latency_ms": payload.get("latency_ms"), "trace_id": payload.get("trace_id")}
        st.markdown(payload["response"])
        render_meta(meta)
        st.session_state.messages.append({"role": "assistant", "content": payload["response"], "meta": meta})


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="wide")
    init_state()

    api_url = render_sidebar()

    st.title(f"{APP_ICON} {APP_TITLE}")
    st.caption(
        f"**API:** `{api_url}` &nbsp;|&nbsp; **Thread:** `{st.session_state.thread_id}`"
    )

    render_feature_cards()
    st.divider()
    render_chat(api_url)


if __name__ == "__main__":
    main()
