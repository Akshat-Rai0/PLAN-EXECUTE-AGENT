"""
LLM-as-judge scoring for one completed run.

Design notes:
- Uses the same get_llm() the agents themselves use (see llm.py), so the
  judge respects whatever LLM_PROVIDER is configured in the environment —
  no separate judge-specific provider config to keep in sync.
- Judge output is forced to strict JSON via explicit prompt instructions
  and parsed defensively; a malformed judge response is reported as a
  judge_error rather than silently defaulting to a score (which would
  quietly corrupt the aggregate numbers).
- For the four deterministic synthesis_required goals (d2, d3, d4 — hash,
  color conversion, UUID format), an EXACT-MATCH check runs in addition to
  the LLM judge, since these have objectively correct answers that
  shouldn't depend on an LLM's judgment call. The exact-match result is
  reported alongside the judge's score, not instead of it, so a
  discrepancy between the two (e.g. judge says "correct" on a wrong hash)
  is itself visible in the report rather than hidden.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional

from src.eval.golden_dataset import GoldenGoal


@dataclass
class JudgeResult:
    goal_id: str
    completeness_score: float  # 0.0-1.0
    correctness_score: float  # 0.0-1.0
    reasoning: str
    judge_error: Optional[str] = None
    exact_match_result: Optional[bool] = None  # only set for deterministic goals


JUDGE_SYSTEM_PROMPT = """You are an evaluation judge for an AI agent's task completion.

You will be given:
1. The original goal the agent was asked to accomplish.
2. Explicit success criteria describing what a correct/complete answer looks like.
3. The agent's final answer.

Score the final answer on two dimensions, each 0.0 to 1.0:
- completeness: did the answer address everything the goal asked for?
- correctness: is the factual/technical content of the answer actually right?

Be strict. A well-written but factually wrong answer should score low on
correctness even if it scores high on completeness. A correct but
incomplete answer (e.g. missing one of several requested things) should
score high on correctness but lower on completeness.

Respond with ONLY a JSON object, no markdown fences, no preamble:
{"completeness_score": <float 0-1>, "correctness_score": <float 0-1>, "reasoning": "<1-3 sentences>"}
"""


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _exact_match_check(goal_id: str, final_answer: str) -> Optional[bool]:
    """
    Deterministic correctness check for goals with an objectively
    computable answer. Returns None for goals with no deterministic check
    defined (i.e. every goal except d2/d3/d4).
    """
    if final_answer is None:
        return None

    answer_lower = final_answer.lower()

    if goal_id == "d2":
        # SHA-256 of 'plan-execute-agent'
        expected = hashlib.sha256(b"plan-execute-agent").hexdigest()
        return expected.lower() in answer_lower

    if goal_id == "d3":
        # #FF5733 -> RGB(255, 87, 51)
        return all(str(n) in final_answer for n in (255, 87, 51))

    if goal_id == "d4":
        # A valid UUID4: 8-4-4-4-12 hex, version nibble '4', variant 8/9/a/b
        uuid4_pattern = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            re.IGNORECASE,
        )
        return bool(uuid4_pattern.search(final_answer))

    return None


def judge_run(goal: GoldenGoal, final_answer: Optional[str]) -> JudgeResult:
    """
    Score one run's final answer against its golden goal's success
    criteria. Handles the None/empty-answer case explicitly (a crashed or
    incomplete run) rather than sending an empty string to the judge and
    getting back a meaningless score.
    """
    if not final_answer or not final_answer.strip():
        return JudgeResult(
            goal_id=goal.id,
            completeness_score=0.0,
            correctness_score=0.0,
            reasoning="No final answer was produced (empty or missing) — scored 0/0 without invoking the judge.",
            exact_match_result=_exact_match_check(goal.id, ""),
        )

    exact_match = _exact_match_check(goal.id, final_answer)

    from src.agents.plan_execute.llm import get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    user_content = (
        f"GOAL:\n{goal.goal}\n\n"
        f"SUCCESS CRITERIA:\n{goal.success_criteria}\n\n"
        f"AGENT'S FINAL ANSWER:\n{final_answer}"
    )

    try:
        llm = get_llm()
        response = llm.invoke([
            SystemMessage(content=JUDGE_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        content = _strip_markdown_fences(response.content)
        data = json.loads(content)

        completeness = float(data["completeness_score"])
        correctness = float(data["correctness_score"])
        reasoning = str(data.get("reasoning", ""))

        # Clamp defensively — an LLM can still emit e.g. 1.2 despite
        # instructions, and an out-of-range score would silently skew
        # aggregate averages.
        completeness = max(0.0, min(1.0, completeness))
        correctness = max(0.0, min(1.0, correctness))

        return JudgeResult(
            goal_id=goal.id,
            completeness_score=completeness,
            correctness_score=correctness,
            reasoning=reasoning,
            exact_match_result=exact_match,
        )

    except Exception as e:
        return JudgeResult(
            goal_id=goal.id,
            completeness_score=0.0,
            correctness_score=0.0,
            reasoning="",
            judge_error=f"{type(e).__name__}: {e}",
            exact_match_result=exact_match,
        )
