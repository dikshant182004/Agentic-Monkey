"""Async CRUD operations for ChaosAgent's PostgreSQL persistence layer.

All functions accept an AsyncSession and are designed to be called from:
  - FastAPI route handlers (via get_db() dependency)
  - Orchestrator graph nodes (via AsyncSessionFactory() context manager)

Fixes applied
─────────────
BUG 1/14  get_run() requires a user_id scope (correct for API routes). Added
          get_run_unscoped() for internal callers (orchestrator stream poller)
          that need to look up a Run by id only, without a user filter.
          The original code passed user_id=None which produced SQL
          WHERE user_id = NULL — a condition that never matches.

Important:
  - Never raise on "not found" — return None instead (callers handle 404)
  - commit() is the caller's responsibility for session-scoped operations
  - Functions that write their own session use AsyncSessionFactory directly
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AFP, Agent, Interaction, Run, SteadyState, User


# ── User ───────────────────────────────────────────────────────────────────────

async def get_or_create_user(session: AsyncSession, email: str, name: str) -> User:
    """Fetch a user by email or create one if absent (upsert pattern)."""
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return existing
    user = User(id=uuid4(), email=email, name=name, created_at=datetime.now(timezone.utc))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ── Agent ──────────────────────────────────────────────────────────────────────

async def create_agent(session: AsyncSession, user_id: str, payload: dict) -> Agent:
    """Create and persist a new Agent row."""
    agent = Agent(
        id=uuid4(),
        user_id=user_id,
        name=payload["name"],
        description=payload.get("description", ""),
        config=payload["config"],
        raw_card=payload["raw_card"],
        created_at=datetime.now(timezone.utc),
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def list_agents(session: AsyncSession, user_id: str) -> list[Agent]:
    """Return all agents owned by a user in reverse-chronological order."""
    rows = await session.scalars(
        select(Agent).where(Agent.user_id == user_id).order_by(desc(Agent.created_at))
    )
    return list(rows)


async def get_agent(session: AsyncSession, user_id: str, agent_id: str) -> Agent | None:
    """Fetch one agent by id scoped to the given user (returns None if not found)."""
    return await session.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user_id)
    )


async def delete_agent_with_runs(
    session: AsyncSession, user_id: str, agent_id: str
) -> bool:
    """Delete an agent and all dependent records via DB cascade. Returns True if deleted."""
    result = await session.execute(
        delete(Agent).where(Agent.id == agent_id, Agent.user_id == user_id)
    )
    await session.commit()
    return result.rowcount > 0


# ── SteadyState ────────────────────────────────────────────────────────────────

async def latest_steady_state(session: AsyncSession, agent_id: str) -> SteadyState | None:
    """Fetch the most recent SteadyState baseline for an agent."""
    return await session.scalar(
        select(SteadyState)
        .where(SteadyState.agent_id == agent_id)
        .order_by(desc(SteadyState.captured_at))
    )


# ── Run ────────────────────────────────────────────────────────────────────────

async def list_runs(session: AsyncSession, user_id: str) -> list[Run]:
    """List all runs for the current user in reverse-chronological order."""
    rows = await session.scalars(
        select(Run).where(Run.user_id == user_id).order_by(desc(Run.started_at))
    )
    return list(rows)


async def get_run(session: AsyncSession, run_id: str, user_id: str) -> Run | None:
    """Fetch one run by id scoped to user. For API routes — always requires user_id."""
    return await session.scalar(
        select(Run).where(Run.id == run_id, Run.user_id == user_id)
    )


async def get_run_unscoped(session: AsyncSession, run_id: str) -> Run | None:
    """Fetch one run by id WITHOUT a user scope check.

    BUG 1/14 FIX: Internal callers (e.g. the SSE stream poller in
    orchestrator.py) do not have a user_id available. The original code
    passed user_id=None to get_run() which produced SQL WHERE user_id = NULL
    — a condition that never matches. This function is the correct internal
    alternative.
    """
    return await session.scalar(select(Run).where(Run.id == run_id))


async def update_run_final(
    session: AsyncSession,
    run_id: str,
    status: str,
    blast_radius: str,
    monkeys_selected: object,
    overall_srq: float,
    overall_hrt: float,
    overall_safety: float,
    afp_count: int,
    ethical_drift_score: float,
    agentic_resilience_score: float,
    estimated_cost_usd: float,
    finished_at: datetime,
) -> None:
    """Update terminal run record metrics in PostgreSQL."""
    run = await session.scalar(select(Run).where(Run.id == run_id))
    if run is None:
        return
    run.status = status
    run.blast_radius = blast_radius
    run.monkeys_selected = monkeys_selected
    run.overall_srq = overall_srq
    run.overall_hrt = overall_hrt
    run.overall_safety = overall_safety
    run.afp_count = afp_count
    run.ethical_drift_score = ethical_drift_score
    run.agentic_resilience_score = agentic_resilience_score
    run.estimated_cost_usd = estimated_cost_usd
    run.finished_at = finished_at
    await session.commit()


# ── Interaction ────────────────────────────────────────────────────────────────

async def create_interaction(
    session: AsyncSession,
    interaction_id: str,
    run_id: str,
    turn: int,
    monkey_type: str,
    prompt: str,
    agent_response: str,
    failure_injected: str,
    srq_score: float,
    hrt_score: float,
    safety_score: float,
    reasoning_score: float,
    tool_recovery_score: float,
    is_afp: bool,
    self_corrected: bool,
    hitl_required: bool,
    hitl_decision: str | None,
    openpipe_request_id: str,
    notes: str,
) -> None:
    """Insert one per-turn Interaction record."""
    session.add(
        Interaction(
            id=UUID(interaction_id),
            run_id=UUID(run_id),
            turn=turn,
            monkey_type=monkey_type,
            prompt=prompt,
            agent_response=agent_response,
            failure_injected=failure_injected,
            srq_score=srq_score,
            hrt_score=hrt_score,
            safety_score=safety_score,
            reasoning_score=reasoning_score,
            tool_recovery_score=tool_recovery_score,
            is_afp=is_afp,
            self_corrected=self_corrected,
            hitl_required=hitl_required,
            hitl_decision=hitl_decision,
            openpipe_request_id=openpipe_request_id,
            notes=notes,
            created_at=datetime.now(timezone.utc),
        )
    )
    # NOTE: caller is responsible for commit() to allow batching


# ── AFP ────────────────────────────────────────────────────────────────────────

async def create_afp(
    session: AsyncSession,
    afp_id: str,
    run_id: str,
    interaction_id: str,
    agent_id: str,
    monkey_type: str,
    prompt: str,
    agent_response: str,
    description: str,
    severity: str,
    recommendation: str,
) -> None:
    """Insert an AFP discovery record (LTM write)."""
    session.add(
        AFP(
            id=UUID(afp_id),
            run_id=UUID(run_id),
            interaction_id=UUID(interaction_id),
            agent_id=UUID(agent_id),
            monkey_type=monkey_type,
            prompt=prompt,
            agent_response=agent_response,
            description=description,
            severity=severity,
            recommendation=recommendation,
            created_at=datetime.now(timezone.utc),
        )
    )
    # NOTE: caller is responsible for commit()


async def load_afp_patterns(
    session: AsyncSession, agent_id: str, monkey_type: str, limit: int = 10
) -> list[str]:
    """Load recent AFP descriptions for one agent and monkey type (DB-layer version)."""
    rows = await session.scalars(
        select(AFP.description)
        .where(AFP.agent_id == agent_id, AFP.monkey_type == monkey_type)
        .order_by(desc(AFP.created_at))
        .limit(limit)
    )
    return list(rows)


async def count_afps_for_run(session: AsyncSession, run_id: str) -> int:
    """Count AFP records for a run (used for report summary when STM is unavailable)."""
    result = await session.scalar(
        select(func.count()).select_from(AFP).where(AFP.run_id == run_id)
    )
    return result or 0