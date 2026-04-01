"""Async CRUD operations for ChaosAgent persistence layer."""

from __future__ import annotations

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AFP, Agent, Run, SteadyState, User


async def get_or_create_user(session: AsyncSession, email: str, name: str) -> User:
    """Fetch a user by email or create one when absent."""
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return existing
    user = User(email=email, name=name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_agent(session: AsyncSession, user_id: str, payload: dict) -> Agent:
    """Create and persist a new Agent row."""
    agent = Agent(
        user_id=user_id,
        name=payload["name"],
        description=payload.get("description", ""),
        config=payload["config"],
        raw_card=payload["raw_card"],
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def list_agents(session: AsyncSession, user_id: str) -> list[Agent]:
    """Return all agents owned by a user."""
    rows = await session.scalars(select(Agent).where(Agent.user_id == user_id).order_by(desc(Agent.created_at)))
    return list(rows)


async def get_agent(session: AsyncSession, user_id: str, agent_id: str) -> Agent | None:
    """Fetch one agent by id scoped to user."""
    return await session.scalar(select(Agent).where(Agent.id == agent_id, Agent.user_id == user_id))


async def delete_agent_with_runs(session: AsyncSession, user_id: str, agent_id: str) -> bool:
    """Delete an agent and dependent records via cascade relationships."""
    result = await session.execute(delete(Agent).where(Agent.id == agent_id, Agent.user_id == user_id))
    await session.commit()
    return result.rowcount > 0


async def latest_steady_state(session: AsyncSession, agent_id: str) -> SteadyState | None:
    """Fetch latest steady state baseline for an agent."""
    return await session.scalar(
        select(SteadyState).where(SteadyState.agent_id == agent_id).order_by(desc(SteadyState.captured_at))
    )


async def list_runs(session: AsyncSession, user_id: str) -> list[Run]:
    """List runs by user in reverse chronological order."""
    rows = await session.scalars(select(Run).where(Run.user_id == user_id).order_by(desc(Run.started_at)))
    return list(rows)


async def get_run(session: AsyncSession, run_id: str, user_id: str) -> Run | None:
    """Fetch one run by id scoped to user."""
    return await session.scalar(select(Run).where(Run.id == run_id, Run.user_id == user_id))


async def load_afp_patterns(session: AsyncSession, agent_id: str, monkey_type: str, limit: int = 10) -> list[str]:
    """Load recent AFP descriptions for one agent and monkey type."""
    rows = await session.scalars(
        select(AFP.description)
        .where(AFP.agent_id == agent_id, AFP.monkey_type == monkey_type)
        .order_by(desc(AFP.created_at))
        .limit(limit)
    )
    return list(rows)

