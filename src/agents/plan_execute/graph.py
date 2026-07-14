from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import plan_node
from .state import State


def build_graph():
    """
    Compile a basic graph with:
    - one node that breaks down tasks into plans
    - InMemorySaver checkpointer
    """

    graph = StateGraph(State)

    # Add single plan node
    graph.add_node("plan", plan_node)

    # Add edges
    graph.add_edge(START, "plan")
    graph.add_edge("plan", END)

    # Compile with InMemorySaver checkpointer
    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)