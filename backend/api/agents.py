"""Agent registration and retrieval API routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.a2a.parser import parse_agent_card
from backend.a2a.validator import validate_agent_config
from backend.auth.dependencies import CurrentUser, get_current_user
from backend.db import crud
from backend.db.session import get_db
from backend.schemas.agents import AgentCreateRequest

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("")
async def create_agent(payload: AgentCreateRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Parse, validate, and persist a new target agent configuration."""
    config = parse_agent_card(payload.card_content)
    valid, reason = await validate_agent_config(config)
    if not valid:
        raise HTTPException(status_code=400, detail=reason)
    agent = await crud.create_agent(
        db,
        user_id=user.user_id,
        payload={"name": config.agent_name, "description": config.description, "config": config.to_dict(), "raw_card": json.dumps(config.raw_card)},
    )
    return {"id": str(agent.id), "name": agent.name, "description": agent.description, "config": agent.config, "created_at": agent.created_at.isoformat()}


@router.get("")
async def list_agents(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    """List all agents registered by the authenticated user."""
    agents = await crud.list_agents(db, user.user_id)
    return [{"id": str(item.id), "name": item.name, "description": item.description, "config": item.config, "created_at": item.created_at.isoformat()} for item in agents]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Retrieve one agent and its latest steady-state baseline."""
    agent = await crud.get_agent(db, user.user_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    steady = await crud.latest_steady_state(db, agent_id)
    return {
        "id": str(agent.id),
        "name": agent.name,
        "description": agent.description,
        "config": agent.config,
        "latest_steady_state": None if steady is None else {"baseline_srq": steady.baseline_srq, "baseline_hrt": steady.baseline_hrt},
    }


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Delete an agent and all dependent runs/interactions via cascade."""
    deleted = await crud.delete_agent_with_runs(db, user.user_id, agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "agent_id": agent_id}

