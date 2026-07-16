from datetime import date

from .state import State, StepStatus
from .tools import breakdown_task
from src.tools.registry import tavily_search
from langchain_core.messages import HumanMessage, SystemMessage
from .llm import get_llm

def plan_node(state: State) -> dict:
    """Break down the input task into a plan using the breakdown_task function."""
    goal = state.get("input", "")
    plan = breakdown_task(goal)
    return {"plan": plan}


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

    try:
        # Extract search query from the task description, including goal context
        query = f"{plan.goal} — {current_step.task}"
        
        # Determine search depth based on step type
        # Use "basic" for status-check queries, "advanced" for detailed searches
        task_lower = current_step.task.lower()
        status_check_keywords = ["status", "current stage", "has the", "is the", "what is the current", "ongoing", "progress"]
        is_status_check = any(keyword in task_lower for keyword in status_check_keywords)
        
        search_depth = "basic" if is_status_check else "advanced"
        
        result = tavily_search(query, search_depth=search_depth)
        current_step.status = StepStatus.DONE
        current_step.result = result
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)

    return {"plan": plan}


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
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)

    return {"plan": plan}


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
    synthesis_prompt = f"""You are given raw, noisy scraped web content related to: "{plan.goal}"

The content contains navigation menus, stadium tables, and unrelated trivia mixed in with the actual relevant facts. Your job:

1. Find the specific fact(s) that answer the goal — dates, scores, team names, match stage (group/knockout/semi/final).
2. Ignore boilerplate, image alt-text, navigation links, stadium capacity tables, and unrelated historical trivia.
3. Determine the MOST RECENT dated event relevant to the goal — sort by date, not by position in the text.
4. If the specific event asked about (e.g., "the final") hasn't occurred, identify the most recent completed match instead from the data provided, and answer using that — do not simply state that no winner was found.
5. Give a direct, confident answer grounded only in facts present in the search results. Do not hedge with "consult a live source" — you have the current data, use it.

Search results:
{chr(10).join(step_results)}"""

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

MAX_REPLAN = 3


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

    # Check replan limit. `replan_count` accumulates via the sum_replan_count
    # reducer in state.py, so this reads the true total across all prior
    # replans, not just the delta from the last node call.
    current_replan_count = state.get("replan_count", 0)
    if current_replan_count >= MAX_REPLAN:
        for step in plan.subtasks:
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING):
                step.status = StepStatus.FAILED
                step.error = f"Replan limit ({MAX_REPLAN}) exceeded - execution terminated"
        return {"plan": plan}

    # Collect the results of completed steps
    completed_results = []
    done_steps = []
    for step in plan.subtasks:
        if step.status == StepStatus.DONE:
            done_steps.append(step)
            if step.result:
                completed_results.append(f"Step {step.id}: {step.task}\nResult: {step.result}")
        elif step.status == StepStatus.FAILED and step.error:
            completed_results.append(f"Step {step.id}: {step.task}\nError: {step.error}")

    # Generate a new plan based on the original goal and the results of completed steps
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

    # Return the delta only — do not mutate `state` directly. LangGraph applies
    # the registered reducers (see state.py) to whatever this dict returns;
    # writing to `state` in place bypasses that and can cause inconsistent
    # results when nodes run concurrently or the graph replays from a checkpoint.
    return {"plan": new_plan, "replan_count": 1}

