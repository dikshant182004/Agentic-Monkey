"""Steady-state baseline API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import CurrentUser, get_current_user
from backend.chaos.steady_state import run_steady_state
from backend.db.crud import get_agent, latest_steady_state
from backend.db.models import SteadyState
from backend.db.session import get_db
from backend.schemas.steady_state import SteadyStateRequest

router = APIRouter(prefix="/steady-state", tags=["steady-state"])


@router.post("/run/{agent_id}")
async def run_baseline(
    agent_id: str,
    payload: SteadyStateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run baseline probes for an agent and persist resulting metrics."""
    agent = await get_agent(db, user.user_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    metrics = await run_steady_state(agent.config, payload.sample_size)
    steady = SteadyState(agent_id=agent.id, **metrics)
    db.add(steady)
    await db.commit()
    await db.refresh(steady)
    return {
        "baseline_srq": steady.baseline_srq,
        "baseline_hrt": steady.baseline_hrt,
        "baseline_latency_p50": steady.baseline_latency_p50,
        "baseline_latency_p95": steady.baseline_latency_p95,
        "baseline_cost_per_task": steady.baseline_cost_per_task,
        "sample_size": steady.sample_size,
    }


@router.get("/{agent_id}")
async def get_baseline(agent_id: str, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Get latest steady-state baseline for one agent."""
    agent = await get_agent(db, user.user_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    steady = await latest_steady_state(db, agent_id)
    if steady is None:
        raise HTTPException(status_code=404, detail="No steady-state baseline found")
    return {
        "baseline_srq": steady.baseline_srq,
        "baseline_hrt": steady.baseline_hrt,
        "baseline_latency_p50": steady.baseline_latency_p50,
        "baseline_latency_p95": steady.baseline_latency_p95,
        "baseline_cost_per_task": steady.baseline_cost_per_task,
        "sample_size": steady.sample_size,
    }

