"""Executor node — picks the next pending plan step."""

from ..state import State, StepStatus

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
