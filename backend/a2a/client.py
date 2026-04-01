"""A2A client for invoking target agents over HTTP protocol."""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx

from backend.a2a.parser import AgentConfig

logger = logging.getLogger(__name__)


def _build_auth_headers(config: AgentConfig) -> dict[str, str]:
    """Build auth headers from AgentConfig auth mode."""
    headers: dict[str, str] = {}
    if config.auth_type == "bearer" and config.auth_value:
        headers["Authorization"] = f"Bearer {config.auth_value}"
    elif config.auth_type == "api_key" and config.auth_value:
        headers["x-api-key"] = config.auth_value
    elif config.auth_type == "basic" and config.auth_value:
        token = base64.b64encode(config.auth_value.encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {token}"
    return headers


def _extract_response(data: dict, output_field: str) -> str:
    """Extract response string from the configured output field safely."""
    value = data.get(output_field, data.get("response", data))
    return value if isinstance(value, str) else str(value)


async def call_agent(config: AgentConfig, message: str, session_id: str) -> tuple[str, float]:
    """Send a prompt to target agent and return response text with latency seconds."""
    if config.protocol == "websocket":
        raise NotImplementedError("WebSocket protocol support coming in v2")
    headers = _build_auth_headers(config)
    payload = {config.input_field: message, "session_id": session_id}
    start = asyncio.get_running_loop().time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(config.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return _extract_response(data, config.output_field), asyncio.get_running_loop().time() - start
    except httpx.TimeoutException:
        logger.warning("A2A timeout for endpoint %s", config.endpoint)
        return "[TIMEOUT: Agent did not respond within 30 seconds]", 30.0
    except httpx.HTTPStatusError as exc:
        logger.error("A2A HTTP status error: %s", exc)
        return f"[HTTP ERROR {exc.response.status_code}]", 0.0
    except httpx.HTTPError as exc:
        logger.exception("A2A connection error")
        return f"[CONNECTION ERROR: {exc}]", 0.0

