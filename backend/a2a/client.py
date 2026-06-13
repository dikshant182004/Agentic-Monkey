"""A2A client for invoking target agents.

Supports two communication modes:
1. **ChaosAgent simple mode** — plain JSON POST with configurable input/output field names.
   Used when the target agent is a simple REST API (not a full A2A server).

2. **Google A2A JSON-RPC mode** — sends a tasks/send JSON-RPC 2.0 request to a proper
   A2A-compliant server (message.parts[0].text as prompt, reads artifact/message back).
   Activated when AgentConfig.a2a_version is non-empty or the endpoint contains
   "/tasks" or "/rpc".

Both modes share the same auth handling and error recovery contract:
- Timeout: 30 s
- Never raises — always returns (response_text, latency_seconds)
- Error responses start with "[" so callers can detect them
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid

import httpx

from backend.a2a.parser import AgentConfig

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_A2A_RPC_METHOD = "tasks/send"
_A2A_RPC_VERSION = "2.0"
_TIMEOUT = 30.0


# ── Public API ─────────────────────────────────────────────────────────────────

async def call_agent(config: AgentConfig, message: str, session_id: str) -> tuple[str, float]:
    """Send an adversarial prompt to the target agent and return (response, latency_s).

    Chooses between ChaosAgent simple mode and Google A2A JSON-RPC mode automatically.
    Never raises — returns an error string on any failure.
    """
    if config.protocol == "websocket":
        raise NotImplementedError("WebSocket protocol support is planned for v2.")

    if _use_a2a_rpc_mode(config):
        return await _call_agent_a2a_rpc(config, message, session_id)
    return await _call_agent_simple(config, message, session_id)


# ── Mode detection ────────────────────────────────────────────────────────────

def _use_a2a_rpc_mode(config: AgentConfig) -> bool:
    """Return True when the target agent appears to be a full A2A JSON-RPC server."""
    if config.a2a_version:
        return True
    endpoint_lower = config.endpoint.lower()
    return "/tasks" in endpoint_lower or "/rpc" in endpoint_lower


# ── Simple REST mode ──────────────────────────────────────────────────────────

async def _call_agent_simple(
    config: AgentConfig, message: str, session_id: str
) -> tuple[str, float]:
    """Plain JSON POST — the original ChaosAgent communication style."""
    headers = _build_auth_headers(config)
    payload = {config.input_field: message, "session_id": session_id}
    start = asyncio.get_running_loop().time()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(config.endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return _extract_simple_response(data, config.output_field), _elapsed(start)
    except httpx.TimeoutException:
        logger.warning("A2A simple-mode timeout for %s", config.endpoint)
        return "[TIMEOUT: Agent did not respond within 30 seconds]", _TIMEOUT
    except httpx.HTTPStatusError as exc:
        logger.error("A2A simple-mode HTTP error: %s", exc)
        return f"[HTTP ERROR {exc.response.status_code}]", _elapsed(start)
    except httpx.HTTPError as exc:
        logger.exception("A2A simple-mode connection error")
        return f"[CONNECTION ERROR: {exc}]", _elapsed(start)
    except Exception as exc:
        logger.exception("A2A simple-mode unexpected error")
        return f"[ERROR: {exc}]", _elapsed(start)


# ── Google A2A JSON-RPC mode ──────────────────────────────────────────────────

async def _call_agent_a2a_rpc(
    config: AgentConfig, message: str, session_id: str
) -> tuple[str, float]:
    """Google A2A-compliant JSON-RPC 2.0 tasks/send request.

    Request shape (per A2A spec):
    {
      "jsonrpc": "2.0",
      "id": "<uuid>",
      "method": "tasks/send",
      "params": {
        "id": "<task-id>",
        "sessionId": "<session-id>",
        "message": {
          "role": "user",
          "parts": [{"type": "text", "text": "<prompt>"}]
        }
      }
    }

    Response shape (success):
    {
      "jsonrpc": "2.0",
      "id": "<same uuid>",
      "result": {
        "id": "<task-id>",
        "status": {"state": "completed"},
        "artifacts": [
          {"parts": [{"type": "text", "text": "<response>"}]}
        ]
      }
    }
    """
    headers = _build_auth_headers(config)
    headers["Content-Type"] = "application/json"

    task_id = str(uuid.uuid4())
    rpc_id = str(uuid.uuid4())

    payload = {
        "jsonrpc": _A2A_RPC_VERSION,
        "id": rpc_id,
        "method": _A2A_RPC_METHOD,
        "params": {
            "id": task_id,
            "sessionId": session_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            },
        },
    }

    start = asyncio.get_running_loop().time()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(config.endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Check for JSON-RPC error object
        if "error" in data:
            err = data["error"]
            code = err.get("code", "?")
            msg = err.get("message", str(err))
            return f"[A2A RPC ERROR {code}: {msg}]", _elapsed(start)

        result = data.get("result", {})
        return _extract_a2a_response(result), _elapsed(start)

    except httpx.TimeoutException:
        logger.warning("A2A JSON-RPC timeout for %s", config.endpoint)
        return "[TIMEOUT: Agent did not respond within 30 seconds]", _TIMEOUT
    except httpx.HTTPStatusError as exc:
        logger.error("A2A JSON-RPC HTTP error: %s", exc)
        return f"[HTTP ERROR {exc.response.status_code}]", _elapsed(start)
    except httpx.HTTPError as exc:
        logger.exception("A2A JSON-RPC connection error")
        return f"[CONNECTION ERROR: {exc}]", _elapsed(start)
    except Exception as exc:
        logger.exception("A2A JSON-RPC unexpected error")
        return f"[ERROR: {exc}]", _elapsed(start)


# ── Response extraction helpers ───────────────────────────────────────────────

def _extract_simple_response(data: dict, output_field: str) -> str:
    """Extract response string from a simple REST response payload."""
    value = data.get(output_field, data.get("response", data))
    return value if isinstance(value, str) else json.dumps(value)


def _extract_a2a_response(result: dict) -> str:
    """Extract human-readable text from a Google A2A task result object.

    Priority:
    1. artifacts[0].parts[?type==text].text
    2. status.message.parts[?type==text].text
    3. Fallback: JSON dump of result
    """
    # Try artifacts first (completed task output)
    artifacts = result.get("artifacts", [])
    if artifacts and isinstance(artifacts, list):
        first = artifacts[0]
        text = _extract_text_from_parts(first.get("parts", []))
        if text:
            return text

    # Try status message (in-progress or input-required state)
    status = result.get("status", {})
    if isinstance(status, dict):
        status_msg = status.get("message", {})
        if isinstance(status_msg, dict):
            text = _extract_text_from_parts(status_msg.get("parts", []))
            if text:
                return text

    # Last resort: dump the whole result
    return json.dumps(result)


def _extract_text_from_parts(parts: list) -> str:
    """Return concatenated text content from A2A message parts."""
    texts = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("type") == "text":
                texts.append(str(part.get("text", "")))
            elif part.get("type") == "data":
                # Structured data part — JSON-dump it
                texts.append(json.dumps(part.get("data", {})))
            elif part.get("type") == "file":
                # File part — note presence only
                name = part.get("file", {}).get("name", "unnamed_file")
                texts.append(f"[FILE: {name}]")
    return "\n".join(texts)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _build_auth_headers(config: AgentConfig) -> dict[str, str]:
    """Build HTTP auth headers from AgentConfig."""
    headers: dict[str, str] = {}
    if config.auth_type == "bearer" and config.auth_value:
        headers["Authorization"] = f"Bearer {config.auth_value}"
    elif config.auth_type == "api_key" and config.auth_value:
        headers["x-api-key"] = config.auth_value
    elif config.auth_type == "basic" and config.auth_value:
        encoded = base64.b64encode(config.auth_value.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif config.auth_type == "oauth2" and config.auth_value:
        # auth_value holds a pre-obtained bearer token for OAuth2
        headers["Authorization"] = f"Bearer {config.auth_value}"
    return headers


# ── Timing helper ─────────────────────────────────────────────────────────────

def _elapsed(start: float) -> float:
    """Return elapsed seconds since start."""
    return asyncio.get_running_loop().time() - start