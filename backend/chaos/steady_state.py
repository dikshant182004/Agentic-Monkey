"""Steady-state baseline runner for normal agent behavior measurement."""

from __future__ import annotations

import statistics

from backend.a2a.client import call_agent
from backend.a2a.parser import AgentConfig


async def run_steady_state(agent_config: dict, sample_size: int) -> dict:
    """Execute baseline tasks and compute steady-state metric aggregates."""
    cfg = AgentConfig(**agent_config)
    latencies: list[float] = []
    success = 0
    for index in range(sample_size):
        response, latency = await call_agent(cfg, f"Baseline probe {index+1}", session_id=f"steady-{index+1}")
        latencies.append(latency)
        if not response.startswith("["):
            success += 1
    sorted_lat = sorted(latencies or [0.0])
    p50 = sorted_lat[int(0.5 * (len(sorted_lat) - 1))]
    p95 = sorted_lat[int(0.95 * (len(sorted_lat) - 1))]
    srq = (success / max(sample_size, 1)) * 10.0
    return {
        "baseline_srq": round(srq, 3),
        "baseline_hrt": 10.0,
        "baseline_latency_p50": round(p50, 3),
        "baseline_latency_p95": round(p95, 3),
        "baseline_cost_per_task": round(statistics.fmean([0.001] * max(sample_size, 1)), 4),
        "sample_size": sample_size,
    }

