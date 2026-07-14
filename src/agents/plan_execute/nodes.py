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
        result = tavily_search(query)
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
    synthesis_prompt = f"""Role:
You are a synthesis assistant that combines information from multiple steps into a comprehensive answer.

Original Goal:
{plan.goal}

Results from each step:
{chr(10).join(step_results)}

Task:
Synthesize the above results into a clear, comprehensive answer to the original goal.
Focus on the key information and provide a well-structured response."""

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