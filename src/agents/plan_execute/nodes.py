import os
import re
import shlex
import asyncio
from datetime import date

from .state import State, StepStatus, Step, Plan
from .tools import breakdown_task, bound_replan_context
from src.tools.registry import (
    tavily_search, today_date,
    shell_command_tool, write_file_tool, delete_file_tool, start_dev_server_tool,
)
from src.sandbox.shell_runner import make_project_workspace
from langchain_core.messages import HumanMessage, SystemMessage
from .llm import get_llm
from src.sandbox.runner import run_in_sandbox
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt
from src.tools.risk_classifier import classify_tool_risk, RiskLevel
from src.synthesis.codegen import declare_schema, generate_function_code
from src.synthesis.validator import validate_synthesized_function
from src.synthesis.registry import default_registry
from src.synthesis.schema import SynthesizedTool


_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


_SHORT_RESULT_CHAR_LIMIT = 200


def _search_relevance_validation_enabled() -> bool:
    """Keep the costly second LLM search check opt-in for production runs."""
    return os.getenv("VALIDATE_SEARCH_RELEVANCE", "false").lower() in {"1", "true", "yes"}


def _log_approval(state: State, tool: str, details: str) -> dict:
    """
    Log LOW-risk tool execution without interrupting.
    
    This is called before LOW-risk tool execution to provide visibility
    into what the agent is doing without requiring human approval.
    """
    approval_event = {
        "tool": tool,
        "risk_level": "LOW",
        "details": details,
        "timestamp": date.today().isoformat(),
    }
    print(f"⚠️ Executing LOW-risk operation: {tool} - {details[:100]}")
    return {"approval_events": [approval_event]}


def _extract_search_context(plan, current_step) -> str:
    """
    Build a short, targeted context string from the most recent prior DONE
    step, to append to this step's search query.

    Only looks at the single most recent prior step (not all of them) and
    only uses its result if it's short — i.e. looks like a reasoning-step
    conclusion (e.g. "The current year is 2026.") rather than a raw scraped
    search result. This deliberately does NOT concatenate every prior
    result — that would bloat the query with noise and degrade search
    relevance rather than improve it.

    Additionally, scans ALL prior DONE step results (short or long) for a
    plausible year, since a correctly-determined year is the single most
    common piece of context a later search needs (see: "who won world cup
    this year" — the year is what search needs, not the surrounding prose).
    """
    prior_done_steps = [
        s for s in plan.subtasks
        if s.id != current_step.id and s.status == StepStatus.DONE and s.result
    ]
    # Only steps that come before this one in the plan
    prior_done_steps = [s for s in prior_done_steps if s.id < current_step.id]
    if not prior_done_steps:
        return ""

    context_parts = []

    # 1. Most recent short prior result — folded in directly.
    most_recent = max(prior_done_steps, key=lambda s: s.id)
    if len(most_recent.result) <= _SHORT_RESULT_CHAR_LIMIT:
        context_parts.append(most_recent.result.strip())

    # 2. Any year mentioned in ANY prior DONE step — surfaced explicitly.
    # Search separately from (1) since the year might be buried in a step
    # that isn't the most recent one, or in a result too long to fold in
    # directly.
    detected_years = []
    for step in prior_done_steps:
        for match in _YEAR_PATTERN.finditer(step.result):
            detected_years.append(match.group())
    if detected_years:
        # Prefer the year from the most recent step if it appears in the
        # detected set; otherwise just take the most recently detected one.
        year = detected_years[-1]
        if year not in " ".join(context_parts):
            context_parts.append(year)

    return " ".join(context_parts)


# Words/phrases that signal a goal is asking about something time-relative —
# "latest", "recent", "current", "this year", etc. For these goals, knowing
# today's actual date is load-bearing for every downstream search (see: "who
# won the world cup this year" defaulting to 2022 because nothing in the
# pipeline was anchored to the real current date). Rather than relying on the
# LLM planner to remember to add a "determine the current date" step — which
# it does inconsistently — we detect this deterministically from the goal
# text and prepend a real date step every time, guaranteed, before the plan
# is even generated.
#
# NOTE: "todays?" (with an optional trailing s, no apostrophe needed) covers
# both "today's date" and the common typed form "todays date" — \btoday\b
# alone does NOT match "todays", since there's no word boundary between the
# "y" and the "s" (both are word characters), which was the original bug:
# "whats todays date ?" went completely undetected and fell through to a full
# unnecessary web search instead of using today_date() directly.
_RECENCY_KEYWORDS = re.compile(
    r"\b(latest|recent(?:ly)?|current(?:ly)?|now|todays?|this year|this month|"
    r"this week|so far|up[- ]to[- ]date|as of|ongoing|most recent)\b",
    re.IGNORECASE,
)

# Goals that are PURELY asking for the current date/day/time — as opposed to
# goals that merely reference recency in passing while asking about something
# else (e.g. "who won the world cup this year"). For these, planning and
# searching is pure waste: the whole goal is answered by a single
# today_date() call. Matched narrowly on purpose — this should only catch
# goals where the date genuinely IS the entire question, not just a
# component of a larger one.
_PURE_DATE_QUERY = re.compile(
    r"^\s*(what'?s?|whats|what is|tell me|give me)?\s*"
    r"(today'?s?|the current|current)\s*(date|day)\s*\??\s*$",
    re.IGNORECASE,
)


def _is_pure_date_query(goal: str) -> bool:
    """Return True if the goal is asking ONLY for today's date/day, with
    nothing else — in which case planning and searching are unnecessary."""
    return bool(_PURE_DATE_QUERY.match(goal.strip()))


def _needs_date_anchor(goal: str) -> bool:
    """Return True if the goal contains recency language that needs today's
    actual date resolved before anything else runs."""
    return bool(_RECENCY_KEYWORDS.search(goal))


def _make_date_anchor_step(next_id: int) -> Step:
    """
    Build a deterministic first step that calls today_date() directly —
    no LLM call, no search, just the real system date — and prepend it to
    the plan. Marked DONE immediately since there's nothing to execute; the
    fact is already known.
    """
    return Step(
        id=next_id,
        task="Determine today's actual date to anchor all recency-related reasoning and searches in this plan.",
        tool_hint="none",
        status=StepStatus.DONE,
        result=f"Today's date is {today_date()}.",
    )


def plan_node(state: State) -> dict:
    """Break down the input task into a plan using the breakdown_task function.

    Two deterministic shortcuts, both bypassing the LLM planner's own
    (inconsistent) judgment about when the date matters:

    1. Pure date queries ("what's today's date?", "whats todays date?") skip
       planning and search entirely — a single DONE step with the real date
       and an immediate final_answer is the whole plan. Previously even this
       trivial case triggered a full web search for something the process
       already knows via today_date().

    2. Goals that merely REFERENCE recency ("who won the world cup this
       year") get a date-anchor step prepended before the LLM planner's own
       steps, so every later step/search has the real date available from
       the start — see _extract_search_context, which auto-folds short prior
       results (including this anchor) into later search queries.
    """
    goal = state.get("input", "")

    print(f"\n{'='*80}")
    print(f"📋 Creating Plan")
    print(f"{'='*80}")
    print(f"Goal: {goal}")

    if _is_pure_date_query(goal):
        anchor_step = _make_date_anchor_step(next_id=1)
        plan = Plan(
            goal=goal,
            subtasks=[anchor_step],
            final_answer=anchor_step.result,
        )
        print(f"✅ Pure date query - skipping planning")
        return {"plan": plan}

    plan = breakdown_task(goal)

    if _needs_date_anchor(goal):
        anchor_step = _make_date_anchor_step(next_id=1)
        # Renumber the planner's own steps to come after the anchor step.
        for i, step in enumerate(plan.subtasks, start=2):
            step.id = i
        plan.subtasks = [anchor_step] + plan.subtasks

    print(f"✅ Plan created with {len(plan.subtasks)} steps:")
    for step in plan.subtasks:
        print(f"   Step {step.id}: {step.task} (tool: {step.tool_hint})")

    return {"plan": plan}



def _check_search_relevance(step_task: str, goal: str, result: str) -> tuple[bool, str]:
    """
    Ask the LLM whether a search result actually answers the step it was
    meant to answer, as opposed to merely having executed successfully.

    This closes a gap where a search could return DONE with plausible-looking
    but irrelevant/stale/off-target content (e.g. searching for "the most
    recent World Cup winner" and getting a list of historical winners with no
    signal about whether the current tournament has concluded). Previously
    nothing distinguished that from a genuinely useful result — both looked
    identical to the graph (status=DONE), so a bad result would flow straight
    into synthesis with no chance to replan around it.

    Returns (is_relevant, reason). reason is a short explanation used as the
    step's error message when irrelevant, so the replanner has something
    concrete to react to rather than just "step failed."

    Deliberately a single short, cheap LLM call — not full synthesis-grade
    reasoning — since this runs after every search and shouldn't meaningfully
    add to latency/cost per step.
    """
    # Truncate — this check only needs enough of the result to judge
    # relevance, not the full text (keeps the check itself fast and cheap).
    excerpt = result[:2000]

    check_prompt = f"""Goal: "{goal}"
Step this search was meant to answer: "{step_task}"

Search result excerpt:
{excerpt}

Does this search result contain information that actually answers the step above — not just topically related content, but the specific fact(s) needed?

Respond in EXACTLY this format, nothing else:
RELEVANT: yes or no
REASON: one short sentence explaining why"""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a strict relevance checker. Be skeptical — topically-related content that doesn't contain the specific answer counts as NOT relevant."),
        HumanMessage(content=check_prompt),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    is_relevant = True
    reason = ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("RELEVANT:"):
            is_relevant = "yes" in line.lower()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip() if ":" in line else ""

    if not reason:
        reason = "Search result did not contain the specific information needed for this step."

    return is_relevant, reason


