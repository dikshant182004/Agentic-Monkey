"""LangGraph failure injector flow for deterministic tool response mutation."""

from langgraph.graph import END, StateGraph

from backend.chaos.graphs.states import FailureInjectorState
from backend.injectors.tool_vortex_monkey import FAILURE_MODES


def apply_failure_mode(state: FailureInjectorState) -> FailureInjectorState:
    """Apply configured tool failure mutation or pass through unchanged."""
    mutator = FAILURE_MODES.get(state["failure_mode"], lambda r: r)
    return {**state, "mutated_response": mutator(state["tool_response"])}


def build_failure_injector_graph():
    """Build and compile failure injector graph once at import time."""
    graph = StateGraph(FailureInjectorState)
    graph.add_node("apply_failure_mode", apply_failure_mode)
    graph.set_entry_point("apply_failure_mode")
    graph.add_edge("apply_failure_mode", END)
    return graph.compile()


failure_injector_graph = build_failure_injector_graph()

