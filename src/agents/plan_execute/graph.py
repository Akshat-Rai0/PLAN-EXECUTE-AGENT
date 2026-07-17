from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import plan_node, executor_node, tavily_search_node, synthesize_node, replaner, reason_node, code_executor_node, MAX_TOTAL_STEPS
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
        "code_executor" if tool_hint is "code_executor" — executes LLM-generated Python code
        "reason" if tool_hint is "none" — a pure-reasoning step, now handled
            by reason_node with a real LLM call instead of being silently
            no-op'd by stub_node
        "stub" for any other/unimplemented tool hint (e.g. "file_editor") — still a placeholder
        "synthesize" only once no RUNNING step remains (all steps DONE/FAILED).
            This is the sole trigger for global synthesis now. Previously,
            tool_hint == "none" on ANY running step (not just a final one)
            routed straight to synthesize — so if the planner emitted more
            than one tool_hint="none" step (e.g. an "analyze results" step
            followed by a "compile answer" step), the first one would
            short-circuit the whole rest of the plan straight to synthesis,
            silently skipping every step after it.
    """
    plan = state["plan"]
    if plan is None:
        return "end"

    running_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if running_step is None:
        # No running step and no PENDING left (executor only sets RUNNING when
        # there's a PENDING step to pick up) - all steps are DONE/FAILED.
        # Always route to synthesize so a final answer is produced.
        return "synthesize"

    tool_hint = running_step.tool_hint.lower()
    if tool_hint in ("web_search", "tavily_search"):
        return "tavily_search"
    if tool_hint == "code_executor":
        return "code_executor"
    if tool_hint == "none":
        return "reason"

    # Any other/unimplemented tool hint falls through to "stub" for now.
    return "stub"


def _route_after_tool(state: State) -> str:
    """
    Route after tool execution:
    - Force termination if step cap exceeded.
    - Route to "replaner" if any step failed (status=FAILED).
    - Route to "synthesize" if any step cancelled (status=CANCELLED).
    - Otherwise, route back to "executor".
    """
    plan = state["plan"]
    if plan is None:
        return "executor"
    
    # Check step cap - force termination if exceeded
    if state.get("steps_executed", 0) >= MAX_TOTAL_STEPS:
        # Mark all remaining PENDING/RUNNING steps as CANCELLED
        for s in plan.subtasks:
            if s.status in (StepStatus.PENDING, StepStatus.RUNNING):
                s.status = StepStatus.CANCELLED
                s.error = f"Step cap ({MAX_TOTAL_STEPS}) exceeded - execution terminated"
        return "synthesize"
    
    # Check for CANCELLED steps - terminate if any exist
    if any(s.status == StepStatus.CANCELLED for s in plan.subtasks):
        return "synthesize"
    
    if any(s.status == StepStatus.FAILED for s in plan.subtasks):
        return "replaner"
        
    return "executor"


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
    graph.add_node("code_executor", code_executor_node)
    graph.add_node("reason", reason_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("replaner", replaner)
    
    # Stub node for tools not yet implemented (e.g. file_editor).
    # NOTE: tool_hint == "none" no longer routes here — see reason_node, which
    # gives those steps a real LLM call instead of a silent no-op.
    # NOTE: tool_hint == "code_executor" now routes to code_executor_node.
    def stub_node(state: State) -> dict:
        """Placeholder for tools not yet implemented."""
        plan = state["plan"]
        if plan is None:
            return {"plan": plan}
        
        running_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
        if running_step:
            running_step.status = StepStatus.DONE
            running_step.result = f"[stub] Tool not implemented for hint: {running_step.tool_hint}"
        
        return {"plan": plan, "steps_executed": 1}
    
    graph.add_node("stub", stub_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "executor")
    
    # Route from executor to appropriate tool node or end
    graph.add_conditional_edges(
        "executor",
        _route_to_tool,
        {
            "tavily_search": "tavily_search",
            "code_executor": "code_executor",
            "reason": "reason",
            "synthesize": "synthesize",
            "stub": "stub",
            "end": END,
        },
    )
    
    # After tool execution, conditionally route to replaner, executor, or synthesize
    graph.add_conditional_edges(
        "tavily_search",
        _route_after_tool,
        {
            "replaner": "replaner",
            "executor": "executor",
            "synthesize": "synthesize",
        },
    )
    graph.add_conditional_edges(
        "code_executor",
        _route_after_tool,
        {
            "replaner": "replaner",
            "executor": "executor",
            "synthesize": "synthesize",
        },
    )
    graph.add_conditional_edges(
        "reason",
        _route_after_tool,
        {
            "replaner": "replaner",
            "executor": "executor",
            "synthesize": "synthesize",
        },
    )
    graph.add_conditional_edges(
        "stub",
        _route_after_tool,
        {
            "replaner": "replaner",
            "executor": "executor",
            "synthesize": "synthesize",
        },
    )
    
    # After replaning, route back to executor to run the new plan
    graph.add_edge("replaner", "executor")
    
    # After synthesis, we're done
    graph.add_edge("synthesize", END)

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)