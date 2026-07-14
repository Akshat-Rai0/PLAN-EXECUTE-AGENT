from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import plan_node, executor_node, tavily_search_node
from .state import State, StepStatus


def _has_pending_steps(state: State) -> str:
    """Conditional edge: loop back to executor while PENDING steps remain."""
    plan = state["plan"]
    if plan is None:
        return "end"
    if any(s.status == StepStatus.PENDING for s in plan.subtasks):
        return "continue"
    return "end"


def _route_to_tool(state: State) -> str:
    """
    Route executor to the appropriate tool node based on the RUNNING step's tool_hint.
    
    Returns:
        "tavily_search" if tool_hint is "web_search" or "tavily_search"
        "stub" for other tool hints (placeholder for future tools)
        "end" if no RUNNING step found (all steps completed)
    """
    plan = state["plan"]
    if plan is None:
        return "end"
    
    running_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if running_step is None:
        # No running step - all steps must be DONE or FAILED
        return "end"
    
    tool_hint = running_step.tool_hint.lower()
    if tool_hint in ("web_search", "tavily_search"):
        return "tavily_search"
    
    # Placeholder for other tools - will route to stub for now
    return "stub"


def build_graph():
    """
    Compile the graph:
      START -> plan -> executor -> [route to tool based on tool_hint] -> executor -> [loop while PENDING] -> END

    Checkpointer is InMemorySaver for now — swap to a persistent one
    (SQLite/Postgres) once you need runs to survive process restarts,
    which you will for the HITL interrupt/resume work later.
    """
    graph = StateGraph(State)

    graph.add_node("plan", plan_node)
    graph.add_node("executor", executor_node)
    graph.add_node("tavily_search", tavily_search_node)
    
    # Stub node for tools not yet implemented
    def stub_node(state: State) -> dict:
        """Placeholder for tools not yet implemented."""
        plan = state["plan"]
        if plan is None:
            return {"plan": plan}
        
        running_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
        if running_step:
            running_step.status = StepStatus.DONE
            running_step.result = f"[stub] Tool not implemented for hint: {running_step.tool_hint}"
        
        return {"plan": plan}
    
    graph.add_node("stub", stub_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "executor")
    
    # Route from executor to appropriate tool node or end
    graph.add_conditional_edges(
        "executor",
        _route_to_tool,
        {
            "tavily_search": "tavily_search",
            "stub": "stub",
            "end": END,
        },
    )
    
    # After tool execution, route back to executor to check for more steps
    graph.add_edge("tavily_search", "executor")
    graph.add_edge("stub", "executor")

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)