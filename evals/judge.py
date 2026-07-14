"""LLM judge for the eval gate.

DeepEval's LLM-judged metrics default to OpenAI; this wrapper routes judging
through any LangChain chat model instead. The judge provider is picked from
whichever API key is configured:

    DEEPSEEK_API_KEY-> deepseek:deepseek-chat
    OPENAI_API_KEY  -> openai:gpt-4o-mini
    GROQ_API_KEY    -> groq:llama-3.3-70b-versatile   (fallback)

DeepSeek ranks first: gpt-4o-mini's AnswerRelevancy statement decomposition
consistently marks the elaborations in list-style answers as irrelevant
(scoring ~0.2 on correct answers); deepseek-chat judges them correctly.

Set EVAL_JUDGE (e.g. "openai:gpt-4o") to override the auto-selection.
"""

from __future__ import annotations

import os

from deepeval.models import DeepEvalBaseLLM
from langchain.chat_models import init_chat_model

_JUDGE_BY_KEY = [
    ("DEEPSEEK_API_KEY", "deepseek:deepseek-chat"),
    ("OPENAI_API_KEY", "openai:gpt-4o-mini"),
    ("GROQ_API_KEY", "groq:llama-3.3-70b-versatile"),
]


def pick_judge_model() -> str:
    """Return a 'provider:model' spec for the best judge the env can run."""
    override = os.getenv("EVAL_JUDGE", "").strip()
    if override:
        return override
    for key, spec in _JUDGE_BY_KEY:
        if os.getenv(key):
            return spec
    # No key at all: return the fallback spec; the run will fail with a clear
    # auth error rather than an import-time crash.
    return _JUDGE_BY_KEY[-1][1]


class ChatModelJudge(DeepEvalBaseLLM):
    """DeepEval judge backed by any LangChain chat model ('provider:model')."""

    def __init__(self, model_spec: str | None = None):
        self.model_spec = model_spec or pick_judge_model()
        self._model = init_chat_model(self.model_spec, temperature=0)

    def load_model(self):
        return self._model

    def generate(self, prompt: str, schema=None):
        model = self.load_model()
        if schema is not None:
            return model.with_structured_output(schema).invoke(prompt)
        return model.invoke(prompt).content

    async def a_generate(self, prompt: str, schema=None):
        model = self.load_model()
        if schema is not None:
            return await model.with_structured_output(schema).ainvoke(prompt)
        return (await model.ainvoke(prompt)).content

    def get_model_name(self) -> str:
        return self.model_spec
