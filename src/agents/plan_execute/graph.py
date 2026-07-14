from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import plan_node, executor_node
from .state import State, StepStatus


def _has_pending_steps(state: State) -> str:
    """Conditional edge: loop back to executor while PENDING steps remain."""
    plan = state["plan"]
    if plan is None:
        return "end"
    if any(s.status == StepStatus.PENDING for s in plan.subtasks):
        return "continue"
    return "end"


def build_graph():
    """
    Compile the graph:
      START -> plan -> executor -> [loop back to executor while PENDING steps remain] -> END

    Checkpointer is InMemorySaver for now — swap to a persistent one
    (SQLite/Postgres) once you need runs to survive process restarts,
    which you will for the HITL interrupt/resume work later.
    """
    graph = StateGraph(State)

    graph.add_node("plan", plan_node)
    graph.add_node("executor", executor_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "executor")

    graph.add_conditional_edges(
        "executor",
        _has_pending_steps,
        {"continue": "executor", "end": END},
    )

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)