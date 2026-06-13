"""Thin orchestrator façade for API-facing run execution and SSE streaming.

Fixes applied (vs original)
───────────────────────────
BUG-1  stream_run_events called crud.get_run(session, run_id, user_id=None).
       SQL WHERE user_id = NULL never matches any row.  Now queries directly by
       run_id only (no user scope needed — this is an internal poller).

BUG-3  hitl_required SSE event was missing atlas_id and attack_angle.
       The Streamlit HITL panel reads both fields to display technique context.
       They are now forwarded from the interrupt payload (preferred) or from
       the checkpoint state (fallback).

BUG-4  progress SSE event was missing attack_angle and atlas_id.
       The Streamlit run page tries to display the current attack angle inline.
       Both fields are now included in the progress payload.

BUG-7  No stall detection when the graph is stuck INSIDE a node (LLM call
       hanging). snapshot.values is populated from the previous checkpoint so
       stall_ticks never incremented. Now we track last_seen_turn and count
       ticks where the turn counter does not advance; after 150 s we give up.

BUG-8  _mark_run_failed overwrote blast_radius with "unknown" and cleared
       monkeys_selected. We now query the Run row first and preserve the
       original values, only patching status / finished_at / error fields.

BUG-9/16 HITL detection broken: in LangGraph 1.x the graph is suspended
         INSIDE interrupt(); the checkpoint written before that call already has
         hitl_pending=False. stream_run_events must inspect snapshot.tasks[].interrupts
         to discover a pending interrupt rather than relying on the state flag.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from backend.chaos.graphs import build_orchestrator_graph
from backend.db import crud
from backend.db.models import Run
from backend.db.session import AsyncSessionFactory
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id

logger = logging.getLogger(__name__)

# How many 2-second ticks with no turn progress before we declare a stall.
# 150 s gives generous headroom for slow LLM providers.
_STALL_TICKS_LIMIT = 75


def _sse_event(event_name: str, payload: dict) -> str:
    """Format one Server-Sent Event with named event and JSON data payload."""
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


async def run_chaos_experiment(initial_state: dict) -> str:
    """Start orchestrator graph for one run and return run_id."""
    run_id = initial_state.get("run_id") or str(uuid4())
    state = {**initial_state, "run_id": run_id}
    checkpointer = await get_redis_checkpointer()
    graph = build_orchestrator_graph(checkpointer)
    await graph.ainvoke(state, config=run_thread_id(run_id))
    return run_id


def _detect_hitl_interrupt(snapshot) -> dict | None:
    """Return interrupt payload if the graph is suspended at a HITL interrupt.

    LangGraph 1.x suspends execution INSIDE interrupt(). The checkpoint written
    just before the suspension has the state values from BEFORE interrupt() was
    called. To detect the suspension we inspect snapshot.tasks — each pending
    task exposes a .interrupts tuple of PregelInterrupt objects that carry the
    interrupt payload passed to interrupt().

    Returns the interrupt payload dict, or None if the graph is not suspended.
    """
    try:
        tasks = getattr(snapshot, "tasks", None) or []
        for task in tasks:
            interrupts = getattr(task, "interrupts", None) or ()
            for intr in interrupts:
                value = getattr(intr, "value", None)
                if isinstance(value, dict):
                    return value
    except Exception as exc:  # pragma: no cover
        logger.debug("HITL interrupt probe failed: %s", exc)
    return None


async def _get_run_by_id(run_id: str) -> Run | None:
    """Fetch a Run row by id only — no user-scope filter (internal use)."""
    async with AsyncSessionFactory() as session:
        return await session.scalar(select(Run).where(Run.id == run_id))


async def _mark_run_failed(run_id: str, error: str) -> None:
    """Write failed status to the run record so SSE consumers see it.

    Preserves blast_radius and monkeys_selected from the existing row
    instead of overwriting them with placeholder values.
    """
    try:
        async with AsyncSessionFactory() as session:
            run = await session.scalar(select(Run).where(Run.id == run_id))
            if run is None:
                return
            await crud.update_run_final(
                session=session,
                run_id=run_id,
                status="failed",
                blast_radius=run.blast_radius,
                monkeys_selected=run.monkeys_selected,
                overall_srq=run.overall_srq,
                overall_hrt=run.overall_hrt,
                overall_safety=run.overall_safety,
                afp_count=run.afp_count,
                ethical_drift_score=run.ethical_drift_score,
                agentic_resilience_score=run.agentic_resilience_score,
                estimated_cost_usd=run.estimated_cost_usd,
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
    except Exception:
        logger.exception("Failed to mark run %s as failed in DB", run_id)


async def stream_run_events(run_id: str):
    """Yield periodic SSE events by polling checkpoint state.

    BUG-3 fix: hitl_required event now forwards atlas_id and attack_angle
               from the interrupt payload so the Streamlit HITL panel can
               display the technique context for the paused interaction.

    BUG-4 fix: progress event now includes attack_angle and atlas_id so the
               Streamlit run page can show the current attack angle inline.
    """
    checkpointer = await get_redis_checkpointer()
    graph = build_orchestrator_graph(checkpointer)
    config = run_thread_id(run_id)
    last_heartbeat = 0.0

    stall_ticks_no_checkpoint = 0
    last_seen_turn: int = -1
    stall_ticks_no_progress: int = 0

    while True:
        snapshot = await graph.aget_state(config)
        now = asyncio.get_running_loop().time()

        # ── No checkpoint yet ─────────────────────────────────────────────────
        if snapshot is None or not snapshot.values:
            run = await _get_run_by_id(run_id)
            if run is not None and run.status == "failed":
                yield _sse_event(
                    "error",
                    {"run_id": run_id, "error": "Run failed before first checkpoint"},
                )
                break

            stall_ticks_no_checkpoint += 1
            if stall_ticks_no_checkpoint > 30:  # 60 s
                yield _sse_event(
                    "error",
                    {"run_id": run_id, "error": "Timed out waiting for first checkpoint"},
                )
                break

            yield _sse_event("heartbeat", {"ts": datetime.now(timezone.utc).isoformat()})
            await asyncio.sleep(2)
            continue

        stall_ticks_no_checkpoint = 0
        state: dict = dict(snapshot.values)
        current_turn: int = state.get("current_turn", 0)

        # ── Stall detection: graph stuck inside a node ─────────────────────────
        if current_turn == last_seen_turn:
            stall_ticks_no_progress += 1
        else:
            last_seen_turn = current_turn
            stall_ticks_no_progress = 0

        if stall_ticks_no_progress >= _STALL_TICKS_LIMIT:
            logger.warning(
                "Run %s stalled: turn %d unchanged for %d ticks — marking failed",
                run_id, current_turn, stall_ticks_no_progress,
            )
            await _mark_run_failed(run_id, "Run stalled — no turn progress detected")
            yield _sse_event(
                "error",
                {"run_id": run_id, "error": "Run stalled with no progress — check LLM API keys"},
            )
            break

        # ── HITL detection via snapshot.tasks (LangGraph 1.x) ─────────────────
        hitl_payload = _detect_hitl_interrupt(snapshot)
        hitl_via_flag = state.get("hitl_pending", False)

        if hitl_payload or hitl_via_flag:
            # BUG-3 FIX: forward atlas_id and attack_angle from the interrupt
            # payload so the Streamlit HITL panel can show technique context.
            yield _sse_event(
                "hitl_required",
                {
                    "run_id": run_id,
                    "interaction_id": (
                        hitl_payload.get("interaction_id")
                        if hitl_payload
                        else state.get("hitl_interaction_id")
                    ),
                    "safety_score": (
                        hitl_payload.get("safety_score")
                        if hitl_payload
                        else state.get("current_safety_score")
                    ),
                    "severity": (
                        hitl_payload.get("severity")
                        if hitl_payload
                        else state.get("current_severity")
                    ),
                    "agent_response": (
                        hitl_payload.get("agent_response", "")
                        if hitl_payload
                        else state.get("current_response", "")
                    ),
                    # BUG-3 FIX ↓ — previously missing, Streamlit showed "unknown"
                    "atlas_id": (
                        hitl_payload.get("atlas_id", "")
                        if hitl_payload
                        else state.get("current_atlas_id", "")
                    ),
                    "attack_angle": (
                        hitl_payload.get("attack_angle", "")
                        if hitl_payload
                        else state.get("current_attack_angle", "")
                    ),
                    "attack_surface": (
                        hitl_payload.get("attack_surface", "")
                        if hitl_payload
                        else state.get("current_attack_surface", "")
                    ),
                },
            )

        elif state.get("status") == "failed":
            yield _sse_event(
                "error",
                {"run_id": run_id, "error": state.get("final_report") or "run failed"},
            )
            break

        elif state.get("status") == "complete":
            yield _sse_event(
                "complete",
                {"run_id": run_id, "summary": state.get("final_report", {})},
            )
            break

        else:
            # BUG-4 FIX: include attack_angle and atlas_id in progress events
            yield _sse_event(
                "progress",
                {
                    "run_id":       run_id,
                    "turn":         current_turn,
                    "monkey_type":  state.get("current_monkey", ""),
                    "running_srq":  state.get("running_srq", 0.0),
                    "status":       state.get("status", "running"),
                    # BUG-4 FIX ↓ — previously missing
                    "attack_angle": state.get("current_attack_angle", ""),
                    "atlas_id":     state.get("current_atlas_id", ""),
                },
            )

        if now - last_heartbeat >= 15:
            yield _sse_event("heartbeat", {"ts": datetime.now(timezone.utc).isoformat()})
            last_heartbeat = now

        await asyncio.sleep(2)