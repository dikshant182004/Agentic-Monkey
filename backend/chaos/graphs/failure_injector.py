"""LangGraph failure injector flow for deterministic tool response mutation.

LangGraph 1.x: uses add_edge(START, ...) instead of set_entry_point().
"""

from langgraph.graph import END, START, StateGraph

from backend.chaos.graphs.states import FailureInjectorState
from backend.injectors.tool_vortex_monkey import FAILURE_MODES


def apply_failure_mode(state: FailureInjectorState) -> FailureInjectorState:
    """Apply configured tool failure mutation or pass through unchanged."""
    mutator = FAILURE_MODES.get(state["failure_mode"], lambda r: r)
    return {**state, "mutated_response": mutator(state["tool_response"])}


def build_failure_injector_graph():
    """Build and compile failure injector graph.

    Uses add_edge(START, ...) — idiomatic LangGraph 1.x style.
    """
    graph = StateGraph(FailureInjectorState)
    graph.add_node("apply_failure_mode", apply_failure_mode)
    graph.add_edge(START, "apply_failure_mode")
    graph.add_edge("apply_failure_mode", END)
    return graph.compile()


failure_injector_graph = build_failure_injector_graph()