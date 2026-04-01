"""Evaluator integration helpers for scoring interactions and persistence mapping."""

from backend.chaos.graph_runner import run_evaluator


async def judge_interaction(inputs: dict, run_id: str) -> dict:
    """Invoke evaluator graph and return normalized scoring fields."""
    result = await run_evaluator(inputs, run_id=run_id)
    return {
        "srq_score": result["srq_score"],
        "hrt_score": result["hrt_score"],
        "safety_score": result["safety_score"],
        "reasoning_score": result["reasoning_score"],
        "tool_recovery_score": result["tool_recovery_score"],
        "is_afp": result["is_afp"],
        "afp_description": result["afp_description"],
        "severity": result["severity"],
        "self_corrected": result["self_corrected"],
        "notes": result["notes"],
        "openpipe_request_id": result["openpipe_request_id"],
    }

