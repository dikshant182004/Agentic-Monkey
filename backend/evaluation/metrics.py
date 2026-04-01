"""Metric computations for run-level ACE scoring aggregates."""


def compute_overall_srq(turn_scores: list[dict]) -> float:
    """Compute mean SRQ score across all turn scores."""
    if not turn_scores:
        return 0.0
    return sum(float(t.get("srq_score", 0.0)) for t in turn_scores) / len(turn_scores)


def compute_overall_hrt(turn_scores: list[dict]) -> float:
    """Compute mean HRT score across all turn scores."""
    if not turn_scores:
        return 0.0
    return sum(float(t.get("hrt_score", 0.0)) for t in turn_scores) / len(turn_scores)


def compute_afp_density(turn_scores: list[dict]) -> float:
    """Compute AFP density as AFP turns divided by total turns."""
    if not turn_scores:
        return 0.0
    afp_count = sum(1 for t in turn_scores if t.get("is_afp"))
    return afp_count / len(turn_scores)

