"""FastAPI service exposing the deep agent.

Endpoints:
    GET  /health  — liveness (process is up; never touches the LLM)
    GET  /ready   — readiness (agent built successfully)
    GET  /info    — model/backend/tracing configuration
    POST /chat    — one agent turn on a conversation thread
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import agent_runtime, settings
from app.observability import current_trace_id, langfuse_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.EAGER_INIT:
        try:
            agent_runtime.get_agent()
        except Exception:
            # Stay alive so /health works and the pod can report not-ready.
            logger.exception("Agent warmup failed — /ready will return 503.")
    yield


app = FastAPI(
    title="LLMOps Deep Agent",
    version=settings.APP_VERSION,
    description="Deep agent (deepagents + LangGraph) served over HTTP with "
    "Langfuse tracing and a DeepEval-gated CI/CD pipeline.",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    backend: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    latency_ms: int
    trace_id: str | None = None
    model: str
    backend: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/ready")
def ready() -> dict:
    try:
        _, status = agent_runtime.get_agent()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"agent not ready: {exc}") from exc
    return {"status": "ready", "detail": status}


@app.get("/info")
def info() -> dict:
    return {
        "version": settings.APP_VERSION,
        "model": settings.MODEL,
        "subagent_model": settings.SUBAGENT_MODEL,
        "backend": settings.BACKEND,
        "available_models": settings.AVAILABLE_MODELS,
        "available_backends": settings.AVAILABLE_BACKENDS,
        "web_search": settings.ENABLE_WEB_SEARCH,
        "subagents": settings.ENABLE_SUBAGENTS,
        "langfuse_tracing": langfuse_enabled(),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    model = request.model or settings.MODEL
    backend = request.backend or settings.BACKEND
    if model not in settings.AVAILABLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown model {model!r} — available: {settings.AVAILABLE_MODELS}",
        )
    if backend not in settings.AVAILABLE_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown backend {backend!r} — available: {settings.AVAILABLE_BACKENDS}",
        )

    thread_id = request.thread_id or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        answer = agent_runtime.run_agent(request.message, thread_id, model, backend)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Agent invocation failed (thread=%s)", thread_id)
        if "rate_limit" in str(exc) or "Error code: 429" in str(exc):
            raise HTTPException(
                status_code=429,
                detail="LLM provider rate limit reached (Groq free tier) — try again later.",
            ) from exc
        raise HTTPException(status_code=500, detail=f"agent error: {exc}") from exc
    return ChatResponse(
        response=answer,
        thread_id=thread_id,
        latency_ms=int((time.perf_counter() - started) * 1000),
        trace_id=current_trace_id(),
        model=model,
        backend=backend,
    )
