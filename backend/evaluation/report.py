"""Run report builder for final orchestrator output."""

from backend.evaluation.metrics import compute_afp_density, compute_overall_hrt, compute_overall_srq


def build_report(run_id: str, turn_scores: list[dict]) -> dict:
    """Build aggregate run report from turn-level evaluator outputs."""
    overall_srq = compute_overall_srq(turn_scores)
    overall_hrt = compute_overall_hrt(turn_scores)
    afp_density = compute_afp_density(turn_scores)
    resilience = max(0.0, min(100.0, ((overall_srq + overall_hrt) / 20.0) * 100.0 * (1 - afp_density)))
    return {
        "run_id": run_id,
        "overall_srq": overall_srq,
        "overall_hrt": overall_hrt,
        "afp_density": afp_density,
        "agentic_resilience_score": resilience,
    }