def tavily_search_node(state: State) -> dict:
    """
    Execute Tavily search for the current step.
    
    This node is called when a step has tool_hint="web_search" or "tavily_search".
    It performs the search using the tavily_search function and updates the step
    with the result.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("tavily_search_node called with no plan in state")

    # Find the currently running step
    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("tavily_search_node called with no RUNNING step")

    # Log LOW-risk operation
    log_update = _log_approval(state, "tavily_search", current_step.task)

    try:
        # Extract search query from the task description, including goal context
        query = f"{plan.goal} — {current_step.task}"

        # Fold in short, targeted context from prior steps (e.g. a year
        # determined by an earlier reason_node step). Previously this
        # function had no visibility into prior results at all, so a
        # correctly-determined fact like "the current year is 2026" never
        # reached the actual search query — search would default to
        # historically dominant results instead of recency-anchored ones.
        search_context = _extract_search_context(plan, current_step)
        if search_context:
            query = f"{query} {search_context}"

        # Tavily rejects queries over 400 chars outright. A long goal string
        # combined with a long step task can exceed that easily — and
        # without capping here, a replan that only rewords the step task
        # (while the goal stays just as long) produces an equally-long query
        # every time, which the replan-identical-limit guard then
        # misreads as "no progress" and gives up rather than the query
        # ever actually getting short enough to succeed.
        # current_step.task and search_context are the specific, load-bearing
        # part of the query; plan.goal is broader framing that's useful but
        # droppable first when something has to give.
        TAVILY_MAX_QUERY_CHARS = 400
        if len(query) > TAVILY_MAX_QUERY_CHARS:
            query = f"{current_step.task} {search_context}".strip() if search_context else current_step.task
            if len(query) > TAVILY_MAX_QUERY_CHARS:
                query = query[:TAVILY_MAX_QUERY_CHARS].rstrip()

        # Determine search depth based on step type
        # Use "basic" for status-check queries, "advanced" for detailed searches
        task_lower = current_step.task.lower()
        status_check_keywords = ["status", "current stage", "has the", "is the", "what is the current", "ongoing", "progress"]
        is_status_check = any(keyword in task_lower for keyword in status_check_keywords)
        
        search_depth = "basic" if is_status_check else "advanced"

        # Bias toward live/news results when either the overall goal or this
        # specific step carries recency language ("latest", "current",
        # "this year", etc.) — reuses the same detection already built for
        # the deterministic date-anchor step, rather than a second regex.
        # This matters because general web search happily surfaces
        # well-indexed historical/reference content (e.g. a "F1 race winners"
        # page that still lists last year's race) even when a plain day-count
        # filter is applied — see tavily_search's recency_sensitive param.
        recency_sensitive = _needs_date_anchor(plan.goal) or _needs_date_anchor(current_step.task)

        result = tavily_search(query, search_depth=search_depth, recency_sensitive=recency_sensitive)

        # A search can succeed (no exception, real content returned) while
        # still being useless for this specific step — e.g. returning a
        # historical winners list when the step needed "has this year's
        # tournament concluded". Without this check that case looked
        # identical to a genuinely useful result (status=DONE), so it flowed
        # straight into synthesis with no opportunity to replan.
        # Search relevance checking is useful for benchmark/quality runs but
        # costs an additional model call for every successful search.  Keep it
        # opt-in; normal interactive runs rely on the planner and replanner.
        if not _search_relevance_validation_enabled():
            current_step.status = StepStatus.DONE
            current_step.result = result
            print(f"✅ Search completed")
            print(f"👁️  Result: {result[:300]}{'...' if len(result) > 300 else ''}")
        else:
            is_relevant, reason = _check_search_relevance(current_step.task, plan.goal, result)
            if is_relevant:
                current_step.status = StepStatus.DONE
                current_step.result = result
                print(f"✅ Search completed (relevance validated)")
                print(f"👁️  Result: {result[:300]}{'...' if len(result) > 300 else ''}")
            else:
                current_step.status = StepStatus.FAILED
                print(f"❌ Search result deemed irrelevant: {reason}")
                current_step.error = f"Search returned content, but it doesn't answer this step: {reason}"
                # Keep the raw result too — even an "irrelevant" search can carry
                # useful signal (e.g. a mention of "semi-finals" that hints at
                # what to search for next), and the replanner's context-building
                # step only looks at DONE steps' results, not FAILED ones' raw
                # result field, so this is preserved for debugging/visibility
                # without changing replan behavior.
                current_step.result = result
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)
        print(f"❌ Search error: {str(e)}")

    return {"plan": plan, "steps_executed": 1, **log_update}


def reason_node(state: State) -> dict:
    """
    Execute a step whose tool_hint is "none" — i.e. a pure-reasoning step with
    no external tool call (e.g. "determine the current date", "plan the
    itinerary", "create a budget", "identify the winner from prior results").

    Previously these steps were routed to `stub_node`, which just marked them
    DONE with a placeholder string and did no actual work. That silently
    dropped steps the planner considered load-bearing — e.g. "determine the
    current year" never running meant downstream searches had no year anchor,
    and "plan the itinerary" never running meant a trip-planning goal's core
    deliverable was just missing from the final answer.

    This node makes a real LLM call, grounded in:
      - the current date (so date/recency-dependent reasoning steps like
        "what year is it" or "has this event happened yet" have a real anchor
        instead of falling back on the model's stale training data)
      - the original goal
      - all prior DONE steps' results, so this step can build on earlier
        research (e.g. "plan the itinerary" can use the weather/accommodation
        results already gathered)
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("reason_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("reason_node called with no RUNNING step")

    # Log LOW-risk operation
    log_update = _log_approval(state, "reason", current_step.task)

    try:
        prior_context = []
        for step in plan.subtasks:
            if step.id == current_step.id:
                break
            if step.status == StepStatus.DONE and step.result:
                result_str = step.result
                if len(result_str) > 1500:
                    result_str = result_str[:1500] + "... [truncated]"
                prior_context.append(f"Step {step.id}: {step.task}\nResult: {result_str}")

        context_block = "\n\n".join(prior_context) if prior_context else "(no prior step results)"
        today = date.today().isoformat()

        reasoning_prompt = f"""Today's date is {today}.

Overall goal: "{plan.goal}"

You are performing ONE step of a larger plan toward that goal. This step requires reasoning/synthesis, not an external tool call.

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

Instructions:
- Complete this step directly and concretely, using today's date and the prior results above where relevant.
- If this step depends on information not present in the prior results and not derivable from today's date, say plainly what's missing rather than guessing.
- Do not restate the whole goal — just produce the output this specific step calls for.
- Be concise but complete."""

        llm = get_llm()
        messages = [
            SystemMessage(content="You are a careful reasoning assistant completing one step of a larger plan."),
            HumanMessage(content=reasoning_prompt),
        ]
        response = llm.invoke(messages)

        current_step.status = StepStatus.DONE
        current_step.result = response.content
        print(f"✅ Reasoning completed")
        print(f"👁️  Result: {response.content[:300]}{'...' if len(response.content) > 300 else ''}")
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)
        print(f"❌ Reasoning failed: {str(e)}")

    return {"plan": plan, "steps_executed": 1, **log_update}


# Exception types that are typically fixable with small code adjustments
_FIXABLE_ERRORS = {
    "ImportError",
    "ModuleNotFoundError",
    "IndexError",
    "KeyError",
    "AttributeError",
    "TypeError",
    "NameError",
}


def _is_fixable_error(error_message: str) -> bool:
    """
    Determine if an error is likely fixable with a small code adjustment.
    Fixable errors are typically import issues, index/key errors, or simple type mismatches.
    Logical errors (ValueError, AssertionError, etc.) are not considered fixable.
    """
    for error_type in _FIXABLE_ERRORS:
        if error_type in error_message:
            return True
    return False


def code_executor_node(state: State) -> dict:
    """
    Execute a step whose tool_hint is "code_executor" — generates and runs Python code.

    This node:
    1. Uses the LLM to generate Python code based on the step's task description
    2. Executes the code in the sandbox (subprocess isolation, timeout, memory limits)
    3. Auto-retries for fixable errors (import errors, index errors, etc.) up to 2 times
    4. Marks the step DONE with the result (stdout) or error message

    The code generation LLM is given:
    - The current step's task description
    - Prior DONE step results for context
    - Instructions to print results to stdout for capture
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("code_executor_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("code_executor_node called with no RUNNING step")

    # Run generated code from inside the actual project workspace, not the
    # sandbox's own throwaway scratch dir — otherwise a script that reads or
    # writes a file previously created by write_file (or read/deleted by any
    # other workspace-aware tool) can't find it, since it's looking in a
    # directory that has nothing to do with where that file actually lives.
    workspace_path = state.get("workspace_path") or None

    try:
        # Build context from prior DONE steps
        prior_context = []
        for step in plan.subtasks:
            if step.id == current_step.id:
                break
            if step.status == StepStatus.DONE and step.result:
                result_str = step.result
                if len(result_str) > 1500:
                    result_str = result_str[:1500] + "... [truncated]"
                prior_context.append(f"Step {step.id}: {step.task}\nResult: {result_str}")

        context_block = "\n\n".join(prior_context) if prior_context else "(no prior step results)"
        today = date.today().isoformat()

        # Determine whether this step needs concrete command-line argument
        # values (e.g. "take n as input" -> the script reads sys.argv[1]).
        # Without this, the generated code has nowhere to actually get a
        # real value from — run_in_sandbox() supports an `args` list, but
        # someone has to decide what goes in it. We ask the LLM the same
        # way approval_node pre-generates commands/paths: a small, focused
        # call before the main code-generation call.
        script_args: list[str] = []
        try:
            args_prompt = f"""Overall goal: "{plan.goal}"

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

This step's Python script will be run non-interactively — it cannot call input().
If it needs, it should read values from sys.argv (command-line arguments) instead.

Decide what command-line argument values (if any) this script needs, based on
the step description and prior results. For example, if the step says "print
the first 20 Fibonacci numbers", the script needs one argument: "20".

Rules:
- Output a JSON object with exactly one key: "args"
- "args" is a list of strings — the command-line argument values, in order.
- If the step doesn't need any input values (e.g. it's self-contained), output {{"args": []}}.
- No markdown fences around the JSON. Output only the raw JSON object."""

            args_llm = get_llm()
            args_response = args_llm.invoke([
                SystemMessage(content="You output only a raw JSON object with an 'args' key, no markdown."),
                HumanMessage(content=args_prompt),
            ])
            raw_args = args_response.content.strip()
            if raw_args.startswith("```"):
                lines = raw_args.split("\n")
                raw_args = "\n".join(line for line in lines if not line.startswith("```")).strip()
            import json
            args_data = json.loads(raw_args)
            script_args = [str(a) for a in args_data.get("args", [])]
        except Exception as e:
            # Fall back to no args rather than failing the whole step —
            # the generated code still has its own hardcoded-default
            # fallback per the prompt instructions below.
            print(f"⚠️ Failed to determine script args, proceeding with none: {e}")
            script_args = []

        args_note = (
            f"This script will be invoked with sys.argv[1:] = {script_args!r}. "
            f"Read the needed value(s) from sys.argv at those positions."
            if script_args
            else "This script will be invoked with no command-line arguments."
        )

        code_generation_prompt = f"""Today's date is {today}.

Overall goal: "{plan.goal}"

You are performing ONE step of a larger plan toward that goal. This step requires writing and executing Python code.

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

Instructions:
- Write Python code to complete this step directly and concretely.
- Use the prior results above where relevant.
- Print your final answer/result to stdout using print() — this is how the result will be captured.
- Keep the code simple and focused on the specific task.
- If you need to import modules, use standard library modules only (no external packages unless you're certain they're available).
- CRITICAL: Do NOT use input() for user input — the execution environment does not support interactive input. Instead:
  * {args_note}
  * If the task mentions taking a value as input, read it via sys.argv (e.g. `import sys; n = int(sys.argv[1]) if len(sys.argv) > 1 else 10`), keeping a sensible hardcoded default as a fallback in case no argument is passed.
- CRITICAL: If this step fetches or looks up real data (an API call, a URL request, reading a file that should already exist, etc.) and that operation fails, let the exception propagate — do NOT catch it and substitute a made-up, hardcoded, or placeholder value in its place. A script that silently invents a plausible-looking number/result when the real one couldn't be obtained is worse than one that visibly fails, because the failure becomes invisible to anything downstream (including the human relying on this answer). It's fine to catch an exception if you're then going to retry, log, or clean up — just don't let the recovery path be "pretend it worked."
- Do not include markdown code fences — output only the raw Python code."""

        llm = get_llm()
        
        # Generate code with auto-retry for fixable errors
        max_retries = 2
        generated_code = None
        last_error = None
        
        for attempt in range(max_retries + 1):
            messages = [
                SystemMessage(content="You are a Python code generator. Output only raw Python code, no markdown fences, no explanations."),
                HumanMessage(content=code_generation_prompt),
            ]
            
            if attempt > 0:
                # Add error context to help fix the code
                messages[-1] = HumanMessage(
                    content=code_generation_prompt + f"\n\nPrevious attempt failed with error:\n{last_error}\n\nFix the code and try again."
                )
            
            response = llm.invoke(messages)
            generated_code = response.content.strip()
            
            # Remove markdown fences if present
            if generated_code.startswith("```"):
                lines = generated_code.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                generated_code = "\n".join(lines).strip()
            
            # Execute the code in the sandbox
            result = run_in_sandbox(
                generated_code,
                timeout_seconds=15,
                memory_limit_mb=256,
                args=script_args,
                cwd=workspace_path,
            )
            
            if result.success:
                # Code executed successfully
                current_step.status = StepStatus.DONE
                current_step.result = result.stdout if result.stdout else "Code executed successfully with no output."
                print(f"✅ Code executed successfully")
                print(f"👁️  Result: {current_step.result[:300]}{'...' if len(current_step.result) > 300 else ''}")
                return {"plan": plan, "steps_executed": 1}
            else:
                # Code execution failed
                last_error = result.error or result.stderr or "Unknown error"
                print(f"❌ Code execution failed (attempt {attempt + 1}/{max_retries + 1}): {last_error[:200]}")
                
                # Check if this is a fixable error
                if _is_fixable_error(last_error) and attempt < max_retries:
                    # Retry with error context
                    print(f"🔄 Retrying with error context...")
                    continue
                else:
                    # Either not fixable or out of retries. This step never
                    # actually succeeded — it must be FAILED, not DONE.
                    # Previously this was marked DONE with the error text
                    # stuffed into .result, which meant: (a) _route_after_tool
                    # never saw a FAILED status, so the replanner never
                    # engaged for a code-exec failure, and (b) synthesize_node
                    # had no way to distinguish "this is the answer" from
                    # "this is an error message that happens to live in the
                    # result field" — a failed step could silently read as a
                    # legitimate finding in the final answer.
                    current_step.status = StepStatus.FAILED
                    error_message = f"Code execution failed: {last_error}"
                    if result.stdout:
                        error_message += f"\nStdout: {result.stdout}"
                    if result.stderr:
                        error_message += f"\nStderr: {result.stderr}"
                    current_step.error = error_message
                    current_step.result = error_message
                    return {"plan": plan, "steps_executed": 1}
        
        # Should not reach here, but handle gracefully. Same reasoning as
        # above — retries exhausted with no success means this step FAILED.
        current_step.status = StepStatus.FAILED
        final_error = f"Code execution failed after {max_retries + 1} attempts. Last error: {last_error}"
        current_step.error = final_error
        current_step.result = final_error
        return {"plan": plan, "steps_executed": 1}
        
    except Exception as e:
        # An exception in the node itself (not the sandboxed code) is also a
        # genuine failure, not a completed step.
        current_step.status = StepStatus.FAILED
        error_message = f"Code executor node error: {str(e)}"
        current_step.error = error_message
        current_step.result = error_message
        return {"plan": plan, "steps_executed": 1}


# ---------------------------------------------------------------------------
# Coding-agent nodes
# ---------------------------------------------------------------------------

def setup_workspace_node(state: State) -> dict:
    """
    Create a fresh project workspace directory and store its path in state.

    This is always the FIRST step for any app-building task. Subsequent nodes
    read workspace_path from state so they all operate inside the same directory.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("setup_workspace_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("setup_workspace_node called with no RUNNING step")

    # Log LOW-risk operation
    log_update = _log_approval(state, "setup_workspace", current_step.task)

    # Derive a slug from the goal for a human-readable directory name
    slug = "-".join(plan.goal.lower().split()[:4])
    slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug)[:40]

    workspace_path = make_project_workspace(slug)

    current_step.status = StepStatus.DONE
    current_step.result = f"Project workspace created at: {workspace_path}"
    print(f"✅ Workspace created: {workspace_path}")

    return {"plan": plan, "steps_executed": 1, "workspace_path": workspace_path, **log_update}


def _build_coding_context(plan, current_step) -> str:
    """Build a short prior-steps context block for coding node prompts."""
    prior = []
    for step in plan.subtasks:
        if step.id >= current_step.id:
            break
        if step.status == StepStatus.DONE and step.result:
            text = step.result if len(step.result) <= 1200 else step.result[:1200] + "... [truncated]"
            prior.append(f"Step {step.id} ({step.tool_hint}): {step.task}\nResult: {text}")
    return "\n\n".join(prior) if prior else "(no prior step results)"


def synthesize_tool_node(state: State) -> dict:
    """
    Handle a step whose tool_hint matched no fixed tool (tool_hint='synthesize_tool').

    Previously these steps fell through to stub_node, which marked the step
    DONE with a placeholder message — silently pretending success when
    nothing actually happened. This node gives them a real path: check if a
    matching capability was already synthesized earlier in this run (reuse
    it directly, no new LLM calls), and if not, run the full synthesis
    pipeline (declare schema -> generate code -> validate in sandbox ->
    register) with retry-on-validation-failure, matching the same
    generate/validate/retry shape code_executor_node already uses.

    On success the step is marked DONE and the synthesized tool is invoked
    immediately to actually complete the step (not just registered for
    hypothetical future use — the step that triggered synthesis still needs
    its own result). On failure after exhausting retries, the step is
    marked FAILED and the existing replanner takes it from there — no new
    failure-handling logic needed, matching every other node in this file.

    See src/synthesis/__init__.py module docstring for the full pipeline
    rationale and the motivating temperature-conversion trace.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("synthesize_tool_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("synthesize_tool_node called with no RUNNING step")

    context_block = _build_coding_context(plan, current_step)
    llm = get_llm()

    # --- Step 1: declare the schema (or reuse if we've synthesized this
    # exact capability already earlier in the run) ---
    try:
        schema = declare_schema(plan.goal, current_step.task, context_block, llm, registry=default_registry)
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"synthesize_tool_node: failed to declare schema: {e}"
        print(f"❌ Synthesis schema declaration failed: {e}")
        return {"plan": plan, "steps_executed": 1}

    existing = default_registry.get(schema.capability_name)
    if existing is not None:
        # Reuse: run the already-validated function against a FRESH input
        # relevant to this step (schema.example_input from THIS declaration
        # call reflects what THIS step actually needs, even though the
        # underlying capability/code is shared with an earlier step).
        result = validate_synthesized_function(existing.source_code, schema)
        default_registry.mark_used(schema.capability_name)
        if result.success:
            current_step.status = StepStatus.DONE
            current_step.result = (
                f"[reused synthesized tool: {schema.capability_name}] {result.output}"
            )
            print(f"✅ Reused synthesized tool '{schema.capability_name}' (used {existing.times_used}x)")
        else:
            # The reused tool didn't handle this step's specific input —
            # fall through to synthesizing a fresh one below rather than
            # failing outright, since the capability name matching doesn't
            # guarantee the exact same input shape across different steps.
            print(f"⚠️ Reused tool '{schema.capability_name}' failed on this step's input, re-synthesizing: {result.error}")
            existing = None

    if existing is None:
        # --- Steps 2-4: generate, validate, retry on failure ---
        max_retries = 2
        last_error = None
        generated_code = None
        validation_result = None

        for attempt in range(max_retries + 1):
            try:
                generated_code = generate_function_code(schema, llm, previous_error=last_error)
            except Exception as e:
                last_error = f"Code generation call failed: {e}"
                continue

            validation_result = validate_synthesized_function(generated_code, schema)
            if validation_result.success:
                break
            last_error = validation_result.error

        if validation_result is None or not validation_result.success:
            current_step.status = StepStatus.FAILED
            current_step.error = (
                f"synthesize_tool_node: '{schema.capability_name}' failed validation "
                f"after {max_retries + 1} attempts: {last_error}"
            )
            print(f"❌ Synthesis failed after {max_retries + 1} attempts: {last_error}")
            return {"plan": plan, "steps_executed": 1}

        # --- Step 5: register ---
        tool = SynthesizedTool(
            capability_name=schema.capability_name,
            description=schema.description,
            input_description=schema.input_description,
            output_description=schema.output_description,
            source_code=generated_code,
            example_input=schema.example_input,
            example_output=validation_result.output,
        )
        default_registry.register(tool)
        default_registry.mark_used(schema.capability_name)

        current_step.status = StepStatus.DONE
        current_step.result = f"[synthesized new tool: {schema.capability_name}] {validation_result.output}"
        print(f"✅ Synthesized and registered new tool '{schema.capability_name}'")
        print(f"   {schema.description}")

    return {"plan": plan, "steps_executed": 1}


def shell_node(state: State) -> dict:
    """
    Execute a shell command step (tool_hint='shell_command').

    Asks the LLM to produce the exact shell command to run for this step,
    then runs it via shell_command_tool inside the project workspace.
    The LLM receives the full goal, prior results, and the workspace path
    so it can construct the correct command (e.g. correct project root).
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("shell_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("shell_node called with no RUNNING step")

    workspace_path = state.get("workspace_path") or ""
    if not workspace_path:
        current_step.status = StepStatus.FAILED
        current_step.error = (
            "shell_node: no workspace_path in state. "
            "Ensure a setup_workspace step runs before any shell_command step."
        )
        return {"plan": plan, "steps_executed": 1}

    context_block = _build_coding_context(plan, current_step)

    command_prompt = f"""You are generating a single shell command to complete one step of building a software project.

Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output ONLY the raw shell command, nothing else. No explanation, no markdown.
- The command will run with cwd={workspace_path}, so paths relative to that are fine.
- Use non-interactive flags where available (e.g. npm --yes, npx --yes).
- For npx create-vite, use exactly: npx --yes create-vite@latest . --template react -- --skip-linter
  (NOTE: `--yes` alone does NOT suppress create-vite's linter/tooling prompt —
  as of recent create-vite versions this is a separate prompt gated behind
  its own flag, not the top-level --yes. Omitting `-- --skip-linter` will
  cause the command to hang or self-cancel waiting for interactive input
  that can never arrive in this environment.)
- Do NOT use shell operators (&&, ||, ;, |, $()) — output ONE command only.
- Do NOT use sudo."""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a shell command generator. Output only the raw command, no markdown, no explanation."),
        HumanMessage(content=command_prompt),
    ]

    try:
        # Check if command was pre-generated by approval_node
        if current_step.result and current_step.result.startswith("_PENDING_COMMAND:"):
            command = current_step.result.replace("_PENDING_COMMAND: ", "")
        else:
            response = llm.invoke(messages)
            command = response.content.strip()
            # Strip any accidental markdown fences the LLM might add
            if command.startswith("```"):
                lines = command.split("\n")
                command = "\n".join(
                    line for line in lines if not line.startswith("```")
                ).strip()

        # --- Guard: refuse to run long-running server commands here ---
        # shell_command_tool / run_shell_command blocks until the process
        # exits (that's correct for one-shot commands like npm install).
        # A dev server never exits on its own, so routing one here — via a
        # planner or replanner mistake — hangs the whole graph indefinitely
        # instead of failing. This has happened in practice (replanner
        # generating "npm run dev" as a shell_command "diagnostic" step
        # after a start_server failure). Catch it here as a deterministic
        # backstop in addition to the prompt-level guidance in
        # REPLAN_INSTRUCTIONS, since an LLM instruction is best-effort and
        # this failure mode hangs the CLI rather than just producing a
        # wrong answer — worth the extra certainty of a code-level check.
        #
        # IMPORTANT: match against tokenized words, not a raw substring
        # search on the whole command string. A substring check on "vite"
        # false-positives on "create-vite" (a normal one-shot scaffold
        # command, not a server start) — tokenizing avoids that class of
        # false positive entirely.
        try:
            command_tokens = [t.lower() for t in shlex.split(command)]
        except ValueError:
            command_tokens = command.lower().split()

        looks_like_server_start = (
            "vite" in command_tokens
            or "dev" in command_tokens  # e.g. "npm run dev", "next dev"
            or "start" in command_tokens  # e.g. "npm start"
            or "runserver" in command_tokens
            or "uvicorn" in command_tokens
            or ("-m" in command_tokens and "http.server" in command_tokens)
            or ("flask" in command_tokens and "run" in command_tokens)
        ) and not any(t in command_tokens for t in ("install", "build", "--version", "-v"))

        if looks_like_server_start:
            current_step.status = StepStatus.FAILED
            current_step.error = (
                f"REFUSED: '{command}' looks like a command that starts a "
                "long-running dev server. shell_command cannot run this — it "
                "blocks until the process exits, and a dev server never "
                "exits on its own, so this would hang indefinitely. Use "
                "tool_hint 'start_server' instead, which runs the process "
                "correctly (non-blocking, with a port-open timeout and "
                "stderr capture)."
            )
            current_step.result = f"Command attempted (refused): {command}"
            print(f"❌ Shell command refused (looks like server start): {command}")
            return {"plan": plan, "steps_executed": 1}

        result_str = shell_command_tool(command, workspace_path)

        if result_str.startswith("ERROR:"):
            current_step.status = StepStatus.FAILED
            current_step.error = result_str
            current_step.result = f"Command attempted: {command}\n{result_str}"
            print(f"❌ Shell command failed: {result_str[:200]}")
        else:
            current_step.status = StepStatus.DONE
            current_step.result = f"$ {command}\n{result_str}"
            print(f"✅ Shell command completed")
            print(f"👁️  Result: {result_str[:300]}{'...' if len(result_str) > 300 else ''}")

    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"shell_node error: {str(e)}"
        print(f"❌ Shell command error: {str(e)}")

    return {"plan": plan, "steps_executed": 1}


def write_file_node(state: State) -> dict:
    """
    Generate and write a source code file (tool_hint='write_file' or 'file_editor').

    The LLM generates the complete file content for the requested file. The
    node writes it to disk inside the project workspace via write_file_tool.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("write_file_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("write_file_node called with no RUNNING step")

    workspace_path = state.get("workspace_path") or ""
    if not workspace_path:
        current_step.status = StepStatus.FAILED
        current_step.error = (
            "write_file_node: no workspace_path in state. "
            "Ensure a setup_workspace step runs before any write_file step."
        )
        return {"plan": plan, "steps_executed": 1}

    context_block = _build_coding_context(plan, current_step)
    today = date.today().isoformat()

    file_prompt = f"""You are generating source code for one step of building a software project.

Today's date: {today}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly two keys:
    "path": relative file path from the project root (e.g. "src/App.jsx", "index.html")
    "content": the complete file content as a string
- No markdown fences around the JSON. Output only the raw JSON object.
- Write complete, working code — not stubs or placeholders.
- If this step requires writing multiple files, pick the most important one;
  the agent can write others in subsequent steps."""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a code generator. Output only a raw JSON object with 'path' and 'content' keys, no markdown."),
        HumanMessage(content=file_prompt),
    ]

    try:
        import json

        # Check if file path was pre-generated by approval_node
        if current_step.result and current_step.result.startswith("_PENDING_FILE_PATH:"):
            rel_path = current_step.result.replace("_PENDING_FILE_PATH: ", "")
            # Generate content after approval
            content_prompt = f"""You are generating source code for one step of building a software project.

Today's date: {today}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}
File to write: {rel_path}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly one key: "content"
- "content" is the complete file content as a string
- No markdown fences around the JSON. Output only the raw JSON object.
- Write complete, working code — not stubs or placeholders."""

            llm = get_llm()
            messages = [
                SystemMessage(content="You are a code generator. Output only a raw JSON object with a 'content' key, no markdown."),
                HumanMessage(content=content_prompt),
            ]
            response = llm.invoke(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(line for line in lines if not line.startswith("```")).strip()
            data = json.loads(raw)
            content = data.get("content", "")
        else:
            response = llm.invoke(messages)
            raw = response.content.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(line for line in lines if not line.startswith("```")).strip()

            data = json.loads(raw)
            rel_path = data.get("path", "")
            content = data.get("content", "")

        if not rel_path:
            current_step.status = StepStatus.FAILED
            current_step.error = "write_file_node: LLM returned empty 'path'"
            return {"plan": plan, "steps_executed": 1}

        result_str = write_file_tool(rel_path, content, workspace_path)

        if result_str.startswith("ERROR:"):
            current_step.status = StepStatus.FAILED
            current_step.error = result_str
            print(f"❌ Write file failed: {result_str[:200]}")
        else:
            current_step.status = StepStatus.DONE
            current_step.result = f"{result_str}\nPath: {rel_path}"
            print(f"✅ File written: {rel_path}")
            print(f"👁️  Result: {result_str[:200]}")

    except json.JSONDecodeError as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"write_file_node: LLM returned invalid JSON: {e}"
        print(f"❌ Write file JSON error: {e}")
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"write_file_node error: {str(e)}"
        print(f"❌ Write file error: {str(e)}")

    return {"plan": plan, "steps_executed": 1}


def delete_file_node(state: State) -> dict:
    """
    Delete a file, directory, or clear the workspace (tool_hint='delete_file').

    Exists so steps like "delete all files in the project" have a real,
    safe path to succeed. Without this node, the executor's only option
    was shell_command with 'rm', which is intentionally blocked by
    ALLOWED_COMMANDS — every such step previously failed and forced a
    replan, and the replanner had no better alternative to reach for,
    so it thrashed through several blocked variants (rm, rm -rf *, a
    python+shutil one-liner that also failed since the sandbox's python
    binary isn't 'python') before hitting the replan cap and giving up.
    See agent_outputs/20260720-025417_.../plan.json and
    agent_outputs/20260720-121944_.../ for two reproduced instances.

    The LLM only needs to specify WHICH path to clear, not generate any
    content — much simpler than write_file_node.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("delete_file_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("delete_file_node called with no RUNNING step")

    workspace_path = state.get("workspace_path") or ""
    if not workspace_path:
        current_step.status = StepStatus.FAILED
        current_step.error = (
            "delete_file_node: no workspace_path in state. "
            "Ensure a setup_workspace step runs before any delete_file step."
        )
        return {"plan": plan, "steps_executed": 1}

    context_block = _build_coding_context(plan, current_step)
    today = date.today().isoformat()

    delete_prompt = f"""You are determining what to delete for one step of a software task.

Today's date: {today}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly one key: "path"
- "path" is a file or directory path relative to the workspace root (e.g. "old_notes.txt", "src/legacy/").
- If the step means clearing everything in the workspace (e.g. "delete all files"), use "" as the path.
- No markdown fences around the JSON. Output only the raw JSON object."""

    llm = get_llm()
    messages = [
        SystemMessage(content="You output only a raw JSON object with a 'path' key, no markdown."),
        HumanMessage(content=delete_prompt),
    ]

    try:
        import json

        # Check if path was pre-generated by approval_node
        if current_step.result and current_step.result.startswith("_PENDING_PATH:"):
            rel_path = current_step.result.replace("_PENDING_PATH: ", "")
        else:
            response = llm.invoke(messages)
            raw = response.content.strip()

            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(line for line in lines if not line.startswith("```")).strip()

            data = json.loads(raw)
            rel_path = data.get("path", "")

        result_str = delete_file_tool(rel_path, workspace_path)

        if result_str.startswith("ERROR:"):
            current_step.status = StepStatus.FAILED
            current_step.error = result_str
            print(f"❌ Delete failed: {result_str[:200]}")
        else:
            current_step.status = StepStatus.DONE
            current_step.result = result_str
            print(f"✅ {result_str}")

    except json.JSONDecodeError as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"delete_file_node: LLM returned invalid JSON: {e}"
        print(f"❌ Delete JSON error: {e}")
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"delete_file_node error: {str(e)}"
        print(f"❌ Delete error: {str(e)}")

    return {"plan": plan, "steps_executed": 1}


def start_server_node(state: State) -> dict:
    """
    Start a dev server and store its URL in state (tool_hint='start_server').

    Asks the LLM which command and port to use based on the project type
    (detected from prior step results), then starts the server via
    start_dev_server_tool. The URL is stored in state["server_url"] so
    synthesize_node can surface it in the final answer.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("start_server_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("start_server_node called with no RUNNING step")

    workspace_path = state.get("workspace_path") or ""
    if not workspace_path:
        current_step.status = StepStatus.FAILED
        current_step.error = (
            "start_server_node: no workspace_path in state. "
            "Ensure a setup_workspace step runs before start_server."
        )
        return {"plan": plan, "steps_executed": 1}

    context_block = _build_coding_context(plan, current_step)

    server_prompt = f"""You are determining how to start the dev server for a software project.

Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Output a JSON object with exactly two keys:
  "command": the server start command string (e.g. "npm run dev", "python3 -m http.server 3000")
  "port": the integer port number the server will listen on

Common conventions:
- Vite (React/Vue): command="npm run dev", port=5173
- Create React App: command="npm start", port=3000
- Next.js: command="npm run dev", port=3000
- Flask: command="python3 app.py", port=5000
- Express: command="node index.js", port=3000
- Python http.server: command="python3 -m http.server 8080", port=8080

No markdown fences — output only the raw JSON object."""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a dev server configuration expert. Output only a raw JSON object with 'command' and 'port' keys."),
        HumanMessage(content=server_prompt),
    ]

    try:
        import json

        response = llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(line for line in lines if not line.startswith("```")).strip()

        data = json.loads(raw)
        command = data.get("command", "npm run dev")
        port = int(data.get("port", 5173))

        url_or_error = start_dev_server_tool(command, workspace_path, port)

        if url_or_error.startswith("ERROR:"):
            current_step.status = StepStatus.FAILED
            current_step.error = url_or_error
            print(f"❌ Dev server failed: {url_or_error[:200]}")
            return {"plan": plan, "steps_executed": 1}

        # Success — record the URL
        current_step.status = StepStatus.DONE
        current_step.result = (
            f"✅ Dev server running at {url_or_error}\n"
            f"Command: {command}\nPort: {port}\nWorkspace: {workspace_path}"
        )
        print(f"✅ Dev server started at {url_or_error}")
        print(f"👁️  Command: {command}, Port: {port}")
        return {"plan": plan, "steps_executed": 1, "server_url": url_or_error}

    except json.JSONDecodeError as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"start_server_node: LLM returned invalid JSON: {e}"
        print(f"❌ Dev server JSON error: {e}")
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"start_server_node error: {str(e)}"
        print(f"❌ Dev server error: {str(e)}")

    return {"plan": plan, "steps_executed": 1}


# ---------------------------------------------------------------------------
# Trusted-source routing for browser automation
# ---------------------------------------------------------------------------

# Maps a topic to a list of (name, url) pairs for trusted, authoritative
# sources. When a step's task matches a topic (via keyword detection below),
# use_browser_node instructs the browser agent to visit these sites directly
# rather than doing an unconstrained open-web task — this trades some
# flexibility for much higher trust/accuracy on topics where source quality
# matters most (health, finance, legal, security, etc).
TRUSTED_SOURCES: dict[str, list[tuple[str, str]]] = {
    "health": [
        ("Mayo Clinic", "https://www.mayoclinic.org"),
        ("Cleveland Clinic", "https://my.clevelandclinic.org"),
        ("World Health Organization", "https://www.who.int"),
        ("MedlinePlus", "https://medlineplus.gov"),
        ("CDC", "https://www.cdc.gov"),
    ],
    "news": [
        ("Reuters", "https://www.reuters.com"),
        ("Associated Press", "https://apnews.com"),
        ("BBC News", "https://www.bbc.com/news"),
        ("The New York Times", "https://www.nytimes.com"),
        ("The Wall Street Journal", "https://www.wsj.com"),
    ],
    "technology": [
        ("Ars Technica", "https://arstechnica.com"),
        ("TechCrunch", "https://techcrunch.com"),
        ("The Verge", "https://www.theverge.com"),
        ("Wired", "https://www.wired.com"),
        ("Tom's Hardware", "https://www.tomshardware.com"),
    ],
    "education": [
        ("Khan Academy", "https://www.khanacademy.org"),
        ("MIT OpenCourseWare", "https://ocw.mit.edu"),
        ("Coursera", "https://www.coursera.org"),
        ("edX", "https://www.edx.org"),
        ("Britannica", "https://www.britannica.com"),
    ],
    "finance": [
        ("Investopedia", "https://www.investopedia.com"),
        ("Morningstar", "https://www.morningstar.com"),
        ("Bloomberg", "https://www.bloomberg.com"),
        ("The Wall Street Journal", "https://www.wsj.com"),
        ("U.S. SEC", "https://www.sec.gov"),
    ],
    "science": [
        ("Nature", "https://www.nature.com"),
        ("Science", "https://www.science.org"),
        ("Scientific American", "https://www.scientificamerican.com"),
        ("NASA", "https://www.nasa.gov"),
        ("National Geographic", "https://www.nationalgeographic.com"),
    ],
    "programming": [
        ("MDN Web Docs", "https://developer.mozilla.org"),
        ("Stack Overflow", "https://stackoverflow.com"),
        ("GitHub Docs", "https://docs.github.com"),
        ("W3Schools", "https://www.w3schools.com"),
        ("GeeksforGeeks", "https://www.geeksforgeeks.org"),
    ],
    "shopping": [
        ("Wirecutter", "https://www.nytimes.com/wirecutter"),
        ("Consumer Reports", "https://www.consumerreports.org"),
        ("RTINGS", "https://www.rtings.com"),
        ("PCMag", "https://www.pcmag.com"),
        ("CNET", "https://www.cnet.com"),
    ],
    "travel": [
        ("Lonely Planet", "https://www.lonelyplanet.com"),
        ("TripAdvisor", "https://www.tripadvisor.com"),
        ("Rick Steves", "https://www.ricksteves.com"),
        ("National Geographic Travel", "https://www.nationalgeographic.com/travel"),
        ("U.S. State Dept Travel Advisories", "https://travel.state.gov"),
    ],
    "food": [
        ("Serious Eats", "https://www.seriouseats.com"),
        ("King Arthur Baking", "https://www.kingarthurbaking.com"),
        ("BBC Good Food", "https://www.bbcgoodfood.com"),
        ("Allrecipes", "https://www.allrecipes.com"),
        ("America's Test Kitchen", "https://www.americastestkitchen.com"),
    ],
    "business": [
        ("Harvard Business Review", "https://hbr.org"),
        ("McKinsey & Company", "https://www.mckinsey.com"),
        ("The Economist", "https://www.economist.com"),
        ("World Bank", "https://www.worldbank.org"),
        ("IMF", "https://www.imf.org"),
    ],
    "ai_ml": [
        ("OpenAI", "https://openai.com"),
        ("Google AI", "https://ai.google"),
        ("Anthropic", "https://www.anthropic.com"),
        ("Hugging Face", "https://huggingface.co"),
        ("arXiv", "https://arxiv.org"),
    ],
    "cybersecurity": [
        ("CISA", "https://www.cisa.gov"),
        ("Krebs on Security", "https://krebsonsecurity.com"),
        ("OWASP", "https://owasp.org"),
        ("SANS Institute", "https://www.sans.org"),
        ("NIST", "https://www.nist.gov"),
    ],
    "weather": [
        ("National Weather Service", "https://www.weather.gov"),
        ("NOAA", "https://www.noaa.gov"),
        ("The Weather Channel", "https://weather.com"),
        ("AccuWeather", "https://www.accuweather.com"),
        ("WMO", "https://public.wmo.int"),
    ],
    "legal": [
        ("Cornell LII", "https://www.law.cornell.edu"),
        ("Justia", "https://www.justia.com"),
        ("FindLaw", "https://www.findlaw.com"),
        ("Supreme Court", "https://www.supremecourt.gov"),
    ],
}

# Keyword -> topic detection. Checked against the step's task text
# (lowercased). Order matters only in that the first topic whose keywords
# match wins — kept simple/deterministic rather than an LLM call, since this
# is a cheap pre-filter, not the actual research step.
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "health": ["health", "medical", "disease", "symptom", "medicine", "diagnosis", "treatment", "vaccine", "doctor", "illness"],
    "news": ["news", "current event", "breaking", "headline", "politics", "election"],
    "technology": ["technology", "tech news", "gadget", "software release", "hardware review", "device"],
    "education": ["learn", "course", "tutorial", "study", "education", "lecture"],
    "finance": ["stock", "invest", "finance", "market", "portfolio", "etf", "bond", "sec filing", "earnings"],
    "science": ["science", "research paper", "physics", "chemistry", "biology", "astronomy", "space"],
    "programming": ["code", "programming", "api", "documentation", "library", "framework", "syntax", "github"],
    "shopping": ["review", "buy", "product comparison", "best product", "shopping"],
    "travel": ["travel", "trip", "itinerary", "vacation", "visa", "flight", "destination"],
    "food": ["recipe", "cooking", "baking", "ingredient", "dish", "meal"],
    "business": ["business strategy", "economics", "economy", "corporate", "management", "gdp"],
    "ai_ml": ["machine learning", "artificial intelligence", " ai ", "llm", "neural network", "model training", "arxiv"],
    "cybersecurity": ["security vulnerability", "cyberattack", "malware", "cve", "cybersecurity", "data breach"],
    "weather": ["weather forecast", "temperature today", "storm", "climate data", "hurricane"],
    "legal": ["law", "legal", "statute", "court case", "regulation", "legislation"],
}


def _detect_trusted_topic(task_text: str) -> str | None:
    """
    Return the first topic whose keywords appear in the task text, or None
    if no topic matches. Deliberately simple substring matching — this is a
    pre-filter to decide whether to constrain the browser agent to a curated
    source list, not a classification step that needs to be exhaustively
    correct. False negatives just mean the agent falls back to open browsing;
    false positives are unlikely given the specificity of the keyword lists.
    """
    text = f" {task_text.lower()} "
    for topic, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return topic
    return None


def _build_trusted_source_task(original_task: str, topic: str) -> str:
    """
    Rewrite the browser task to instruct the agent to check trusted sources
    for this topic directly, rather than doing an open-ended web search. The
    agent is told to visit the listed URLs (in order) and stop as soon as it
    finds the information it needs, rather than mechanically visiting all of
    them regardless of task the — that would waste time/steps for simple
    lookups.
    """
    sources = TRUSTED_SOURCES.get(topic, [])
    source_lines = "\n".join(f"- {name}: {url}" for name, url in sources)
    return (
        f"{original_task}\n\n"
        f"This task falls under a topic where source trustworthiness matters. "
        f"Prioritize gathering the information from the following trusted "
        f"sources, visiting them directly by URL rather than doing a generic "
        f"web search. Try them in order and stop once you have what you need; "
        f"only fall back to a general web search if none of these sources "
        f"have the relevant information:\n{source_lines}"
    )


def use_browser_node(state: State) -> dict:
    """
    Execute a browser automation task using browser-use (tool_hint='use_browser').

    Before building the agent's task, checks whether the step's task matches
    a known topic (health, finance, programming, etc.) via keyword detection.
    If it does, the task given to the browser agent is rewritten to point it
    directly at a curated list of trusted URLs for that topic (see
    TRUSTED_SOURCES / _TOPIC_KEYWORDS above) instead of leaving source
    selection to unconstrained open-web browsing. This matters most for
    topics where source quality has outsized impact on correctness — health,
    finance, legal, cybersecurity, etc. — where an unconstrained agent could
    land on a low-quality or unreliable page that looks superficially
    relevant.

    If no topic matches, falls back to the original open-ended task exactly
    as before.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("use_browser_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("use_browser_node called with no RUNNING step")

    # Log LOW-risk operation
    log_update = _log_approval(state, "use_browser", current_step.task)

    try:
        # Import browser_use here to avoid import errors if not installed
        try:
            from browser_use import Agent
            from browser_use.llm import ChatOpenRouter
        except ImportError:
            current_step.status = StepStatus.FAILED
            current_step.error = (
                "browser-use library not installed. "
                "Install it with: pip install browser-use>=0.13.6"
            )
            print(f"❌ Browser automation failed: browser-use not installed")
            return {"plan": plan, "steps_executed": 1}

        import os
        from dotenv import load_dotenv
        load_dotenv()

        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_key:
            current_step.status = StepStatus.FAILED
            current_step.error = (
                "OPENROUTER_API_KEY not found in environment. "
                "Browser automation currently requires OpenRouter API key."
            )
            print(f"❌ Browser automation failed: OPENROUTER_API_KEY missing")
            return {"plan": plan, "steps_executed": 1}

        model = os.getenv("BROWSER_USE_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
        browser_llm = ChatOpenRouter(model=model, api_key=openrouter_key)

        # Detect whether this step's task matches a trusted-source topic and
        # rewrite the browser task accordingly.
        detected_topic = _detect_trusted_topic(current_step.task)
        if detected_topic:
            browser_task = _build_trusted_source_task(current_step.task, detected_topic)
            print(f"🔗 Trusted-source topic detected: '{detected_topic}' — routing browser agent to curated sources")
        else:
            browser_task = current_step.task

        agent = Agent(
            task=browser_task,
            llm=browser_llm,
        )

        loop = asyncio.get_event_loop()
        history = None
        try:
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, agent.run())
                    history = future.result()
            else:
                history = loop.run_until_complete(agent.run())
        except Exception as e:
            current_step.status = StepStatus.FAILED
            current_step.error = f"Browser automation execution failed: {str(e)}"
            print(f"❌ Browser automation execution error: {str(e)}")
            return {"plan": plan, "steps_executed": 1, **log_update}

        if history is None:
            current_step.status = StepStatus.FAILED
            current_step.error = "Browser automation returned no history/result"
            print(f"❌ Browser automation failed: no history returned")
            return {"plan": plan, "steps_executed": 1, **log_update}

        try:
            result = history.final_result()
            if not result:
                result = "Browser automation completed but returned no result"
        except Exception as e:
            current_step.status = StepStatus.FAILED
            current_step.error = f"Failed to extract result from browser history: {str(e)}"
            print(f"❌ Failed to extract result: {str(e)}")
            return {"plan": plan, "steps_executed": 1, **log_update}

        current_step.status = StepStatus.DONE
        current_step.result = result
        if detected_topic:
            current_step.result = f"[trusted sources: {detected_topic}] {result}"
        print(f"✅ Browser automation completed")
        print(f"👁️  Result: {result[:300]}{'...' if len(result) > 300 else ''}")

    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"use_browser_node error: {str(e)}"
        print(f"❌ Browser automation error: {str(e)}")

    return {"plan": plan, "steps_executed": 1, **log_update}

def ask_human_node(state: State) -> dict:
    """
    Handle LLM requests to ask the human a question.
    
    This node is called when the LLM wants to ask a human for clarification
    or input. It triggers an interrupt to pause execution and wait for human input.
    On resume, it returns the human's response to the LLM.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("ask_human_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("ask_human_node called with no RUNNING step")

    # Check if the step's result contains an ASK_HUMAN marker
    if current_step.result and current_step.result.startswith("[ASK_HUMAN:"):
        # Extract the question from the result
        question = current_step.result.replace("[ASK_HUMAN: ", "").rstrip("]")
        
        # Trigger interrupt to get human response
        question_payload = {
            "type": "human_question",
            "question": question,
            "step_id": current_step.id,
            "task": current_step.task,
        }
        
        human_response = interrupt(question_payload)
        
        # Log the question and response
        question_event = {
            "step_id": current_step.id,
            "question": question,
            "response": human_response,
            "timestamp": date.today().isoformat(),
        }
        
        print(f"❓ Human question: {question}")
        print(f"💬 Human response: {human_response}")
        
        # Return the human's response as the step result
        current_step.result = human_response
        current_step.status = StepStatus.DONE
        
        return {
            "plan": plan,
            "human_questions": [question_event],
        }
    else:
        # No question to ask, just proceed
        return {"plan": plan}


def approval_node(state: State) -> dict:
    """
    Handle human-in-the-loop approval for HIGH-risk operations.

    This node checks if a pending_approval exists in state. If so, it triggers
    an interrupt to pause execution and wait for human input. On resume, it
    processes the human's decision (approve/reject/alternative) and updates
    the step status accordingly.

    For HIGH-risk tools (shell_command, write_file, code_executor, start_server),
    this node is called before the actual tool execution to ensure human oversight.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("approval_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("approval_node called with no RUNNING step")

    # Check if this step requires approval (HIGH-risk tool)
    risk_level = classify_tool_risk(current_step.tool_hint)
    
    if risk_level != RiskLevel.HIGH:
        # LOW-risk tools don't require approval - skip this node
        return {"plan": plan}

    # Pre-generate operation details for display during approval
    command_to_show = None
    path_to_show = None
    file_path_to_show = None
    file_content_to_show = None
    code_to_show = None
    port_to_show = None
    synthesis_preview_to_show = None

    workspace_path = state.get("workspace_path") or ""

    if current_step.tool_hint == "shell_command" and workspace_path:
        try:
            context_block = _build_coding_context(plan, current_step)
            command_prompt = f"""You are generating a single shell command to complete one step of building a software project.

Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output ONLY the raw shell command, nothing else. No explanation, no markdown.
- The command will run with cwd={workspace_path}, so paths relative to that are fine.
- Use non-interactive flags where available (e.g. npm --yes, npx --yes).
- For npx create-vite, use exactly: npx --yes create-vite@latest . --template react -- --skip-linter
  (NOTE: `--yes` alone does NOT suppress create-vite's linter/tooling prompt —
  as of recent create-vite versions this is a separate prompt gated behind
  its own flag, not the top-level --yes. Omitting `-- --skip-linter` will
  cause the command to hang or self-cancel waiting for interactive input
  that can never arrive in this environment.)
- Do NOT use shell operators (&&, ||, ;, |, $()) — output ONE command only.
- Do NOT use sudo."""

            llm = get_llm()
            messages = [
                SystemMessage(content="You are a shell command generator. Output only the raw command, no markdown, no explanation."),
                HumanMessage(content=command_prompt),
            ]
            response = llm.invoke(messages)
            command_to_show = response.content.strip()
            if command_to_show.startswith("```"):
                lines = command_to_show.split("\n")
                command_to_show = "\n".join(
                    line for line in lines if not line.startswith("```")
                ).strip()
            # Store the command in the step so shell_node can use it
            current_step.result = f"_PENDING_COMMAND: {command_to_show}"
        except Exception as e:
            print(f"⚠️ Failed to generate command for approval: {e}")
            command_to_show = "(command generation failed)"

    elif current_step.tool_hint == "delete_file" and workspace_path:
        try:
            context_block = _build_coding_context(plan, current_step)
            delete_prompt = f"""You are determining what to delete for one step of a software task.

Today's date: {date.today().isoformat()}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly one key: "path"
- "path" is a file or directory path relative to the workspace root (e.g. "old_notes.txt", "src/legacy/").
- If the step means clearing everything in the workspace (e.g. "delete all files"), use "" as the path.
- No markdown fences around the JSON. Output only the raw JSON object."""

            llm = get_llm()
            messages = [
                SystemMessage(content="You output only a raw JSON object with a 'path' key, no markdown."),
                HumanMessage(content=delete_prompt),
            ]
            response = llm.invoke(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(line for line in lines if not line.startswith("```")).strip()
            import json
            data = json.loads(raw)
            path_to_show = data.get("path", "")
            # Store the path in the step so delete_file_node can use it
            current_step.result = f"_PENDING_PATH: {path_to_show}"
        except Exception as e:
            print(f"⚠️ Failed to generate path for approval: {e}")
            path_to_show = "(path generation failed)"

    elif current_step.tool_hint in ("write_file", "file_editor") and workspace_path:
        try:
            context_block = _build_coding_context(plan, current_step)
            file_prompt = f"""You are determining what file to write for one step of a software task.

Today's date: {date.today().isoformat()}
Overall goal: "{plan.goal}"

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Rules:
- Output a JSON object with exactly one key: "path"
- "path" is a file path relative to the workspace root (e.g. "index.js", "src/App.jsx").
- No markdown fences around the JSON. Output only the raw JSON object."""

            llm = get_llm()
            messages = [
                SystemMessage(content="You output only a raw JSON object with a 'path' key, no markdown."),
                HumanMessage(content=file_prompt),
            ]
            response = llm.invoke(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(line for line in lines if not line.startswith("```")).strip()
            import json
            data = json.loads(raw)
            file_path_to_show = data.get("path", "")
            # Store the path in the step so write_file_node can use it
            current_step.result = f"_PENDING_FILE_PATH: {file_path_to_show}"
        except Exception as e:
            print(f"⚠️ Failed to generate file path for approval: {e}")
            file_path_to_show = "(file path generation failed)"

    elif current_step.tool_hint not in (
        "web_search", "tavily_search", "code_executor", "none",
        "setup_workspace", "shell_command", "start_server",
    ) and current_step.tool_hint not in ("write_file", "file_editor", "delete_file"):
        # Unrecognized tool_hint -> synthesis will handle this step (see
        # graph.py routing). Preview via declare_schema ONLY (not the full
        # generate+validate pipeline) — running full synthesis here just to
        # preview it would mean paying for codegen+sandbox validation TWICE
        # (once to show, once for real in synthesize_tool_node) and risks
        # showing the human one generated function while a DIFFERENT one
        # (from a second, independent LLM call) actually executes — exactly
        # the command/execution mismatch the pre-generation pattern elsewhere
        # in this function exists to prevent. The schema declaration alone
        # (capability name, description, I/O shapes) is cheap, deterministic
        # enough to be a fair preview, and gives a human real signal on what
        # kind of code is about to be generated and run.
        try:
            from src.synthesis.codegen import declare_schema
            import json as _json

            context_block = _build_coding_context(plan, current_step)
            llm = get_llm()
            schema = declare_schema(plan.goal, current_step.task, context_block, llm, registry=default_registry)
            synthesis_preview_to_show = (
                f"Will synthesize a new tool: {schema.capability_name}\n"
                f"  {schema.description}\n"
                f"  Input: {schema.input_description}\n"
                f"  Output: {schema.output_description}"
            )
            # Cache the declared schema so synthesize_tool_node reuses THIS
            # exact declaration instead of calling declare_schema again —
            # same reuse pattern as _PENDING_COMMAND/_PENDING_FILE_PATH above.
            current_step.result = f"_PENDING_SCHEMA: {_json.dumps(schema.model_dump())}"
        except Exception as e:
            print(f"⚠️ Failed to preview synthesis for approval: {e}")
            synthesis_preview_to_show = "(synthesis preview generation failed)"

    # Trigger interrupt for HIGH-risk operations
    approval_request = {
        "type": "command_approval",
        "tool": current_step.tool_hint,
        "step_id": current_step.id,
        "task": current_step.task,
        "risk_level": "HIGH",
        "command": command_to_show,
        "path": path_to_show,
        "file_path": file_path_to_show,
        "synthesis_preview": synthesis_preview_to_show,
        "workspace_path": workspace_path,
    }
    
    # Call interrupt to pause execution and wait for human input
    human_response = interrupt(approval_request)
    
    # Process human's response after resume
    decision = human_response.get("decision", "reject")
    
    if decision == "approve":
        # Human approved - proceed with tool execution
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "approve",
            "timestamp": date.today().isoformat(),
        }
        print(f"✅ Human approved: {current_step.tool_hint} for step {current_step.id}")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }
    
    elif decision == "reject":
        # Human rejected - mark step as FAILED and route to replanner
        current_step.status = StepStatus.FAILED
        current_step.error = "Operation rejected by human"
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "reject",
            "timestamp": date.today().isoformat(),
        }
        print(f"❌ Human rejected: {current_step.tool_hint} for step {current_step.id}")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }
    
    elif decision == "alternative":
        # Human provided alternative input - use it for tool execution
        alternative_input = human_response.get("alternative_input", "")
        # Store alternative in step result for the tool node to use
        current_step.result = f"ALTERNATIVE_INPUT: {alternative_input}"
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "alternative",
            "alternative_input": alternative_input,
            "timestamp": date.today().isoformat(),
        }
        print(f"🔄 Human provided alternative for step {current_step.id}: {alternative_input[:100]}")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }
    
    else:
        # Unknown decision - treat as reject for safety
        current_step.status = StepStatus.FAILED
        current_step.error = f"Unknown approval decision: {decision}"
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "reject",
            "reason": f"Unknown decision: {decision}",
            "timestamp": date.today().isoformat(),
        }
        print(f"❌ Unknown decision '{decision}' - treating as reject")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }


