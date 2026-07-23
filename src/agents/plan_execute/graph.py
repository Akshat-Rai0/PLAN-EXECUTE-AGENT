from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    plan_node, executor_node, tavily_search_node, synthesize_node,
    replaner, reason_node, code_executor_node, synthesize_tool_node,
    setup_workspace_node, shell_node, write_file_node, delete_file_node, start_server_node,
    approval_node, ask_human_node, use_browser_node,
    MAX_TOTAL_STEPS,
)
from .state import State, StepStatus
from src.tools.risk_classifier import classify_tool_risk, RiskLevel


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
        "synthesize_tool" for any other/unrecognized tool hint (e.g. a
            capability the planner named that has no fixed tool) — routes
            to dynamic tool synthesis (see src/synthesis/). NOTE the naming
            collision with "synthesize" below: that one means FINAL-ANSWER
            synthesis (combining step results into a response), this one
            means TOOL synthesis (generating new callable code). Same word,
            two unrelated concepts — kept distinct in routing strings
            specifically to avoid conflating them, even though the English
            word is shared.
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
    risk_level = classify_tool_risk(tool_hint)
    
    # HIGH-risk tools route through approval_node first
    if risk_level == RiskLevel.HIGH:
        return "approval"
    
    # LOW-risk tools route directly to their tool nodes
    if tool_hint in ("web_search", "tavily_search"):
        return "tavily_search"
    if tool_hint == "code_executor":
        return "code_executor"
    if tool_hint == "none":
        return "reason"
    if tool_hint == "setup_workspace":
        return "setup_workspace"
    if tool_hint == "shell_command":
        return "shell"
    if tool_hint in ("write_file", "file_editor"):
        return "write_file"
    if tool_hint == "delete_file":
        return "delete_file"
    if tool_hint == "start_server":
        return "start_server"
    if tool_hint == "use_browser":
        return "use_browser"

    # Any other/unrecognized tool hint means no fixed tool matches — route
    # to synthesis rather than the dead-end stub (which used to mark these
    # steps DONE with a placeholder, silently pretending success).
    return "synthesize_tool"


def _route_after_approval(state: State) -> str:
    """
    Route after approval_node: send to the appropriate tool node based on tool_hint.
    This is called after human approval is granted to execute the actual tool.
    """
    plan = state["plan"]
    if plan is None:
        return "executor"
    
    running_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if not running_step:
        return "executor"
    
    tool_hint = running_step.tool_hint.lower()
    
    # Route to the actual tool node
    if tool_hint in ("web_search", "tavily_search"):
        return "tavily_search"
    if tool_hint == "code_executor":
        return "code_executor"
    if tool_hint == "shell_command":
        return "shell"
    if tool_hint in ("write_file", "file_editor"):
        return "write_file"
    if tool_hint == "delete_file":
        return "delete_file"
    if tool_hint == "start_server":
        return "start_server"
    if tool_hint == "use_browser":
        return "use_browser"

    # Any other/unrecognized tool_hint means synthesis was the route taken
    # to get here (see _route_to_tool) — send it on to synthesize_tool now
    # that approval is granted, rather than falling back to "executor"
    # (which would loop back to step-selection instead of actually running
    # the synthesis pipeline the human just approved).
    return "synthesize_tool"


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
    graph.add_node("synthesize_tool", synthesize_tool_node)
    graph.add_node("reason", reason_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("replaner", replaner)
    graph.add_node("setup_workspace", setup_workspace_node)
    graph.add_node("shell", shell_node)
    graph.add_node("write_file", write_file_node)
    graph.add_node("delete_file", delete_file_node)
    graph.add_node("start_server", start_server_node)
    graph.add_node("use_browser", use_browser_node)
    graph.add_node("approval", approval_node)
    graph.add_node("ask_human", ask_human_node)
    
    # Stub node kept registered for backward-compat (in case anything still
    # references "stub" directly) but is no longer reachable via normal
    # _route_to_tool/_route_after_approval routing — unrecognized tool_hints
    # now route to synthesize_tool instead (see src/synthesis/).
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
            "synthesize_tool": "synthesize_tool",
            "reason": "reason",
            "synthesize": "synthesize",
            "stub": "stub",
            "setup_workspace": "setup_workspace",
            "shell": "shell",
            "write_file": "write_file",
            "delete_file": "delete_file",
            "start_server": "start_server",
            "use_browser": "use_browser",
            "approval": "approval",
            "end": END,
        },
    )
    
    # After approval, route to the actual tool node
    graph.add_conditional_edges(
        "approval",
        _route_after_approval,
        {
            "tavily_search": "tavily_search",
            "code_executor": "code_executor",
            "synthesize_tool": "synthesize_tool",
            "shell": "shell",
            "write_file": "write_file",
            "delete_file": "delete_file",
            "start_server": "start_server",
            "use_browser": "use_browser",
            "executor": "executor",
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
        "synthesize_tool",
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

    # Coding-agent nodes — all share the same post-execution routing
    _coding_routing = {"replaner": "replaner", "executor": "executor", "synthesize": "synthesize"}
    graph.add_conditional_edges("setup_workspace", _route_after_tool, _coding_routing)
    graph.add_conditional_edges("shell", _route_after_tool, _coding_routing)
    graph.add_conditional_edges("write_file", _route_after_tool, _coding_routing)
    graph.add_conditional_edges("delete_file", _route_after_tool, _coding_routing)
    graph.add_conditional_edges("start_server", _route_after_tool, _coding_routing)
    graph.add_conditional_edges("use_browser", _route_after_tool, _coding_routing)
    
    # After replaning, route back to executor to run the new plan
    graph.add_edge("replaner", "executor")
    
    # After synthesis, we're done
    graph.add_edge("synthesize", END)

    # Return uncompiled graph - will be compiled in main.py with checkpointer
    return graph