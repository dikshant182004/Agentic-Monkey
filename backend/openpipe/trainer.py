"""OpenPipe fine-tune trigger and status polling helpers."""

from __future__ import annotations

import httpx

from backend.config import settings


async def trigger_finetune(base_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct") -> dict:
    """Create a new OpenPipe fine-tune job for scenario generation logs."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://app.openpipe.ai/api/v1/fine-tunes",
            headers={"Authorization": f"Bearer {settings.openpipe_api_key}"},
            json={
                "base_model": base_model,
                "filter_tags": {"flow": "scenario_gen"},
                "training_config": {"n_epochs": 3, "learning_rate": 2e-5},
            },
        )
        response.raise_for_status()
        return response.json()


async def poll_finetune(job_id: str) -> dict:
    """Poll OpenPipe fine-tune job status for a given job id."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"https://app.openpipe.ai/api/v1/fine-tunes/{job_id}",
            headers={"Authorization": f"Bearer {settings.openpipe_api_key}"},
        )
        response.raise_for_status()
        return response.json()

