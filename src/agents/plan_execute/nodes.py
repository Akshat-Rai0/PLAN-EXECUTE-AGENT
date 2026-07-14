from .state import State
from .tools import breakdown_task


def plan_node(state: State) -> dict:
    """Break down the input task into a plan using the breakdown_task tool."""
    goal = state.get("input", "")
    plan = breakdown_task.invoke({"goal": goal})
    return {"plan": plan, "output": plan}