"""Chaos run lifecycle API routes including SSE and live state polling."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import CurrentUser, get_current_user
from backend.chaos.orchestrator import run_chaos_experiment, stream_run_events
from backend.db import crud
from backend.db.models import Run
from backend.db.session import get_db
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id
from backend.schemas.runs import RunCreateRequest

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("")
async def create_run(payload: RunCreateRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Create run record and start orchestrator graph asynchronously."""
    agent = await crud.get_agent(db, user.user_id, payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    run = Run(
        id=uuid4(),
        agent_id=agent.id,
        user_id=user.user_id,
        status="running",
        blast_radius=payload.blast_radius,
        monkeys_selected=payload.monkeys_selected,
        config={"intensity": payload.intensity, "hypothesis": payload.hypothesis},
        overall_srq=0.0,
        overall_hrt=0.0,
        overall_safety=0.0,
        afp_count=0,
        ethical_drift_score=0.0,
        agentic_resilience_score=0.0,
        estimated_cost_usd=0.0,
    )
    db.add(run)
    await db.commit()
    initial_state = {
        "run_id": str(run.id),
        "agent_id": str(agent.id),
        "user_id": user.user_id,
        "agent_config": agent.config,
        "steady_state": {},
        "blast_radius": payload.blast_radius,
        "monkeys_selected": payload.monkeys_selected or ["cti"],
        "intensity": payload.intensity,
        "current_turn": 0,
        "total_turns_planned": max(len(payload.monkeys_selected or ["cti"]) * 3, 3),
        "turn_scores": [],
        "afp_discoveries": [],
        "estimated_cost_usd": 0.0,
        "consecutive_errors": 0,
        "running_srq": 0.0,
        "hitl_pending": False,
        "hitl_interaction_id": None,
        "hitl_decision": None,
        "status": "running",
        "final_report": None,
        "current_monkey": "",
        "current_prompt": "",
        "current_response": "",
        "current_latency": 0.0,
        "current_safety_score": 10.0,
        "current_is_afp": False,
        "current_severity": "low",
    }
    asyncio.create_task(run_chaos_experiment(initial_state))
    return {"run_id": str(run.id), "status": "running"}


@router.get("")
async def list_runs(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    """List all runs for current user."""
    runs = await crud.list_runs(db, user.user_id)
    return [{"id": str(item.id), "status": item.status, "blast_radius": item.blast_radius, "overall_srq": item.overall_srq} for item in runs]


@router.get("/{run_id}")
async def get_run(run_id: str, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Get one run aggregate record from PostgreSQL."""
    run = await crud.get_run(db, run_id, user.user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": str(run.id),
        "status": run.status,
        "blast_radius": run.blast_radius,
        "overall_srq": run.overall_srq,
        "overall_hrt": run.overall_hrt,
        "overall_safety": run.overall_safety,
        "afp_count": run.afp_count,
    }


@router.get("/{run_id}/live-state")
async def get_live_state(run_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return current OrchestratorState snapshot from checkpointer backend."""
    checkpointer = await get_redis_checkpointer()
    snapshot = await checkpointer.aget(run_thread_id(run_id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No live state found - run may be complete")
    return snapshot.values


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, user: CurrentUser = Depends(get_current_user)) -> StreamingResponse:
    """Stream run events over Server-Sent Events with heartbeat support."""
    return StreamingResponse(stream_run_events(run_id), media_type="text/event-stream")

