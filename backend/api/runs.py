"""Chaos run lifecycle API routes including SSE and live state polling.

Fixes applied
─────────────
BUG 8  _mark_run_failed previously hard-coded blast_radius="unknown" and
       monkeys_selected=[] in the update_run_final call, clobbering the
       original values persisted when the Run row was created. This made
       the dashboard show "unknown" blast radius for failed runs.

       The fix: _mark_run_failed now queries the Run row first and passes
       the original field values back to update_run_final, only overwriting
       status and finished_at.

       NOTE: _mark_run_failed lives in orchestrator.py in the fixed version
       (where it has access to the full run row). The version here in runs.py
       delegates to the orchestrator module helper so there is a single
       implementation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import CurrentUser, get_current_user
from backend.chaos.orchestrator import _mark_run_failed, run_chaos_experiment, stream_run_events
from backend.chaos.graphs import build_orchestrator_graph
from backend.db import crud
from backend.db.models import Run
from backend.db.session import get_db, AsyncSessionFactory
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id
from backend.schemas.runs import RunCreateRequest

router = APIRouter(prefix="/runs", tags=["runs"])
logger = logging.getLogger(__name__)


def _make_task_error_callback(run_id: str):
    """Return a done-callback that marks the run as failed if the task raised.

    BUG 8 FIX: Delegates to orchestrator._mark_run_failed which preserves the
    original blast_radius / monkeys_selected values fetched from the DB.
    """
    def _callback(task: asyncio.Task) -> None:
        exc = task.exception() if not task.cancelled() else None
        if exc is not None:
            logger.exception(
                "Orchestrator task for run %s raised an unhandled exception",
                run_id,
                exc_info=exc,
            )
            asyncio.create_task(_mark_run_failed(run_id, str(exc)))
    return _callback


@router.post("")
async def create_run(
    payload: RunCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
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

    run_id = str(run.id)
    initial_state = {
        "run_id": run_id,
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
        "hitl_required": False,
        "status": "running",
        "final_report": None,
        "current_monkey": "",
        "current_prompt": "",
        "current_response": "",
        "current_latency": 0.0,
        "current_safety_score": 10.0,
        "current_is_afp": False,
        "current_severity": "low",
        "current_srq_score": 0.0,
        "current_hrt_score": 0.0,
        "current_reasoning_score": 0.0,
        "current_tool_recovery_score": 0.0,
        "current_self_corrected": False,
        "current_notes": "",
        "current_afp_description": "",
        "current_openpipe_request_id": "",
        "current_interaction_id": str(uuid4()),
        "current_token_cost_usd": 0.0,
    }

    task = asyncio.create_task(run_chaos_experiment(initial_state))
    task.add_done_callback(_make_task_error_callback(run_id))

    return {"run_id": run_id, "status": "running"}


@router.get("")
async def list_runs(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all runs for current user."""
    runs = await crud.list_runs(db, user.user_id)
    return [
        {
            "id": str(item.id),
            "status": item.status,
            "blast_radius": item.blast_radius,
            "overall_srq": item.overall_srq,
        }
        for item in runs
    ]


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
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
async def get_live_state(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    checkpointer=Depends(get_redis_checkpointer),
) -> dict:
    """Return current OrchestratorState snapshot from checkpointer backend."""
    graph = build_orchestrator_graph(checkpointer)
    config = run_thread_id(run_id)
    snapshot = await graph.aget_state(config)
    if snapshot is None or not snapshot.values:
        raise HTTPException(status_code=404, detail="No live state found - run may be complete")
    return dict(snapshot.values)


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream run events over Server-Sent Events with heartbeat support."""
    return StreamingResponse(stream_run_events(run_id), media_type="text/event-stream")