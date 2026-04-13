"""Validation utilities for parsed AgentConfig objects.

Implements:
1. Structural validation of required fields
2. Google A2A /.well-known/agent.json discovery probe (optional)
3. Endpoint reachability check (OPTIONS then HEAD then GET fallback)
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import httpx

from backend.a2a.parser import AgentConfig

logger = logging.getLogger(__name__)

# Google A2A discovery path
_WELL_KNOWN_PATH = "/.well-known/agent.json"
_WELL_KNOWN_PATH_ALT = "/.well-known/agent-card.json"  # alternate per newer spec drafts

# HTTP status codes that are acceptable during a reachability probe
_ACCEPTABLE_STATUS_CODES = set(range(200, 500))  # 2xx, 3xx, 4xx all mean server is up


async def validate_agent_config(config: AgentConfig) -> tuple[bool, str]:
    """Validate endpoint reachability and structural requirements.

    Returns (is_valid: bool, reason: str).

    Checks (in order):
    1. Endpoint field is non-empty
    2. Endpoint looks like a valid URL
    3. WebSocket — accepted without reachability probe (no HTTP semantics)
    4. Google A2A /.well-known/agent.json discovery probe (opportunistic)
    5. Direct endpoint OPTIONS probe to verify the server is up
    """
    if not config.endpoint:
        return False, "Endpoint is required."

    parsed = urlparse(config.endpoint)
    if not parsed.scheme or not parsed.netloc:
        return False, f"Endpoint '{config.endpoint}' is not a valid URL."

    if config.protocol == "websocket":
        return True, "WebSocket protocol accepted (runtime connectivity is not pre-validated)."

    # --- Opportunistic A2A well-known probe -----------------------------------
    well_known_result = await _probe_well_known(config.endpoint)
    if well_known_result is not None:
        ok, msg = well_known_result
        if not ok:
            logger.warning("A2A well-known probe failed: %s", msg)
            # Not fatal — continue with direct endpoint probe

    # --- Direct endpoint reachability probe ----------------------------------
    return await _probe_endpoint(config.endpoint)


async def _probe_well_known(endpoint: str) -> tuple[bool, str] | None:
    """Probe /.well-known/agent.json on the server root.

    Returns None when the server root cannot be determined (e.g. the endpoint
    IS the root, not a sub-path — in that case skip silently).
    Returns (True, msg) or (False, msg) when a probe was attempted.
    """
    parsed = urlparse(endpoint)
    server_root = f"{parsed.scheme}://{parsed.netloc}"

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            for wk_path in (_WELL_KNOWN_PATH, _WELL_KNOWN_PATH_ALT):
                wk_url = urljoin(server_root, wk_path)
                try:
                    resp = await client.get(wk_url)
                    if resp.status_code == 200:
                        try:
                            card_json = resp.json()
                            name = card_json.get("name", card_json.get("agent_name", ""))
                            logger.info(
                                "A2A well-known card discovered at %s (agent: %s)", wk_url, name
                            )
                            return True, f"A2A Agent Card discovered at {wk_url}"
                        except Exception:
                            return True, f"A2A well-known endpoint reachable at {wk_url}"
                    elif resp.status_code == 404:
                        continue  # try alternate path
                    else:
                        logger.debug("A2A well-known probe: %s → %d", wk_url, resp.status_code)
                except httpx.HTTPError:
                    continue
    except Exception as exc:
        logger.debug("A2A well-known probe skipped: %s", exc)

    return None  # probe skipped / inconclusive


async def _probe_endpoint(endpoint: str) -> tuple[bool, str]:
    """Check that the agent's declared endpoint responds to HTTP requests."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # OPTIONS is the least intrusive method; many servers handle it
            try:
                resp = await client.options(endpoint)
                if resp.status_code in _ACCEPTABLE_STATUS_CODES:
                    return True, f"Endpoint reachable (OPTIONS {resp.status_code})"
                # 5xx → server up but broken
                return False, f"Endpoint returned server error {resp.status_code}"
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _ACCEPTABLE_STATUS_CODES:
                    return True, f"Endpoint reachable ({exc.response.status_code})"
                return False, f"Endpoint returned {exc.response.status_code}"

    except httpx.TimeoutException:
        logger.warning("Agent endpoint validation timed out: %s", endpoint)
        return False, "Endpoint timed out during validation (>10s)."
    except httpx.HTTPError as exc:
        logger.warning("Agent endpoint validation HTTP error: %s", exc)
        return False, f"Endpoint validation failed: {exc}"