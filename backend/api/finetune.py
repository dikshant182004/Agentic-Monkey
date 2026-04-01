"""OpenPipe fine-tuning API routes."""

from fastapi import APIRouter, Depends

from backend.auth.dependencies import get_current_user
from backend.config import settings
from backend.openpipe.trainer import poll_finetune, trigger_finetune

router = APIRouter(prefix="/finetune", tags=["finetune"])


@router.get("/stats")
async def finetune_stats(user=Depends(get_current_user)) -> dict:
    """Return placeholder OpenPipe dataset stats used by UI cards."""
    return {"total_logged": 0, "good_tagged": 0, "bad_tagged": 0}


@router.post("/trigger")
async def finetune_trigger(user=Depends(get_current_user)) -> dict:
    """Trigger OpenPipe fine-tune job and return API payload."""
    return await trigger_finetune()


@router.get("/status/{job_id}")
async def finetune_status(job_id: str, user=Depends(get_current_user)) -> dict:
    """Poll OpenPipe fine-tune job status."""
    return await poll_finetune(job_id)


@router.post("/activate/{model_id}")
async def finetune_activate(model_id: str, user=Depends(get_current_user)) -> dict:
    """Return activation response reflecting chosen model id."""
    return {"status": "activated", "llm_model": model_id, "previous_model": settings.llm_model}

