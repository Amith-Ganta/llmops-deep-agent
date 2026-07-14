"""Custom DeepEval judge backed by Groq (no OpenAI key required).

DeepEval defaults to OpenAI for LLM-judged metrics; this wrapper routes the
judging calls to Groq's llama-3.3-70b-versatile via langchain-groq instead.
"""

from deepeval.models import DeepEvalBaseLLM
from langchain_groq import ChatGroq

JUDGE_MODEL_NAME = "llama-3.3-70b-versatile"


class GroqJudge(DeepEvalBaseLLM):
    def __init__(self, model_name: str = JUDGE_MODEL_NAME):
        self.model_name = model_name
        self._model = ChatGroq(model=model_name, temperature=0)

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
        return f"groq/{self.model_name}"
