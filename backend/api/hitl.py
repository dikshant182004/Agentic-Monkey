"""Human-in-the-loop approval and rejection routes for paused runs.

LangGraph 1.x migration:
─────────────────────────
OLD pattern (broken with 1.x snapshot.values):
    snapshot = await checkpointer.aget(config)
    updated_state = {**snapshot.values, "hitl_decision": "approved", ...}
    await graph.aupdate_state(config, updated_state)
    await graph.ainvoke(None, config)

NEW pattern (LangGraph 1.x — Command(resume=...)):
    await graph.ainvoke(Command(resume={"decision": "approved"}), config)

The resume payload becomes the return value of interrupt() inside hitl_gate,
which writes hitl_decision into state and returns normally. No manual state
patching required. The graph continues from exactly where it was suspended.
"""

from fastapi import APIRouter, Depends, HTTPException

from langgraph.types import Command

from backend.auth.dependencies import get_current_user
from backend.chaos.graphs import build_orchestrator_graph
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id

router = APIRouter(prefix="/runs", tags=["hitl"])


@router.post("/{run_id}/approve")
async def approve_turn(
    run_id: str,
    user=Depends(get_current_user),
    checkpointer=Depends(get_redis_checkpointer),
) -> dict:
    """Approve paused interaction and resume graph execution.

    Sends Command(resume={"decision": "approved"}) to the suspended graph.
    The interrupt() call in hitl_gate receives this as its return value.
    """
    config = run_thread_id(run_id)
    graph = build_orchestrator_graph(checkpointer)

    # Verify the run exists and is actually paused before resuming
    snapshot = await graph.aget_state(config)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run state not found")

    # LangGraph 1.x: resume via Command — no manual state patching needed
    await graph.ainvoke(Command(resume={"decision": "approved"}), config)
    return {"status": "resumed", "run_id": run_id}


@router.post("/{run_id}/reject")
async def reject_turn(
    run_id: str,
    user=Depends(get_current_user),
    checkpointer=Depends(get_redis_checkpointer),
) -> dict:
    """Reject paused interaction and resume graph (interaction still logged as rejected).

    Sends Command(resume={"decision": "rejected"}) to the suspended graph.
    """
    config = run_thread_id(run_id)
    graph = build_orchestrator_graph(checkpointer)

    snapshot = await graph.aget_state(config)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run state not found")

    await graph.ainvoke(Command(resume={"decision": "rejected"}), config)
    return {"status": "rejected_and_skipped", "run_id": run_id}