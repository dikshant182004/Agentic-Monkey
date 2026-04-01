"""Thin orchestrator façade for API-facing run execution and SSE streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from backend.chaos.graphs import build_orchestrator_graph
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id

logger = logging.getLogger(__name__)


def _sse_event(event_name: str, payload: dict) -> str:
    """Format one Server-Sent Event with named event and JSON data payload."""
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


async def run_chaos_experiment(initial_state: dict) -> str:
    """Start orchestrator graph for one run and return run_id immediately."""
    run_id = initial_state.get("run_id") or str(uuid4())
    state = {**initial_state, "run_id": run_id}
    checkpointer = await get_redis_checkpointer()
    graph = build_orchestrator_graph(checkpointer)
    await graph.ainvoke(state, config=run_thread_id(run_id))
    return run_id


async def stream_run_events(run_id: str):
    """Yield periodic SSE events by polling checkpoint state and emitting heartbeat."""
    checkpointer = await get_redis_checkpointer()
    last_heartbeat = 0.0
    while True:
        snapshot = await checkpointer.aget(run_thread_id(run_id))
        now = asyncio.get_running_loop().time()
        if snapshot is None:
            yield _sse_event("complete", {"run_id": run_id, "status": "complete"})
            break
        state = snapshot.values
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
        else:
            yield _sse_event(
                "progress",
                {
                    "run_id": run_id,
                    "turn": state.get("current_turn", 0),
                    "monkey_type": state.get("current_monkey", ""),
                    "running_srq": state.get("running_srq", 0.0),
                    "status": state.get("status", "running"),
                },
            )
        if now - last_heartbeat >= 15:
            yield _sse_event("heartbeat", {"ts": datetime.now(timezone.utc).isoformat()})
            last_heartbeat = now
        if state.get("status") == "complete":
            yield _sse_event("complete", {"run_id": run_id, "summary": state.get("final_report", {})})
            break
        await asyncio.sleep(2)

