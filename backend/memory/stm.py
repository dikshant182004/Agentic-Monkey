"""Short-term memory helpers for orchestrator graph state updates."""

from __future__ import annotations


def init_stm(steady_state: dict) -> dict:
    """Initialize STM fields embedded in OrchestratorState at run start."""
    return {
        "steady_state": steady_state,
        "current_turn": 0,
        "turn_scores": [],
        "afp_discoveries": [],
        "estimated_cost_usd": 0.0,
        "consecutive_errors": 0,
        "running_srq": steady_state.get("baseline_srq", 0.0),
        "hitl_pending": False,
        "hitl_interaction_id": None,
        "hitl_required": False,
        "hitl_decision": None,
        "status": "running",
        "final_report": None,
    }


def update_stm_with_turn(state: dict, turn_result: dict) -> dict:
    """Append one turn result and update rolling SRQ and cost counters."""
    updated_scores = state["turn_scores"] + [turn_result]
    new_srq = sum(float(t.get("srq_score", 0.0)) for t in updated_scores) / len(updated_scores)
    return {
        **state,
        "turn_scores": updated_scores,
        "running_srq": new_srq,
        "estimated_cost_usd": float(state.get("estimated_cost_usd", 0.0)) + float(turn_result.get("token_cost", 0.0)),
    }