def executor_node(state: State) -> dict:
    """
    Execute the next PENDING step in the plan.

    Finds the first step with status PENDING, marks it RUNNING, and returns
    the tool_hint for routing to the appropriate tool node.

    Only processes ONE step per call — the graph's conditional edge decides
    which tool node to route to based on tool_hint.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("executor_node called with no plan in state")

    next_step = next((s for s in plan.subtasks if s.status == StepStatus.PENDING), None)
    if next_step is None:
        # Nothing left to do - all steps are either DONE or FAILED
        return {"plan": plan}

    next_step.status = StepStatus.RUNNING

    print(f"\n{'='*80}")
    print(f"🔄 Executing Step {next_step.id}")
    print(f"{'='*80}")
    print(f"Task: {next_step.task}")
    print(f"Tool: {next_step.tool_hint}")

    return {"plan": plan}


def synthesize_node(state: State) -> dict:
    """
    Synthesize all step results into a final answer using the LLM.

    This node is called when all steps are complete and the final step has
    tool_hint="none". It concatenates all step results and asks the LLM to
    provide a comprehensive answer to the original goal.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("synthesize_node called with no plan in state")

    print(f"\n{'='*80}")
    print(f"🧠 Synthesizing Final Answer")
    print(f"{'='*80}")

    # Collect all step results
    step_results = []
    for step in plan.subtasks:
        if step.result:
            result_str = step.result
            if len(result_str) > 1500:
                result_str = result_str[:1500] + "... [truncated]"
            step_results.append(f"Step {step.id}: {step.task}\nResult: {result_str}")
        elif step.error:
            step_results.append(f"Step {step.id}: {step.task}\nError: {step.error}")

    if not step_results:
        # No results to synthesize
        plan.final_answer = "No step results were available to synthesize a final answer."
        return {"plan": plan}

    # Build synthesis prompt
    synthesis_prompt = f"""You are given the results of executing a multi-step plan toward this goal: "{plan.goal}"

For information/research goals: extract the specific facts that answer the goal, ignoring boilerplate.
For app-building goals: summarize what was built, what files were created, and — most importantly — how to access the running app.

Step results:
{chr(10).join(step_results)}

{f'\n✅ A dev server is running at: {state.get("server_url")}\n' if state.get("server_url") else ''}

Provide a clear, direct final answer. For apps, lead with the URL if one is running."""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a helpful synthesis assistant that combines information from multiple sources."),
        HumanMessage(content=synthesis_prompt),
    ]
    response = llm.invoke(messages)

    # Store the synthesis result directly on the plan. This no longer depends
    # on a step having tool_hint="none" existing in the plan — the planner
    # prompt isn't guaranteed to always emit one, and when it doesn't, the
    # synthesized answer was previously silently discarded.
    plan.final_answer = response.content

    return {"plan": plan}

