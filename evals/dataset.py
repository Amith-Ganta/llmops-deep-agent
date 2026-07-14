"""Golden eval dataset.

Every question is answerable without web search (from the agent's AGENTS.md
context or general model knowledge), so the eval run is deterministic-ish and
free of Tavily usage. `expected_facts` feeds the GEval correctness criteria.
"""

GOLDEN_CASES = [
    {
        "id": "deep-agent-pillars",
        "input": "What are the four pillars of a deep agent? Answer briefly.",
        "expected_output": (
            "The four pillars of a deep agent are: (1) planning, e.g. a to-do/"
            "write_todos tool to break work into steps; (2) context engineering, "
            "e.g. an AGENTS.md file of instructions and memory; (3) subagents for "
            "delegating isolated tasks; and (4) a filesystem/backend for storing "
            "state and files."
        ),
        "expected_facts": [
            "planning (a todo tool such as write_todos)",
            "context engineering (AGENTS.md instructions/memory)",
            "subagents (task delegation)",
            "filesystem or backend access (state/file storage)",
        ],
    },
    {
        "id": "what-is-rag",
        "input": "In two or three sentences, what is Retrieval-Augmented Generation (RAG)?",
        "expected_output": (
            "RAG is a technique where an LLM's answer is grounded in documents "
            "retrieved from an external knowledge source. Relevant chunks are "
            "fetched (usually via embedding similarity search over a vector "
            "store) and injected into the prompt so the model answers from that "
            "context, reducing hallucinations and keeping answers current."
        ),
        "expected_facts": [
            "retrieves relevant documents/context from an external source",
            "retrieved context is added to the LLM prompt",
            "grounds generation, reducing hallucination / enabling up-to-date answers",
        ],
    },
    {
        "id": "k8s-deployment",
        "input": "In Kubernetes, what does a Deployment do? Keep it short.",
        "expected_output": (
            "A Deployment declaratively manages a set of identical pods via a "
            "ReplicaSet: you declare the desired number of replicas and the pod "
            "template, and it keeps that state, replacing failed pods and "
            "performing rolling updates and rollbacks when the spec changes."
        ),
        "expected_facts": [
            "manages replicated pods (via ReplicaSets) to match a desired state",
            "handles rolling updates and rollbacks",
            "self-heals by replacing failed pods",
        ],
    },
    {
        "id": "langfuse-purpose",
        "input": "What is Langfuse used for in an LLM application? Answer in 2-3 sentences.",
        "expected_output": (
            "Langfuse is an open-source LLM observability platform. It records "
            "traces of LLM calls and agent steps (inputs, outputs, latency, token "
            "usage and cost) so you can debug, monitor and evaluate an LLM "
            "application in production."
        ),
        "expected_facts": [
            "observability/tracing for LLM applications",
            "captures LLM call and agent-step details such as inputs/outputs, latency, tokens or cost",
            "used for debugging, monitoring or evaluating LLM apps",
        ],
    },
]
