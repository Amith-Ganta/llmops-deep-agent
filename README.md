# LLMOps Deep Agent

[![ci](https://github.com/Amith-Ganta/llmops-deep-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Amith-Ganta/llmops-deep-agent/actions/workflows/ci.yml)

A production-style LLMOps pipeline around a **deep agent** (planning + subagents + skills, built on
[`deepagents`](https://github.com/langchain-ai/deepagents) / LangGraph):

- **Serve** — FastAPI service with liveness/readiness probes and per-thread conversations
- **Observe** — every agent turn traced end-to-end in **Langfuse** (LLM calls, tool calls, latency, token usage)
- **Evaluate** — **DeepEval** LLM-as-judge quality gate (answer relevancy + correctness) wired into CI
- **Ship** — Docker (non-root, 398 MB) → GitHub Actions (lint → test → eval gate → GHCR + Docker Hub) → Helm chart, **live on AWS EKS** behind a public LoadBalancer, with HPA + Cluster Autoscaler
- **Survive** — automatic **DeepSeek fallback** when the primary provider is rate-limited or down (verified live in production, twice)

```
        ┌───────────────── AWS EKS (deep-agents-cluster, 2× t3.small) ─────────────────┐
        │  Secret (envFrom) ──┐                                     ┌─ HPA 1→10        │
        │  chart config: ─────┤                                     │  (cpu 50%)       │
internet ──► ELB ──► Service ──► FastAPI (app/) ──► deep agent  ◄───┤                  │
        │  (LoadBalancer)     /health /ready /chat   │       │      └─ Cluster         │
        └────────────────────────────────────────────┼───────┼──────── Autoscaler ─────┘
                                                     │       │
                                  Groq llama-3.3-70b │       │ Tavily web search
                                  (subagent: 20b)    │       │ + skills/ + AGENTS.md
                                          on outage ─┤
                                  DeepSeek deepseek-chat
                                                     │
                                              Langfuse traces
```

> **Live UI (Streamlit):** http://ac92bf82396074d1c9eea748febd1e3e-2038085742.us-east-1.elb.amazonaws.com
> **Live API:** http://a2e22fecbf11e4e7cafc556a913d4b32-1236537386.us-east-1.elb.amazonaws.com/docs
> — images `amith98480/llmops-deep-agent` + `-frontend` (Docker Hub, mirrored from GHCR, pinned by git SHA)

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

## Provider fallback (DeepSeek)

If the primary model's provider is **unresponsive** — rate limit (413/429), 5xx, timeout, or
connection failure — the turn is retried once on `FALLBACK_MODEL` (default `deepseek:deepseek-chat`
when `DEEPSEEK_API_KEY` is set). The classifier ([app/agent_runtime.py](app/agent_runtime.py))
only reroutes on *provider outage* signatures, never on our own bad requests, and the response
JSON's `"model"` field always reports which model actually answered, so fallbacks are visible to
clients and in Langfuse traces.

DeepSeek was chosen deliberately: it is a **different provider**, so a Groq-wide outage or an
exhausted Groq quota cannot take the fallback down with it. Both failure modes have been observed
live in production:

1. **413 TPM** — the agent's prompt (system prompt + tool schemas) is ~8.2k tokens; on a model
   with an 8k tokens-per-minute cap every call is rejected before it starts.
2. **429 TPD** — the daily 100k-token budget ran out mid-day; DeepSeek served the traffic until
   the rolling window recovered.

In both cases the pod logged `Primary model ... unresponsive ... falling back to
deepseek:deepseek-chat` and the user got an answer instead of an error.

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
provider from the keys available — **DeepSeek `deepseek-chat` > OpenAI `gpt-4o-mini` > Groq
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

These are the local/kind defaults; the EKS release below overrides them (LoadBalancer service,
HPA 1→10 at 50 %, image pinned to a git SHA).

## Production deployment (AWS EKS)

The same chart runs live on **EKS** (`deep-agents-cluster`, us-east-1, Kubernetes 1.35, managed
nodegroup of t3.small), exposed through classic ELBs:

- **Chat UI (Streamlit):** **http://ac92bf82396074d1c9eea748febd1e3e-2038085742.us-east-1.elb.amazonaws.com**
- **API:** **http://a2e22fecbf11e4e7cafc556a913d4b32-1236537386.us-east-1.elb.amazonaws.com** (`/docs` for the OpenAPI UI)

The frontend runs as its own Deployment + Service from `frontend/Dockerfile` and reaches the API
via in-cluster DNS (`http://<release>-deep-agent:80`), so the UI never depends on the API's
external hostname. Its pods carry a distinct `app.kubernetes.io/name` label — they must never
match the API Service's selector, or `/chat` traffic would be routed to Streamlit.

```bash
curl -X POST http://a2e22fecbf11e4e7cafc556a913d4b32-1236537386.us-east-1.elb.amazonaws.com/chat \
  -H "Content-Type: application/json" -d '{"message":"What is RAG?"}'
```

How the production release differs from a laptop deploy — each of these is a deliberate
operational choice:

- **Immutable image tags.** The Deployment pins `amith98480/llmops-deep-agent:<git-sha>` with
  `pullPolicy: IfNotPresent` — never `latest` + `Always`. Rollbacks are exact and "what is
  running?" has exactly one answer. Images are built once in CI (GHCR) and mirrored to Docker Hub
  with `docker buildx imagetools create` (registry-to-registry, no local pull).
- **No config drift.** All non-secret config (model choices etc.) lives in a `config:` map in
  `values.yaml`, rendered into env vars by a template `range` loop; secrets arrive via
  `envFrom: secretRef`, so new secret keys reach the pod without template edits. Nothing is ever
  `kubectl set env`-ed by hand — the chart is the single source of truth and `helm upgrade`
  reconciles everything.
- **Model policy from rate-limit math.** Groq free-tier limits are per model: the agent's prompt
  is ~8.2k tokens, so the primary must be a model whose TPM cap fits it —
  `llama-3.3-70b-versatile` (12k TPM) works, `gpt-oss-120b` (8k TPM) can never serve a single
  call. The 100k TPD cap ≈ 9–12 agent turns/day, after which the DeepSeek fallback takes over.
- **Autoscaling at both layers.** HPA (1→10 replicas at 50 % CPU — load-tested: scaled 1→6 under
  synthetic load) handles pod scaling; **Cluster Autoscaler** (installed with IRSA via an OIDC
  provider + a scoped IAM policy, ASG auto-discovery) adds nodes when pods go Pending.
- **Right-sizing evidence.** Fairwinds **VPA in recommender-only mode + Goldilocks** report actual
  usage (~15m CPU / ~121Mi) vs requests (200m / 256Mi) — headroom is deliberate; HPA owns replica
  count, so the VPA updater stays off (the two fight over the same signal otherwise).
- **Probes split by meaning.** Liveness `/health` never touches the LLM (a provider outage must
  not restart pods); readiness `/ready` gates on the agent graph being built.

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
| `FALLBACK_MODEL` | `deepseek:deepseek-chat` if `DEEPSEEK_API_KEY` set, else off | one retry on this model when the primary provider is unresponsive |
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

- ~~EKS (managed node group, IRSA, Cluster Autoscaler)~~ — **done, live** (see Production deployment)
- Terraform for the cluster + ECR (currently eksctl/CLI-provisioned)
- Prometheus `/metrics` + Grafana dashboard
- Streaming responses (SSE) from the agent graph

## Notes on free-tier limits

Groq free-tier limits are **per model** and come in two flavors that fail differently:

- **TPM (tokens/minute)** rejects a single oversized request with **413**. The agent's prompt
  (system prompt + tool schemas) is ~8.2k tokens, so any model with an 8k TPM cap (e.g.
  `gpt-oss-120b`) can never serve this agent at all — pick primaries whose TPM cap exceeds the
  prompt (`llama-3.3-70b-versatile`: 12k).
- **TPD (tokens/day)** returns **429** once the rolling daily budget is spent.
  `llama-3.3-70b-versatile` gets 100k/day; one agent turn costs ~10k, a full eval run ~40–50k
  including judge calls — that's ~9–12 turns/day before the DeepSeek fallback takes over.

Budget accordingly or upgrade the Groq tier before running evals repeatedly.
