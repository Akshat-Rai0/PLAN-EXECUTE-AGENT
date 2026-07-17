from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import react_step
from .state import ReactState, MAX_REACT_ITERATIONS

def _should_continue(state: ReactState) -> str:
    if state.get("final_answer") is not None:
        return "end"
    if state.get("iterations", 0) >= MAX_REACT_ITERATIONS:
        return "end"  # force-terminate, similar to your MAX_TOTAL_STEPS guard
    return "continue"

def build_react_graph():
    graph = StateGraph(ReactState)
    graph.add_node("react_step", react_step)
    graph.add_edge(START, "react_step")
    graph.add_conditional_edges("react_step", _should_continue, {
        "continue": "react_step",  # loop back to itself
        "end": END,
    })
    return graph.compile(checkpointer=InMemorySaver())