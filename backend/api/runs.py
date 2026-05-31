"""
ChaosAgent Runs API — v2 with dashboard endpoints.

Changes vs original:
  - POST /runs: initial_state now includes current_attack_surface (from states.py BUG-2 fix)
  - GET /runs/{run_id}/interactions: new — returns per-turn data for dashboard charts
  - GET /runs/{run_id}/afps: new — returns AFP list for dashboard heatmap
  - GET /runs/plan: unchanged (must stay above /{run_id} to avoid param capture)
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
from backend.db.session import get_db
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
    """Create run record and start orchestrator graph asynchronously."""
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
        intensity = payload.intensity if payload.intensity != 3 else plan.intensity
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
        # v2 seed / technique metadata — BUG-2 fix: current_attack_surface initialised
        "current_attack_angle": "",
        "current_attack_surface": "reasoning",    # ← BUG-2 fix
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


# NOTE: /plan must be defined BEFORE /{run_id} so FastAPI doesn't route
# GET /runs/plan to get_run with run_id="plan".
@router.get("/plan")
async def get_experiment_plan(
    agent_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Preview the auto-generated experiment plan for an agent WITHOUT launching a run."""
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
            "monkeys_selected": item.monkeys_selected,
            "overall_srq": item.overall_srq,
            "overall_hrt": item.overall_hrt,
            "overall_safety": item.overall_safety,
            "afp_count": item.afp_count,
            "agentic_resilience_score": item.agentic_resilience_score,
            "started_at": item.started_at.isoformat(),
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
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
        "monkeys_selected": run.monkeys_selected,
        "overall_srq": run.overall_srq,
        "overall_hrt": run.overall_hrt,
        "overall_safety": run.overall_safety,
        "afp_count": run.afp_count,
        "agentic_resilience_score": run.agentic_resilience_score,
        "estimated_cost_usd": run.estimated_cost_usd,
        "config": run.config,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.get("/{run_id}/interactions")
async def list_run_interactions(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return per-turn interaction data for dashboard charts.

    BUG-10 addition — previously this route did not exist so the dashboard
    had no way to fetch real SRQ/HRT/safety scores per turn.
    """
    run = await crud.get_run(db, run_id, user.user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    interactions = await crud.list_interactions(db, run_id)
    return [
        {
            "turn":                i.turn,
            "monkey_type":         i.monkey_type,
            "srq_score":           i.srq_score,
            "hrt_score":           i.hrt_score,
            "safety_score":        i.safety_score,
            "reasoning_score":     i.reasoning_score,
            "tool_recovery_score": i.tool_recovery_score,
            "is_afp":              i.is_afp,
            "self_corrected":      i.self_corrected,
            "hitl_required":       i.hitl_required,
            "hitl_decision":       i.hitl_decision,
            "notes":               i.notes,
            # Truncate prompt/response for the dashboard to keep payload small
            "prompt_snippet":      i.prompt[:200],
            "response_snippet":    i.agent_response[:200],
            "created_at":          i.created_at.isoformat(),
        }
        for i in interactions
    ]


@router.get("/{run_id}/afps")
async def list_run_afps(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return AFP discoveries for a run — used by dashboard heatmap.

    BUG-10 addition.
    """
    run = await crud.get_run(db, run_id, user.user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    afps = await crud.list_afps_for_run(db, run_id)
    return [
        {
            "monkey_type":    a.monkey_type,
            "severity":       a.severity,
            "description":    a.description,
            "recommendation": a.recommendation,
            "created_at":     a.created_at.isoformat(),
        }
        for a in afps
    ]


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