MAX_REPLAN = 4
MAX_TOTAL_STEPS = 15
MAX_CONSECUTIVE_IDENTICAL_REPLANS = 2


def _check_replan_novelty(previous_context: list[str], new_context: list[str]) -> tuple[bool, str]:
    """
    Use LLM to determine if new replan provides meaningful new information.
    
    Compares the previous step results with the new step results to detect
    whether the replan actually produced new, useful information or if it's
    essentially repeating the same search results.
    
    Returns (has_new_info, reason).
    """
    if not previous_context:
        # First replan always has new info by definition
        return True, "First replan - no previous context to compare"

    # Avoid a model call for the common retry case where execution supplied
    # exactly the same context as the prior replan.
    if previous_context == new_context:
        return False, "No new step results since the previous replan"
    
    previous_str = "\n".join(previous_context)
    new_str = "\n".join(new_context)
    
    # Truncate to keep the check fast and cheap
    previous_excerpt = previous_str[:3000]
    new_excerpt = new_str[:3000]
    
    novelty_prompt = f"""Previous step results:
{previous_excerpt}

New step results:
{new_excerpt}

Does the new step results contain genuinely new information that wasn't present in the previous results? Consider:
- Are there new facts, dates, or specific details?
- Is there new perspective or analysis?
- Or is this essentially the same information rephrased?

Respond in EXACTLY this format, nothing else:
HAS_NEW_INFO: yes or no
REASON: one short sentence explaining why"""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a strict novelty checker. Be skeptical — rephrased or marginally different content counts as NOT having new information."),
        HumanMessage(content=novelty_prompt),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    has_new_info = True
    reason = ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("HAS_NEW_INFO:"):
            has_new_info = "yes" in line.lower()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip() if ":" in line else ""

    if not reason:
        reason = "Could not determine novelty - assuming new information" if has_new_info else "No meaningful new information detected"

    return has_new_info, reason


