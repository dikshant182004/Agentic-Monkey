"""Thin orchestrator façade for API-facing run execution and SSE streaming.

LangGraph 1.x fixes applied:
- snapshot.values returns a dict_values view in newer checkpointers; always cast
  to dict() before calling .get() on it — this was the root cause of the
  AttributeError: 'dict_values' object has no attribute 'get' crash.
- Use graph.aget_state(config) instead of checkpointer.aget() directly; this
  returns a proper StateSnapshot whose .values is already a plain dict in 1.x,
  but we still defensively cast it.
"""

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
    """Yield periodic SSE events by polling checkpoint state and emitting heartbeat.

    Fix: snapshot.values in LangGraph 1.x may be a dict_values object from the
    channel manager. Always convert to a plain dict before any .get() calls.
    We use graph.aget_state() which is the blessed public API for reading state.
    """
    checkpointer = await get_redis_checkpointer()
    graph = build_orchestrator_graph(checkpointer)
    config = run_thread_id(run_id)
    last_heartbeat = 0.0

    while True:
        snapshot = await graph.aget_state(config)
        now = asyncio.get_running_loop().time()

        if snapshot is None or not snapshot.values:
            yield _sse_event("complete", {"run_id": run_id, "status": "complete"})
            break

        # ── FIX: cast to plain dict so .get() always works ──────────────────
        state: dict = dict(snapshot.values)

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
            yield _sse_event(
                "complete",
                {"run_id": run_id, "summary": state.get("final_report", {})},
            )
            break

        await asyncio.sleep(2)