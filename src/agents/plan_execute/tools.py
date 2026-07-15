import json
from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .state import Plan

MAX_RETRIES = 2

PROMPT_TEMPLATE = """Role:
You are a task planning assistant that breaks down complex goals into actionable steps.

Task:
Analyze the given goal and create a step-by-step plan to achieve it.

Constraints:
- Break down the goal into 3-7 clear, actionable steps
- Each step should be specific and executable
- Steps should follow a logical sequence
- Keep steps concise but descriptive
- For questions about current events (sports, news, tournaments, live data), first determine the current status/state before searching for outcomes or winners
- Avoid assumptions about event completion when dealing with time-sensitive topics
- If the goal references "the most recent match," treat that literally as the latest completed fixture — do not assume it means the tournament final unless the goal says so explicitly

Goal:
{goal}

Output format:
Return ONLY a valid JSON object with this exact structure, no markdown fences, no commentary:
{{
  "goal": "the original goal",
  "subtasks": [
    {{
      "id": 1,
      "task": "first step description",
      "tool_hint": "none",
      "status": "PENDING",
      "sensitive": false
    }}
  ]
}}

Notes:
- "tool_hint": suggest a tool (e.g., "web_search", "code_executor", "file_editor") or "none"
- "status": always "PENDING"
- "sensitive": true only if human confirmation should be required before this step runs
"""

RETRY_SUFFIX = """

Your previous response could not be parsed. Error:
{error}

Return ONLY the raw JSON object. No markdown code fences. No explanation text before or after."""


def _strip_markdown_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


def breakdown_task(goal: str) -> Plan:
    """
    Break down a goal into a validated Plan of Steps.
    Retries up to MAX_RETRIES times if the model returns invalid JSON
    or JSON that doesn't satisfy the Plan/Step schema.

    Raises RuntimeError if no valid plan is produced after all retries —
    callers must handle this rather than receiving silently broken data.
    """
    llm = get_llm()
    prompt = PROMPT_TEMPLATE.format(goal=goal)
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        messages = [
            SystemMessage(content="You are a helpful task planning assistant that outputs valid JSON."),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        content = _strip_markdown_fences(response.content)

        try:
            data = json.loads(content)
            plan = Plan.model_validate(data)
            return plan
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            prompt = PROMPT_TEMPLATE.format(goal=goal) + RETRY_SUFFIX.format(error=str(e))
            continue

    raise RuntimeError(
        f"breakdown_task: failed to produce a valid Plan after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )