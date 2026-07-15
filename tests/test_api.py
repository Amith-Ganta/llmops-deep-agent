"""API contract tests — no API keys, no network: agent_runtime is stubbed."""

from fastapi.testclient import TestClient

from app import agent_runtime
from app.main import app


def make_client(monkeypatch, answer="stubbed answer"):
    monkeypatch.setattr(
        agent_runtime, "run_agent",
        lambda message, thread_id, model=None, backend=None: (
            answer,
            model or agent_runtime.settings.MODEL,
        ),
    )
    monkeypatch.setattr(
        agent_runtime, "get_agent",
        lambda model=None, backend=None: (object(), "stub agent"),
    )
    return TestClient(app)


def test_health(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_info_shape(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.get("/info")
    body = r.json()
    assert r.status_code == 200
    for key in ("model", "backend", "web_search", "langfuse_tracing"):
        assert key in body


def test_chat_returns_answer_and_thread(monkeypatch):
    with make_client(monkeypatch, answer="hello from agent") as client:
        r = client.post("/chat", json={"message": "hi"})
    body = r.json()
    assert r.status_code == 200
    assert body["response"] == "hello from agent"
    assert body["thread_id"]
    assert body["latency_ms"] >= 0


def test_chat_preserves_thread_id(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.post("/chat", json={"message": "hi", "thread_id": "t-123"})
    assert r.json()["thread_id"] == "t-123"


def test_chat_rejects_empty_message(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.post("/chat", json={"message": ""})
    assert r.status_code == 422


def test_info_exposes_choices(monkeypatch):
    with make_client(monkeypatch) as client:
        body = client.get("/info").json()
    assert isinstance(body["available_models"], list) and body["available_models"]
    assert body["model"] in body["available_models"]
    assert set(body["available_backends"]) >= {"StateBackend", "FilesystemBackend", "StoreBackend"}


def test_chat_echoes_model_and_backend(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.post(
            "/chat",
            json={"message": "hi", "model": "groq:llama-3.1-8b-instant", "backend": "StoreBackend"},
        )
    body = r.json()
    assert r.status_code == 200
    assert body["model"] == "groq:llama-3.1-8b-instant"
    assert body["backend"] == "StoreBackend"


def test_chat_rejects_unknown_model(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.post("/chat", json={"message": "hi", "model": "openai:gpt-99"})
    assert r.status_code == 400
    assert "unknown model" in r.json()["detail"]


def test_chat_rejects_unknown_backend(monkeypatch):
    with make_client(monkeypatch) as client:
        r = client.post("/chat", json={"message": "hi", "backend": "RedisBackend"})
    assert r.status_code == 400
    assert "unknown backend" in r.json()["detail"]


def test_chat_agent_failure_is_500(monkeypatch):
    def boom(message, thread_id, model=None, backend=None):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(agent_runtime, "run_agent", boom)
    with TestClient(app) as client:
        r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 500
    assert "model exploded" in r.json()["detail"]


def test_chat_rate_limit_is_429(monkeypatch):
    def limited(message, thread_id, model=None, backend=None):
        raise RuntimeError("Error code: 429 - rate_limit_exceeded for llama-3.3-70b")

    monkeypatch.setattr(agent_runtime, "run_agent", limited)
    with TestClient(app) as client:
        r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"]


def test_run_agent_retries_malformed_tool_call(monkeypatch):
    """A transient Groq tool_use_failed 400 is retried once, then succeeds."""
    calls = {"n": 0}

    class FlakyAgent:
        def invoke(self, payload, config):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("Error code: 400 - {'code': 'tool_use_failed'}")
            return {"messages": [type("Msg", (), {"content": "recovered"})()]}

    monkeypatch.setattr(
        agent_runtime, "get_agent", lambda model=None, backend=None: (FlakyAgent(), "stub")
    )
    monkeypatch.setattr(agent_runtime, "get_langfuse_handler", lambda: None)
    answer, _ = agent_runtime.run_agent("hi", "t-1")
    assert answer == "recovered"
    assert calls["n"] == 2


def test_run_agent_gives_up_after_max_attempts(monkeypatch):
    class AlwaysBroken:
        def invoke(self, payload, config):
            raise RuntimeError("Error code: 400 - {'code': 'tool_use_failed'}")

    monkeypatch.setattr(
        agent_runtime, "get_agent", lambda model=None, backend=None: (AlwaysBroken(), "stub")
    )
    monkeypatch.setattr(agent_runtime, "get_langfuse_handler", lambda: None)
    try:
        agent_runtime.run_agent("hi", "t-1")
        raise AssertionError("expected the error to propagate")
    except RuntimeError as exc:
        assert "tool_use_failed" in str(exc)


def test_run_agent_falls_back_to_deepseek_on_outage(monkeypatch):
    """A 429 from the primary provider reroutes the turn to FALLBACK_MODEL."""
    class RateLimited:
        def invoke(self, payload, config):
            raise RuntimeError("Error code: 429 - rate_limit_exceeded")

    class Healthy:
        def invoke(self, payload, config):
            return {"messages": [type("Msg", (), {"content": "deepseek answer"})()]}

    agents = {"groq:primary": RateLimited(), "deepseek:deepseek-chat": Healthy()}
    monkeypatch.setattr(
        agent_runtime, "get_agent",
        lambda model=None, backend=None: (agents[model], "stub"),
    )
    monkeypatch.setattr(agent_runtime, "get_langfuse_handler", lambda: None)
    monkeypatch.setattr(agent_runtime.settings, "FALLBACK_MODEL", "deepseek:deepseek-chat")
    answer, model_used = agent_runtime.run_agent("hi", "t-1", model="groq:primary")
    assert answer == "deepseek answer"
    assert model_used == "deepseek:deepseek-chat"


def test_run_agent_no_fallback_when_disabled(monkeypatch):
    class RateLimited:
        def invoke(self, payload, config):
            raise RuntimeError("Error code: 429 - rate_limit_exceeded")

    monkeypatch.setattr(
        agent_runtime, "get_agent",
        lambda model=None, backend=None: (RateLimited(), "stub"),
    )
    monkeypatch.setattr(agent_runtime, "get_langfuse_handler", lambda: None)
    monkeypatch.setattr(agent_runtime.settings, "FALLBACK_MODEL", "")
    try:
        agent_runtime.run_agent("hi", "t-1")
        raise AssertionError("expected the 429 to propagate")
    except RuntimeError as exc:
        assert "429" in str(exc)


def test_run_agent_no_fallback_on_our_own_bad_request(monkeypatch):
    """A 400-class error is our bug, not an outage — never rerouted."""
    class BadRequest:
        def invoke(self, payload, config):
            raise RuntimeError("Error code: 400 - invalid request payload")

    monkeypatch.setattr(
        agent_runtime, "get_agent",
        lambda model=None, backend=None: (BadRequest(), "stub"),
    )
    monkeypatch.setattr(agent_runtime, "get_langfuse_handler", lambda: None)
    monkeypatch.setattr(agent_runtime.settings, "FALLBACK_MODEL", "deepseek:deepseek-chat")
    try:
        agent_runtime.run_agent("hi", "t-1")
        raise AssertionError("expected the 400 to propagate")
    except RuntimeError as exc:
        assert "400" in str(exc)


def test_extract_answer_handles_content_blocks():
    class Msg:
        content = [{"type": "text", "text": "part1 "}, {"type": "text", "text": "part2"}]

    assert agent_runtime.extract_answer({"messages": [Msg()]}) == "part1 part2"


def test_extract_answer_handles_plain_string():
    class Msg:
        content = "plain"

    assert agent_runtime.extract_answer({"messages": [Msg()]}) == "plain"
    assert agent_runtime.extract_answer({"messages": []}) == ""
