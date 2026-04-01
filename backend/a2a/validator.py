"""Validation utilities for parsed Agent Card configurations."""

from __future__ import annotations

import logging

import httpx

from backend.a2a.parser import AgentConfig

logger = logging.getLogger(__name__)


async def validate_agent_config(config: AgentConfig) -> tuple[bool, str]:
    """Validate endpoint reachability and structural requirements for an AgentConfig."""
    if not config.endpoint:
        return False, "Endpoint is required"
    if config.protocol == "websocket":
        return True, "WebSocket protocol accepted (runtime call is not yet implemented)"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.options(config.endpoint)
        if response.status_code >= 500:
            return False, f"Endpoint unhealthy with status {response.status_code}"
        return True, "Endpoint reachable"
    except httpx.TimeoutException:
        logger.warning("Agent endpoint validation timed out for %s", config.endpoint)
        return False, "Endpoint timed out during validation"
    except httpx.HTTPError as exc:
        logger.warning("Agent endpoint validation HTTP error: %s", exc)
        return False, f"Endpoint validation failed: {exc}"

