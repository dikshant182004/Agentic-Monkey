"""Long-term memory helpers backed by PostgreSQL tables."""

from __future__ import annotations

from sqlalchemy import desc, select

from backend.db.models import AFP, SteadyState
from backend.db.session import AsyncSessionFactory

_DEFAULT_STEADY_STATE = {
    "baseline_srq": 5.0,
    "baseline_hrt": 5.0,
    "baseline_latency_p50": 1.0,
    "baseline_latency_p95": 2.0,
    "baseline_cost_per_task": 0.001,
}


async def load_steady_state(agent_id: str) -> dict:
    """Load latest steady-state baseline for an agent from PostgreSQL.

    Returns a safe default dict instead of raising when no baseline exists.
    A missing baseline is not fatal — chaos can still run with default thresholds.
    """
    async with AsyncSessionFactory() as session:
        row = await session.scalar(
            select(SteadyState)
            .where(SteadyState.agent_id == agent_id)
            .order_by(desc(SteadyState.captured_at))
        )
    if row is None:
        import logging
        logging.getLogger(__name__).warning(
            "No steady-state baseline found for agent %s — using defaults. "
            "Run steady-state baseline first for accurate thresholds.",
            agent_id,
        )
        return dict(_DEFAULT_STEADY_STATE)
    return {
        "baseline_srq": row.baseline_srq,
        "baseline_hrt": row.baseline_hrt,
        "baseline_latency_p50": row.baseline_latency_p50,
        "baseline_latency_p95": row.baseline_latency_p95,
        "baseline_cost_per_task": row.baseline_cost_per_task,
    }


async def write_afp_to_ltm(afp: dict, agent_id: str) -> None:
    """Persist an AFP discovery for future evaluator context loading."""
    async with AsyncSessionFactory() as session:
        session.add(
            AFP(
                run_id=afp["run_id"],
                interaction_id=afp["interaction_id"],
                agent_id=agent_id,
                monkey_type=afp["monkey_type"],
                prompt=afp["prompt"],
                agent_response=afp["agent_response"],
                description=afp["description"],
                severity=afp["severity"],
                recommendation=afp.get("recommendation", ""),
            )
        )
        await session.commit()


async def load_afp_patterns(agent_id: str, monkey_type: str, limit: int = 10) -> list[str]:
    """Read recent AFP descriptions for one agent and monkey category."""
    async with AsyncSessionFactory() as session:
        rows = await session.scalars(
            select(AFP.description)
            .where(AFP.agent_id == agent_id, AFP.monkey_type == monkey_type)
            .order_by(desc(AFP.created_at))
            .limit(limit)
        )
        return list(rows)