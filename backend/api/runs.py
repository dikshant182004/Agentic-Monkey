"""
ChaosAgent Runs API — updated for v2.

Changes:
  - POST /runs now accepts optional auto_plan=true flag.
    When set, experiment config (monkeys, intensity, blast_radius, hypothesis)
    is derived from the A2A card via experiment_planner.plan_experiment().
    User-supplied values override auto-plan if provided.
  - initial_state now includes all new OrchestratorState v2 fields:
    refinement_budget, refinement_used, auto_planned, current_attack_angle,
    current_seed_id, current_atlas_id, current_owasp_category,
    current_failure_hypothesis.
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
from backend.chaos.experiment_planner import plan_experiment, ExperimentPlan
from backend.chaos.graphs.scenario_generator import REFINEMENT_BUDGET
from backend.chaos.orchestrator import _mark_run_failed, run_chaos_experiment, stream_run_events
from backend.chaos.graphs import build_orchestrator_graph
from backend.db import crud
from backend.db.models import Run
from backend.db.session import get_db, AsyncSessionFactory
from backend.a2a.parser import AgentConfig
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id
from backend.schemas.runs import RunCreateRequest

router = APIRouter(prefix="/runs", tags=["runs"])
logger = logging.getLogger(__name__)


def _make_task_error_callback(run_id: str):
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
    """
    Create run record and start orchestrator graph asynchronously.

    If payload.auto_plan=True AND monkeys_selected is empty:
      - Reads agent A2A card
      - Calls experiment_planner.plan_experiment() to derive config
      - User-supplied intensity/blast_radius/hypothesis override plan if set
    """
    agent = await crud.get_agent(db, user.user_id, payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # ── Auto-planning ─────────────────────────────────────────────────────────
    plan: ExperimentPlan | None = None
    auto_planned = False

    if payload.auto_plan and not payload.monkeys_selected:
        try:
            agent_cfg = AgentConfig(**agent.config)
            plan = await plan_experiment(agent_cfg)
            auto_planned = True
            logger.info(
                "Auto-plan for agent %s: monkeys=%s intensity=%d blast=%s",
                agent.id, plan.monkeys_selected, plan.intensity, plan.blast_radius,
            )
        except Exception as exc:
            logger.warning("Auto-plan failed (%s) — falling back to defaults", exc)
            plan = None

    # Resolve final config (user overrides auto-plan)
    if plan:
        monkeys = payload.monkeys_selected or plan.monkeys_selected
        intensity = payload.intensity if payload.intensity != 3 else plan.intensity  # 3 is default
        blast = payload.blast_radius if payload.blast_radius != "staging" else plan.blast_radius
        hypothesis = payload.hypothesis.strip() or plan.hypothesis
    else:
        monkeys = payload.monkeys_selected or ["cti"]
        intensity = payload.intensity
        blast = payload.blast_radius
        hypothesis = payload.hypothesis.strip() or f"Agent may degrade under {', '.join(monkeys)} attacks."

    # ── Create DB record ──────────────────────────────────────────────────────
    run = Run(
        id=uuid4(),
        agent_id=agent.id,
        user_id=user.user_id,
        status="running",
        blast_radius=blast,
        monkeys_selected=monkeys,
        config={"intensity": intensity, "hypothesis": hypothesis, "auto_planned": auto_planned},
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
    refinement_budget = REFINEMENT_BUDGET.get(blast, 3)

    # ── Build initial orchestrator state ──────────────────────────────────────
    initial_state = {
        "run_id": run_id,
        "agent_id": str(agent.id),
        "user_id": user.user_id,
        "agent_config": agent.config,
        "steady_state": {},
        "blast_radius": blast,
        "monkeys_selected": monkeys,
        "intensity": intensity,
        "auto_planned": auto_planned,
        # Run-time accumulation
        "current_turn": 0,
        "total_turns_planned": max(len(monkeys) * 3, 3),
        "turn_scores": [],
        "afp_discoveries": [],
        "estimated_cost_usd": 0.0,
        "consecutive_errors": 0,
        "running_srq": 0.0,
        # Refinement budget
        "refinement_budget": refinement_budget,
        "refinement_used": 0,
        # HITL
        "hitl_pending": False,
        "hitl_interaction_id": None,
        "hitl_decision": None,
        "hitl_required": False,
        # Status
        "status": "running",
        "final_report": None,
        # Per-turn staging
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
        # v2 seed metadata
        "current_attack_angle": "",
        "current_seed_id": "",
        "current_atlas_id": "",
        "current_owasp_category": "",
        "current_failure_hypothesis": "",
    }

    task = asyncio.create_task(run_chaos_experiment(initial_state))
    task.add_done_callback(_make_task_error_callback(run_id))

    response = {
        "run_id": run_id,
        "status": "running",
        "monkeys_selected": monkeys,
        "intensity": intensity,
        "blast_radius": blast,
        "auto_planned": auto_planned,
        "refinement_budget": refinement_budget,
    }
    if plan:
        response["plan_notes"] = plan.plan_notes
        response["monkey_rankings"] = [
            {
                "monkey_type": r.monkey_type,
                "priority_score": r.priority_score,
                "reason": r.reason,
            }
            for r in plan.monkey_rankings
        ]

    return response


@router.get("/plan")
async def get_experiment_plan(
    agent_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Preview the auto-generated experiment plan for an agent WITHOUT launching a run.
    Useful for the UI to show the user what would be planned before they confirm.
    """
    agent = await crud.get_agent(db, user.user_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_cfg = AgentConfig(**agent.config)
    plan = await plan_experiment(agent_cfg)

    return {
        "monkeys_selected": plan.monkeys_selected,
        "intensity": plan.intensity,
        "blast_radius": plan.blast_radius,
        "hypothesis": plan.hypothesis,
        "total_turns": plan.total_turns,
        "plan_notes": plan.plan_notes,
        "monkey_rankings": [
            {
                "monkey_type": r.monkey_type,
                "priority_score": r.priority_score,
                "reason": r.reason,
                "attack_surfaces": r.attack_surfaces,
            }
            for r in plan.monkey_rankings
        ],
    }


@router.get("")
async def list_runs(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
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
    graph = build_orchestrator_graph(checkpointer)
    config = run_thread_id(run_id)
    snapshot = await graph.aget_state(config)
    if snapshot is None or not snapshot.values:
        raise HTTPException(status_code=404, detail="No live state found")
    return dict(snapshot.values)


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(stream_run_events(run_id), media_type="text/event-stream")