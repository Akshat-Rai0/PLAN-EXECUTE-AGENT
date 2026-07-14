from .state import State, StepStatus
from .tools import breakdown_task


def plan_node(state: State) -> dict:
    """Break down the input task into a plan using the breakdown_task function."""
    goal = state.get("input", "")
    plan = breakdown_task(goal)
    return {"plan": plan, "output": ""}


def executor_node(state: State) -> dict:
    """
    Execute the next PENDING step in the plan.

    Finds the first step with status PENDING, marks it RUNNING, dispatches
    it (stubbed for now — real tool dispatch lands in Step 4), and marks
    it DONE or FAILED based on the result.

    Only processes ONE step per call — the graph's conditional edge decides
    whether to loop back here or move on, based on whether PENDING steps
    remain. This mirrors your spec: the executor runs one step at a time,
    the replanner (not yet built) decides what happens after a failure.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("executor_node called with no plan in state")

    next_step = next((s for s in plan.subtasks if s.status == StepStatus.PENDING), None)
    if next_step is None:
        # Nothing left to do — shouldn't normally be reached if the
        # conditional edge is wired correctly, but fail loudly if it is.
        return {"plan": plan, "output": state.get("output", "")}

    next_step.status = StepStatus.RUNNING

    try:
        # STUB: real tool dispatch (search, file_editor, code_executor, ...)
        # keyed off next_step.tool_hint lands in Step 4. For now this just
        # simulates a successful execution so we can verify the loop/state
        # transitions work before wiring real tools.
        result = _stub_execute(next_step)
        next_step.status = StepStatus.DONE
        next_step.result = result
    except Exception as e:
        next_step.status = StepStatus.FAILED
        next_step.error = str(e)

    return {"plan": plan, "output": state.get("output", "")}


def _stub_execute(step) -> str:
    """Placeholder tool dispatch. Replace with real tool_hint-based routing."""
    return f"[stub] would execute via tool_hint={step.tool_hint!r}: {step.task}"