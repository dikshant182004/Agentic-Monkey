"""Schemas for baseline steady-state API operations."""

from pydantic import BaseModel, Field


class SteadyStateRequest(BaseModel):
    """Request payload for running steady-state baseline tasks."""

    sample_size: int = Field(default=20, ge=10, le=100)


class SteadyStateResponse(BaseModel):
    """Response payload for baseline metrics."""

    baseline_srq: float
    baseline_hrt: float
    baseline_latency_p50: float
    baseline_latency_p95: float
    baseline_cost_per_task: float
    sample_size: int

