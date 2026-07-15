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
            step_results.append(f"Step {step.id}: {step.task}\nResult: {step.result}")
        elif step.error:
            step_results.append(f"Step {step.id}: {step.task}\nError: {step.error}")

    if not step_results:
        # No results to synthesize
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

    # Store the synthesis result in the plan (we'll need to add a field for this)
    # For now, we'll add it as a special result on a synthetic step or modify the plan
    # Let's add it as the result of the last step if it had tool_hint="none"
    for step in reversed(plan.subtasks):
        if step.tool_hint == "none":
            step.result = response.content
            break

    return {"plan": plan}