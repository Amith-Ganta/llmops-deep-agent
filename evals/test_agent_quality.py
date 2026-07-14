"""LLM eval gate: the real deep agent answers a golden dataset in-process and
an LLM judge scores each answer. The judge auto-selects by available key —
DeepSeek > OpenAI > Groq (see evals/judge.py; override with EVAL_JUDGE).

Metrics per case:
  - AnswerRelevancyMetric (threshold 0.6): did the answer address the question?
  - GEval "Correctness"  (threshold 0.5): does it state the expected facts
    without contradicting them?

Scores are LLM-judged evidence, not proof — reasons are attached to failures.
Run:  pytest evals/ -v   (requires GROQ_API_KEY for the agent under test)
"""

import pytest
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric, GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from evals.dataset import GOLDEN_CASES
from evals.judge import ChatModelJudge

RELEVANCY_THRESHOLD = 0.6
CORRECTNESS_THRESHOLD = 0.5


@pytest.fixture(scope="session")
def judge():
    return ChatModelJudge()


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c["id"] for c in GOLDEN_CASES])
def test_agent_answer_quality(case, agent_answer, judge):
    answer = agent_answer(case["input"])
    assert isinstance(answer, str) and answer.strip(), "agent returned an empty answer"

    test_case = LLMTestCase(
        input=case["input"],
        actual_output=answer,
        expected_output=case["expected_output"],
    )

    relevancy = AnswerRelevancyMetric(
        threshold=RELEVANCY_THRESHOLD,
        model=judge,
        include_reason=True,
    )
    correctness = GEval(
        name="Correctness",
        criteria=(
            "The actual output must be factually consistent with the expected "
            "output and cover these facts: " + "; ".join(case["expected_facts"]) + ". "
            "Minor wording differences and extra correct detail are acceptable; "
            "missing or contradicted facts are not."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        threshold=CORRECTNESS_THRESHOLD,
        model=judge,
    )

    assert_test(test_case, [relevancy, correctness])