def replaner(state: State) -> dict:
    """
    Replan the remaining steps in the plan.

    This function is called when a step fails (status=FAILED) and it will evaluate
    the output of steps that are finished and will decied to continue or revies. It will
    generate a new plan for the remaining tasks, replacing the old plan
    in the state. The new plan will only include steps that are still
    PENDING or RUNNING, and will re-evaluate how to achieve the goal.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("replaner called with no plan in state")

    print(f"\n{'='*80}")
    print(f"🔄 Replanning")
    print(f"{'='*80}")

    # Check for consecutive identical replans - early termination
    consecutive_count = state.get("consecutive_identical_replans", 0)
    if consecutive_count >= MAX_CONSECUTIVE_IDENTICAL_REPLANS:
        print(f"❌ Consecutive identical replan limit reached ({MAX_CONSECUTIVE_IDENTICAL_REPLANS})")
        # Mark all remaining PENDING/RUNNING steps as CANCELLED
        cancelled_steps = [s for s in plan.subtasks if s.status in (StepStatus.PENDING, StepStatus.RUNNING)]
        for step in cancelled_steps:
            step.status = StepStatus.CANCELLED
            step.error = "Unable to find additional reliable information after multiple search attempts."
        plan.cancelled_steps.extend(cancelled_steps)
        # Remove cancelled steps from subtasks (filter by original status before we changed it)
        plan.subtasks = [s for s in plan.subtasks if s.status not in (StepStatus.CANCELLED,)]
        return {"plan": plan}

    # Check replan limit. `replan_count` accumulates via the sum_replan_count
    # reducer in state.py, so this reads the true total across all prior
    # replans, not just the delta from the last node call.
    current_replan_count = state.get("replan_count", 0)
    if current_replan_count >= MAX_REPLAN:
        print(f"❌ Replan limit reached ({MAX_REPLAN})")
        # Mark all remaining PENDING/RUNNING steps as CANCELLED instead of FAILED
        cancelled_steps = [s for s in plan.subtasks if s.status in (StepStatus.PENDING, StepStatus.RUNNING)]
        for step in cancelled_steps:
            step.status = StepStatus.CANCELLED
            step.error = f"Replan limit ({MAX_REPLAN}) exceeded - execution terminated"
        plan.cancelled_steps.extend(cancelled_steps)
        # Remove cancelled steps from subtasks (filter by original status before we changed it)
        plan.subtasks = [s for s in plan.subtasks if s.status not in (StepStatus.CANCELLED,)]
        return {"plan": plan}
    else:
        # Collect the results of completed steps — this reflects what actually
        # EXECUTED so far in this run (i.e. the outcome of the previous replan
        # cycle, if any).
        completed_results = []
        done_steps = []
        for step in plan.subtasks:
            if step.status == StepStatus.DONE:
                done_steps.append(step)
                if step.result:
                    completed_results.append(f"Step {step.id}: {step.task}\nResult: {step.result}")
            elif step.status == StepStatus.FAILED and step.error:
                completed_results.append(f"Step {step.id}: {step.task}\nError: {step.error}")

        # Compare THIS replan's incoming context (what execution has produced so
        # far) against what was on hand at the time of the LAST replan. This is
        # the correct comparison — real outcomes vs. real outcomes.
        #
        # Previously this compared `completed_results` against the results of the
        # brand-new plan `breakdown_task` was about to generate — but a
        # freshly-generated plan is always all-PENDING and has never executed, so
        # that comparison was structurally guaranteed to find "no new info" every
        # single time, regardless of whether the replan was actually repetitive.
        # That caused premature termination after just one real replan cycle.
        # Bound before novelty comparison as well as before planning. This
        # makes identical large results comparable without another model call.
        completed_results = bound_replan_context(completed_results)

        previous_context = state.get("last_replan_context")
        if previous_context is None:
            # No prior replan cycle to compare against yet (this is the first
            # replan in the run) — nothing to judge novelty against.
            has_new_info, novelty_reason = True, "First replan - no previous context to compare"
        else:
            has_new_info, novelty_reason = _check_replan_novelty(previous_context, completed_results)

        # Generate a new plan based on the original goal and the results of completed steps.
        new_plan = breakdown_task(plan.goal, context=completed_results)

        # Merge DONE steps back to preserve execution history and results for synthesis
        next_id = 1
        if done_steps:
            done_steps.sort(key=lambda s: s.id)
            for s in done_steps:
                s.id = next_id
                next_id += 1

        for s in new_plan.subtasks:
            s.id = next_id
            next_id += 1

        new_plan.subtasks = done_steps + new_plan.subtasks

        print(f"✅ New plan generated with {len(new_plan.subtasks)} steps")
        if not has_new_info:
            print(f"⚠️  No new information found (consecutive: {consecutive_count + 1})")

        # Return the delta only — do not mutate `state` directly. LangGraph applies
        # the registered reducers (see state.py) to whatever this dict returns;
        # writing to `state` in place bypasses that and can cause inconsistent
        # results when nodes run concurrently or the graph replays from a checkpoint.
        if has_new_info:
            # Reset consecutive counter when we have new information
            return {
                "plan": new_plan,
                "replan_count": 1,
                "consecutive_identical_replans": 0,
                "last_replan_context": completed_results,
            }
        else:
            # Increment consecutive counter when no new information. The reducer
            # now REPLACES rather than accumulates, so we must compute the new
            # value explicitly here rather than returning a delta of 1.
            return {
                "plan": new_plan,
                "replan_count": 1,
                "consecutive_identical_replans": consecutive_count + 1,
                "last_replan_context": completed_results,
            }