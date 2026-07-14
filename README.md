# LLMOps Deep Agent

[![ci](https://github.com/Amith-Ganta/llmops-deep-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Amith-Ganta/llmops-deep-agent/actions/workflows/ci.yml)

A production-style LLMOps pipeline around a **deep agent** (planning + subagents + skills, built on
[`deepagents`](https://github.com/langchain-ai/deepagents) / LangGraph):

- **Serve** — FastAPI service with liveness/readiness probes and per-thread conversations
- **Observe** — every agent turn traced end-to-end in **Langfuse** (LLM calls, tool calls, latency, token usage)
- **Evaluate** — **DeepEval** LLM-as-judge quality gate (answer relevancy + correctness) wired into CI
- **Ship** — Docker (non-root, 398 MB) → GitHub Actions (lint → test → eval gate → GHCR publish) → Helm chart on Kubernetes with HPA

```
        ┌────────────────────── Kubernetes (kind / EKS) ───────────────────────┐
        │  ConfigMap ──┐                                          ┌─ HPA 1→3   │
        │  Secret ─────┤                                          │  (cpu 70%) │
client ──► Service ────► FastAPI (app/) ──► deep agent (core/)  ◄─┘            │
        │              /health /ready /chat   │        │                       │
        └──────────────────────────────────────┼────────┼───────────────────────┘
                                               │        │
                                     Groq llama-3.3-70b │ Tavily web search
                                     (subagents: 8b)    │ + skills/ + AGENTS.md
                                               │
                                        Langfuse traces
```

## What the agent is

A research-style deep agent with:

- **Planning** (todo-list tool) and a **virtual file system** (`StateBackend`, or `FilesystemBackend`/`CompositeBackend` via config)
- **Subagents** — a `research-agent` on a cheaper model (`llama-3.1-8b-instant`) for parallel research
- **Skills** (`skills/`) — progressive-disclosure instructions for AWS, LangGraph, Python, report writing
- **Persistent agent memory** (`config/AGENTS.md`) and **Tavily** web search

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness — process is up, never touches the LLM |
| `/ready` | GET | Readiness — agent graph built successfully |
| `/info` | GET | Running config + the pickable `available_models` / `available_backends` lists |
| `/chat` | POST | One agent turn: `{"message": "...", "thread_id"?, "model"?, "backend"?}` → `{"response", "thread_id", "latency_ms", "trace_id", "model", "backend"}` |
| `/docs` | GET | OpenAPI UI |

Same `thread_id` = same conversation (LangGraph checkpointer). The returned `trace_id` links the
turn to its Langfuse trace.

`model` and `backend` are optional per-request overrides, validated against the `/info` lists.
Groq's free-tier rate limits are **per model**, so switching model when one hits its daily token
cap is a real workaround, not just a preference. Setting `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`
adds OpenAI (`gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4o`) and DeepSeek (`deepseek-chat`,
`deepseek-reasoner`) models to the list automatically — models whose key is missing are never
offered. `backend` picks one of the three deepagents memory types:

| Backend | Agent files live in… | Survives restart | Shared across threads |
|---|---|---|---|
| `StateBackend` | the conversation state | no | no |
| `FilesystemBackend` | real files under `workspace/` | yes | yes |
| `StoreBackend` | a LangGraph store (AGENTS.md pre-seeded) | no | yes |

Each `(model, backend)` combo gets its own agent instance and checkpointer, so conversation
history is kept per combo.

## Quickstart

```bash
cp .env.example .env        # fill in GROQ_API_KEY (required), TAVILY_API_KEY + LANGFUSE_* (optional)

# local
make install
make run                    # uvicorn on :8000

# docker
make docker-build
make docker-run             # :8000, reads .env

# kubernetes (kind)
make kind-up                # create cluster + metrics-server
make kind-load              # load the local image into the cluster
make deploy                 # secret from .env + helm upgrade --install
kubectl port-forward svc/deep-agent 8080:80
curl -X POST localhost:8080/chat -H "Content-Type: application/json" -d '{"message":"What is RAG?"}'
```

## Frontend (Streamlit)

A chat UI that talks to the API over HTTP — it works against any of the three run modes above
(local uvicorn, Docker, or a Kubernetes port-forward):

```bash
make frontend               # installs streamlit + requests, serves on :8501
```

Point the sidebar's **API URL** at wherever the service is listening (`http://localhost:8000`
for local/Docker, `http://localhost:8080` through the kind port-forward). The sidebar shows the
service's live `/health`, `/ready`, and `/info` state, plus **🧠 Model** and **💾 Memory**
dropdowns (populated from `/info`) to switch the LLM and the deepagents memory backend per
conversation; every answer displays its latency, the model/backend that produced it, and its
Langfuse trace ID. The UI holds no secrets and never touches the LLM directly — it is a pure
HTTP client, so the API stays the single deployable unit.

## Evaluation gate (DeepEval)

`evals/` runs the **real agent in-process** against a golden dataset and judges every answer with
two metrics:

| Metric | Threshold | What it checks |
|---|---|---|
| `AnswerRelevancyMetric` | 0.6 | Did the answer actually address the question? |
| `GEval` "Correctness" | 0.5 | Does it contain the expected facts (per-case criteria)? |

The judge is a custom `DeepEvalBaseLLM` wrapper (`evals/judge.py`) that auto-selects the best
provider from the keys available — **OpenAI `gpt-4o-mini` > DeepSeek `deepseek-chat` > Groq
`llama-3.3-70b-versatile`** (override with `EVAL_JUDGE=provider:model`). Evals run with web
search and subagents disabled so scores measure the model + prompt, not Tavily.

```bash
make evals        # locally
```

In CI the eval gate runs after unit tests and **blocks the Docker publish** on failure. If the
`GROQ_API_KEY` secret is not configured the gate is skipped with a visible warning instead of
failing the build.

> LLM-judged scores are probabilistic evidence, not proof — every metric runs with
> `include_reason=True` so failures explain themselves in the CI log.

## Observability (Langfuse)

`app/observability.py` attaches the Langfuse v3 `CallbackHandler` to every agent invocation when
`LANGFUSE_*` keys are present (and is a clean no-op when they're absent). Each `/chat` turn becomes
a trace with the full LangGraph run tree — model calls, tool calls, token counts, latency — tagged
with the `thread_id` as session id, so multi-turn conversations group together in the Langfuse UI.

## CI/CD (GitHub Actions)

```
push → lint (ruff) + unit tests (9, no API keys)
     → eval gate (DeepEval + Groq judge; skips with warning if no secret)
     → build & push ghcr.io/amith-ganta/llmops-deep-agent:{sha,latest}   (main only)
```

Unit tests stub the agent (`tests/conftest.py`) so they're fast and free; only the eval gate spends
tokens.

## Kubernetes (Helm)

`helm/deep-agent` deploys:

- **Deployment** — non-root (uid 1000), resources `250m/512Mi → 1cpu/1Gi`, env from ConfigMap
  (agent knobs) + Secret (API keys), liveness `/health`, readiness `/ready`
- **Service** — ClusterIP 80 → 8000
- **HPA** — `autoscaling/v2`, 1→3 replicas at 70 % CPU (needs metrics-server; on kind install it
  with `--kubelet-insecure-tls`)

```bash
kubectl create secret generic deep-agent-secrets --from-env-file=.env
helm upgrade --install deep-agent helm/deep-agent
```

## Configuration

All knobs are env vars (12-factor), defaults in [app/settings.py](app/settings.py):

| Variable | Default | Meaning |
|---|---|---|
| `GROQ_API_KEY` | — | **required** — agent + fallback eval judge |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | — | optional — unlock OpenAI / DeepSeek models in the picker and as eval judge |
| `EVAL_JUDGE` | auto by key | force the eval judge, e.g. `openai:gpt-4o` |
| `TAVILY_API_KEY` | — | web search (agent degrades gracefully without it) |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_BASE_URL` | — | tracing (off if unset) |
| `DEEPAGENT_MODEL` | `groq:llama-3.3-70b-versatile` | main agent model |
| `SUBAGENT_MODEL` | `groq:llama-3.1-8b-instant` | research subagent model |
| `DEEPAGENT_BACKEND` | `StateBackend` | default memory type: `StateBackend` \| `FilesystemBackend` \| `StoreBackend` |
| `AVAILABLE_MODELS` | 6 Groq models + key-gated OpenAI/DeepSeek | comma-separated whitelist clients may pick from per request |
| `ENABLE_WEB_SEARCH` / `ENABLE_SUBAGENTS` | `true` | feature flags |
| `EAGER_INIT` | `true` | build the agent at startup (readiness gate) |
| `SYSTEM_PROMPT` | research assistant | override the agent's instructions |
| `RECURSION_LIMIT` | `50` | LangGraph step budget per turn |

## Project layout

```
app/        FastAPI service: routes, settings, Langfuse wiring, agent runtime
core/       the deep agent: graph builder, backends, tools
frontend/   Streamlit chat UI — pure HTTP client of the API
config/     AGENTS.md — persistent agent memory
skills/     agent skills (progressive disclosure)
tests/      unit tests — agent stubbed, no keys needed
evals/      DeepEval golden-dataset gate — real agent + key-selected LLM judge
helm/       Helm chart (Deployment/Service/ConfigMap/HPA)
k8s/        kind cluster config
```

## Roadmap

- **Phase 2** — Terraform → EKS (managed node group, ECR, IRSA), remote state
- Prometheus `/metrics` + Grafana dashboard
- Streaming responses (SSE) from the agent graph

## Notes on free-tier limits

Groq free tier caps `llama-3.3-70b-versatile` at **100k tokens/day**; one deep-agent turn costs
~10k tokens (the agent's system prompt is large), and a full eval run ~40–50k including judge
calls. Budget accordingly or upgrade the Groq tier before running evals repeatedly.
