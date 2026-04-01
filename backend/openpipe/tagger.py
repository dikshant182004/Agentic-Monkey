"""OpenPipe feedback tagging for scored interactions."""

from __future__ import annotations

import logging

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


async def tag_interaction(openpipe_request_id: str, score: float, monkey_type: str) -> None:
    """Tag OpenPipe logged interaction with good/bad quality feedback."""
    if not openpipe_request_id:
        return
    label = "good" if score >= 7.0 else "bad"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"https://app.openpipe.ai/api/v1/request-logs/{openpipe_request_id}/feedback",
                headers={"Authorization": f"Bearer {settings.openpipe_api_key}"},
                json={"score": score / 10.0, "label": label, "comment": monkey_type},
            )
    except httpx.HTTPError:
        logger.exception("Failed to tag OpenPipe interaction")

