"""Unified async runner wrappers for ChaosAgent LangGraph flows."""

from langsmith import traceable

from backend.chaos.graphs.evaluator import evaluator_graph
from backend.chaos.graphs.failure_injector import failure_injector_graph
from backend.chaos.graphs.scenario_generator import scenario_generator_graph


@traceable(name="run_scenario_generator", tags=["graph", "scenario_gen"])
async def run_scenario_generator(inputs: dict, run_id: str) -> dict:
    """Invoke scenario generator graph and return final state."""
    return await scenario_generator_graph.ainvoke(inputs)


@traceable(name="run_failure_injector", tags=["graph", "failure_injector"])
async def run_failure_injector(inputs: dict, run_id: str) -> dict:
    """Invoke failure injector graph and return final state."""
    return await failure_injector_graph.ainvoke(inputs)


@traceable(name="run_evaluator", tags=["graph", "evaluator"])
async def run_evaluator(inputs: dict, run_id: str) -> dict:
    """Invoke evaluator graph and return final state."""
    return await evaluator_graph.ainvoke(inputs)

