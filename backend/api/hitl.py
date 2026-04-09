"""Human-in-the-loop approval and rejection routes for paused runs."""

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import get_current_user
from backend.chaos.graphs import build_orchestrator_graph
from backend.memory.redis_checkpointer import get_redis_checkpointer, run_thread_id

router = APIRouter(prefix="/runs", tags=["hitl"])


@router.post("/{run_id}/approve")
async def approve_turn(run_id: str, user=Depends(get_current_user), checkpointer=Depends(get_redis_checkpointer)) -> dict:
    """Approve paused interaction and resume graph execution."""
    config = run_thread_id(run_id)
    snapshot = await checkpointer.aget(config)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run state not found")
    updated_state = {**snapshot.values, "hitl_decision": "approved", "hitl_pending": False}
    graph = build_orchestrator_graph(checkpointer)
    await graph.aupdate_state(config, updated_state)
    await graph.ainvoke(None, config)
    return {"status": "resumed", "run_id": run_id}


@router.post("/{run_id}/reject")
async def reject_turn(run_id: str, user=Depends(get_current_user), checkpointer=Depends(get_redis_checkpointer)) -> dict:
    """Reject paused interaction and resume graph by skipping current turn."""
    config = run_thread_id(run_id)
    snapshot = await checkpointer.aget(config)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run state not found")
    updated_state = {**snapshot.values, "hitl_decision": "rejected", "hitl_pending": False}
    graph = build_orchestrator_graph(checkpointer)
    await graph.aupdate_state(config, updated_state)
    await graph.ainvoke(None, config)
    return {"status": "rejected_and_skipped", "run_id": run_id}

