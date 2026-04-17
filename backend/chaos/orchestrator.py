"""Thin orchestrator façade for API-facing run execution and SSE streaming.

FIX: stream_run_events now detects the "failed" status from the DB (written by
the task error callback in runs.py) and emits an error SSE event + breaks out
of the loop instead of polling forever when the graph has crashed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from backend.chaos.graphs import build_orchestrator_graph
from backend.db import crud
from backend.db.session import AsyncSessionFactory
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id

logger = logging.getLogger(__name__)


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


async def stream_run_events(run_id: str):
    """Yield periodic SSE events by polling checkpoint state.

    FIX: If the graph task has crashed (status="failed" in DB), we emit an
    error event and stop — previously this looped forever.
    """
    checkpointer = await get_redis_checkpointer()
    graph = build_orchestrator_graph(checkpointer)
    config = run_thread_id(run_id)
    last_heartbeat = 0.0
    stall_ticks = 0          # count consecutive polls with no state change
    last_turn = -1

    while True:
        snapshot = await graph.aget_state(config)
        now = asyncio.get_running_loop().time()

        # ── No checkpoint yet — graph may still be initializing ──────────────
        if snapshot is None or not snapshot.values:
            # Check DB to see if the run was marked failed before first checkpoint
            async with AsyncSessionFactory() as session:
                run = await crud.get_run(session, run_id, user_id=None)  # type: ignore[arg-type]

            if run is not None and run.status == "failed":
                yield _sse_event("error", {"run_id": run_id, "error": "Run failed before first checkpoint"})
                break

            stall_ticks += 1
            if stall_ticks > 30:  # 60s without a checkpoint → give up
                yield _sse_event("error", {"run_id": run_id, "error": "Timed out waiting for first checkpoint"})
                break

            yield _sse_event("heartbeat", {"ts": datetime.now(timezone.utc).isoformat()})
            await asyncio.sleep(2)
            continue

        stall_ticks = 0
        state: dict = dict(snapshot.values)
        current_turn = state.get("current_turn", 0)

        # Detect turn progress to reset stall counter
        if current_turn != last_turn:
            last_turn = current_turn

        if state.get("hitl_pending"):
            yield _sse_event(
                "hitl_required",
                {
                    "run_id": run_id,
                    "interaction_id": state.get("hitl_interaction_id"),
                    "safety_score": state.get("current_safety_score"),
                    "severity": state.get("current_severity"),
                    "agent_response": state.get("current_response", ""),
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
            yield _sse_event(
                "progress",
                {
                    "run_id": run_id,
                    "turn": current_turn,
                    "monkey_type": state.get("current_monkey", ""),
                    "running_srq": state.get("running_srq", 0.0),
                    "status": state.get("status", "running"),
                },
            )

        if now - last_heartbeat >= 15:
            yield _sse_event("heartbeat", {"ts": datetime.now(timezone.utc).isoformat()})
            last_heartbeat = now

        await asyncio.sleep(2)