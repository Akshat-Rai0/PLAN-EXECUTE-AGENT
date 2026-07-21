import json
from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .state import Plan

MAX_RETRIES = 2
MAX_REPLAN_CONTEXT_CHARS = 12_000
MAX_REPLAN_CONTEXT_ITEM_CHARS = 1_800

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
- "tool_hint": suggest a tool from this list:
    "web_search"       - search the web for information
    "code_executor"    - write and execute a Python script
    "setup_workspace"  - create a project directory (use as FIRST step of any app/coding task)
    "shell_command"    - run a CLI command (npm init, npm install, npx create-vite, mkdir, git, etc.)
                          NOTE: 'rm' is NOT available via shell_command for safety reasons.
                          Use "delete_file" instead for any deletion — never plan a shell_command
                          step that deletes files.
    "write_file"       - write or edit a source code file inside the project workspace
    "delete_file"      - delete a file or directory inside the project workspace, or clear
                          everything in the workspace (e.g. "delete all files in the project")
    "start_server"     - start a dev server (use as LAST step of app-building tasks)
    "none"             - pure reasoning, no external tool
- "status": always "PENDING"
- "sensitive": true only if human confirmation should be required before this step runs

For most one-off computation (unit conversions, data transforms, calculations), prefer
"code_executor" — it already handles arbitrary Python computation directly. Only use a
tool_hint outside this list if the step genuinely needs a capability none of these cover
(e.g. calling a specific external API with its own auth/schema); an unrecognized tool_hint
will automatically trigger dynamic tool synthesis rather than failing the step.

For app/coding tasks, always follow this step order:
  1. setup_workspace (create the project directory)
  2. shell_command (scaffold, e.g. npx create-vite@latest . --template react)
  3. write_file (write/edit source files, one step per logical file group)
  4. shell_command (npm install or pip install)
  5. start_server (npm run dev, python3 -m http.server, uvicorn, etc.)

If the goal requires deleting or clearing files, always use "delete_file" — never
"shell_command" with rm, since rm is blocked and will always fail.
"""

RETRY_SUFFIX = """

Your previous response could not be parsed. Error:
{error}

Return ONLY the raw JSON object. No markdown code fences. No explanation text before or after."""


def _truncate_context_item(value: str, limit: int = MAX_REPLAN_CONTEXT_ITEM_CHARS) -> str:
    """Keep both the conclusion and tail of a long tool result."""
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit < 80:
        return value[:limit]
    tail_size = min(300, limit // 4)
    head_size = limit - tail_size
    omitted = len(value) - limit
    return f"{value[:head_size]}\n... [{omitted} characters omitted] ...\n{value[-tail_size:]}"


def bound_replan_context(
    context: list[str],
    max_chars: int = MAX_REPLAN_CONTEXT_CHARS,
) -> list[str]:
    """Bound replan input so repeated tool output cannot grow prompts forever.

    The plan and its full results remain available for final synthesis.  This
    only compacts the *working* context sent to the planner/novelty checker.
    """
    bounded: list[str] = []
    used = 0
    for item in context:
        compact = _truncate_context_item(item)
        separator_size = 1 if bounded else 0
        remaining = max_chars - used - separator_size
        if remaining <= 0:
            break
        if len(compact) > remaining:
            compact = _truncate_context_item(compact, remaining)
        bounded.append(compact)
        used += len(compact) + separator_size

    if len(bounded) < len(context):
        marker = f"[Replan context truncated: retained {len(bounded)} of {len(context)} step records]"
        if used + len(marker) + 1 <= max_chars:
            bounded.append(marker)
    return bounded


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


REPLAN_INSTRUCTIONS = """

Context of completed/failed steps:
{context_str}

Please revise/update the remaining steps of the plan based on the context above. Keep only pending and revised steps in the returned list of subtasks.

CRITICAL — read each failure reason carefully before writing new steps:
- If a step's error says a search "doesn't answer" or "doesn't specify" or "doesn't contain" the needed information, that means the search ran successfully but was too GENERIC or too BROAD. Do not repeat a similarly generic search — the new step's task description must be MORE SPECIFIC than the one that failed. Narrow it using any concrete details already surfaced in other steps' results (exact team/entity names, exact dates, tournament stage, match ID, etc.) rather than re-describing the same broad question in different words.
- Example: if "search for the latest match results" failed because the results were a generic schedule/fixture list with no explicit winner, the next step should target the SPECIFIC match already identified (e.g. "search for the result of the France vs Spain semi-final on July 14, 2026"), not a rephrased generic query like "find recent match results".
- If you cannot identify a more specific angle from the available context, say so explicitly in the step's task description (e.g. "no more specific match identified in prior results — broaden search to include result pages specifically, not schedule/fixture pages") rather than silently repeating the same query shape that already failed.
"""


def breakdown_task(goal: str, context: list[str] = None) -> Plan:
    """
    Break down a goal into a validated Plan of Steps.
    Retries up to MAX_RETRIES times if the model returns invalid JSON
    or JSON that doesn't satisfy the Plan/Step schema.

    Raises RuntimeError if no valid plan is produced after all retries —
    callers must handle this rather than receiving silently broken data.
    """
    llm = get_llm()
    if context:
        # Defence in depth: callers besides replaner can use this public
        # function, so never trust them to have already bounded the context.
        context = bound_replan_context(context)
        context_str = "\n".join(context)
        prompt = PROMPT_TEMPLATE.format(goal=goal) + REPLAN_INSTRUCTIONS.format(context_str=context_str)
    else:
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
            if context:
                prompt = PROMPT_TEMPLATE.format(goal=goal) + REPLAN_INSTRUCTIONS.format(context_str=context_str) + RETRY_SUFFIX.format(error=str(e))
            else:
                prompt = PROMPT_TEMPLATE.format(goal=goal) + RETRY_SUFFIX.format(error=str(e))
            continue

    raise RuntimeError(
        f"breakdown_task: failed to produce a valid Plan after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )