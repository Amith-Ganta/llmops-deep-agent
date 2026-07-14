"""API contract tests — no API keys, no network: agent_runtime is stubbed."""

from fastapi.testclient import TestClient

from app import agent_runtime
from app.main import app


def make_client(monkeypatch, answer="stubbed answer"):
    monkeypatch.setattr(agent_runtime, "run_agent", lambda message, thread_id: answer)
    monkeypatch.setattr(agent_runtime, "get_agent", lambda: (object(), "stub agent"))
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


def test_chat_agent_failure_is_500(monkeypatch):
    def boom(message, thread_id):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(agent_runtime, "run_agent", boom)
    with TestClient(app) as client:
        r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 500
    assert "model exploded" in r.json()["detail"]


def test_extract_answer_handles_content_blocks():
    class Msg:
        content = [{"type": "text", "text": "part1 "}, {"type": "text", "text": "part2"}]

    assert agent_runtime.extract_answer({"messages": [Msg()]}) == "part1 part2"


def test_extract_answer_handles_plain_string():
    class Msg:
        content = "plain"

    assert agent_runtime.extract_answer({"messages": [Msg()]}) == "plain"
    assert agent_runtime.extract_answer({"messages": []}) == ""
