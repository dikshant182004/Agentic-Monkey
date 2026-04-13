"""Agent Card parser that normalises all supported input formats into AgentConfig.

Supported formats (per Google A2A spec + ChaosAgent internal card):
  A. Full ChaosAgent Agent Card JSON (preferred)
  B. Google A2A-compliant Agent Card JSON  (/.well-known/agent.json shape)
  C. Minimal card  {"endpoint": "..."}
  D. OpenAPI / Swagger spec
  E. Plain URL string
  F. Any of the above serialised as YAML
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

# Preferred OpenAPI path fragments (most → least semantic)
PREFERRED_OPENAPI_PATH_FRAGMENTS = ["/chat", "/invoke", "/messages", "/completions", "/run", "/tasks"]

# Google A2A canonical Agent Card field names
_A2A_URL_FIELD = "url"          # A2A spec uses "url" not "endpoint" for the service URL
_A2A_NAME_FIELD = "name"        # A2A spec uses "name" not "agent_name"
_A2A_VERSION_FIELD = "version"
_A2A_DESCRIPTION_FIELD = "description"
_A2A_CAPABILITIES_FIELD = "capabilities"
_A2A_SKILLS_FIELD = "skills"
_A2A_AUTH_FIELD = "authentication"      # A2A spec key
_CHAOS_AUTH_FIELD = "auth"              # ChaosAgent internal key
_A2A_DEFAULT_INPUT_MODES = "defaultInputModes"
_A2A_DEFAULT_OUTPUT_MODES = "defaultOutputModes"
_A2A_STREAMING_FIELD = "streaming"
_A2A_PUSH_NOTIFICATIONS_FIELD = "pushNotifications"


@dataclass
class AgentConfig:
    """Normalised A2A target agent configuration derived from uploaded cards.

    This is the single internal representation used everywhere in ChaosAgent.
    It is produced by parse_agent_card() regardless of the input format.
    """

    agent_name: str
    endpoint: str
    protocol: str = "http"         # "http" | "websocket"
    auth_type: str = "none"        # "none" | "bearer" | "api_key" | "basic" | "oauth2"
    auth_value: str = ""
    input_field: str = "message"   # JSON key used to send the prompt
    output_field: str = "response" # JSON key used to read the reply
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    memory_type: str = "unknown"
    supports_streaming: bool = False
    description: str = ""
    version: str = "1.0"
    a2a_version: str = ""          # populated when card explicitly carries a2a_version
    skills: list[dict] = field(default_factory=list)   # Google A2A "skills" array
    input_modes: list[str] = field(default_factory=lambda: ["text"])
    output_modes: list[str] = field(default_factory=lambda: ["text"])
    raw_card: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary (used to persist in DB)."""
        return asdict(self)


# ── Public entry point ────────────────────────────────────────────────────────

def parse_agent_card(raw_input: str | dict[str, Any]) -> AgentConfig:
    """Parse any supported agent card format and return a normalised AgentConfig.

    Handles:
    - dict / JSON string → ChaosAgent card, Google A2A card, OpenAPI spec, minimal card
    - YAML string → same as above after YAML→dict conversion
    - Bare URL string → minimal card
    """
    card = _normalise_to_dict(raw_input)

    # OpenAPI / Swagger: extract endpoint first, then continue with remaining fields
    if _is_openapi(card):
        endpoint = _extract_openapi_endpoint(card)
        card = {**card, "endpoint": endpoint}

    return _build_agent_config(card)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalise_to_dict(raw_input: str | dict[str, Any]) -> dict[str, Any]:
    """Convert any supported input type to a plain Python dict."""
    if isinstance(raw_input, dict):
        return raw_input

    content = raw_input.strip()

    # Bare URL
    if _looks_like_url(content):
        return {"endpoint": content}

    # JSON
    try:
        parsed: Any = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("JSON agent card must be a JSON object, not an array or scalar.")
    except json.JSONDecodeError:
        pass

    # YAML (fallback)
    try:
        parsed = yaml.safe_load(content)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("YAML agent card must be a mapping, not a sequence or scalar.")
    except yaml.YAMLError as exc:
        raise ValueError(f"Unable to parse agent card as JSON or YAML: {exc}") from exc


def _is_openapi(card: dict[str, Any]) -> bool:
    return "openapi" in card or "swagger" in card


def _build_agent_config(card: dict[str, Any]) -> AgentConfig:
    """Map a normalised dict onto AgentConfig, supporting both card schemas."""
    # ── Endpoint resolution ──────────────────────────────────────────────────
    # Google A2A cards use "url" at top level; ChaosAgent cards use "endpoint"
    endpoint = str(card.get("endpoint") or card.get("url") or "").strip()
    if not endpoint:
        raise ValueError(
            "Agent card must include a valid endpoint URL. "
            "Provide 'endpoint' (ChaosAgent format) or 'url' (Google A2A format)."
        )

    # ── Agent name ───────────────────────────────────────────────────────────
    # Google A2A uses "name"; ChaosAgent uses "agent_name"
    agent_name = str(card.get("agent_name") or card.get("name") or "unnamed-agent").strip()

    # ── Protocol ─────────────────────────────────────────────────────────────
    protocol = str(card.get("protocol", "http")).lower()
    if protocol not in {"http", "websocket"}:
        logger.warning("Unknown protocol %r — defaulting to 'http'", protocol)
        protocol = "http"

    # ── Auth ─────────────────────────────────────────────────────────────────
    # ChaosAgent card: auth = {"type": ..., "token": ...}
    # Google A2A card: authentication = {"schemes": [...]}
    auth_raw = card.get(_CHAOS_AUTH_FIELD) or card.get(_A2A_AUTH_FIELD) or {}
    auth_type, auth_value = _extract_auth(auth_raw)

    # ── Schema / field names ──────────────────────────────────────────────────
    input_field = _extract_primary_key(card.get("input_schema"), default="message")
    output_field = _extract_primary_key(card.get("output_schema"), default="response")

    # ── Capabilities ─────────────────────────────────────────────────────────
    # Google A2A uses "capabilities" as an object with flags, and "skills" as an array.
    # ChaosAgent internal cards use "capabilities" as a list[str].
    capabilities_raw = card.get("capabilities", [])
    if isinstance(capabilities_raw, dict):
        # Google A2A format: capabilities = {streaming: bool, pushNotifications: bool, …}
        # Extract the keys that are True as capability strings
        capabilities = [k for k, v in capabilities_raw.items() if v is True]
        supports_streaming = bool(capabilities_raw.get(_A2A_STREAMING_FIELD, False))
    else:
        capabilities = _to_str_list(capabilities_raw)
        supports_streaming = bool(card.get("supports_streaming", False))

    # ── Skills (Google A2A specific) ─────────────────────────────────────────
    skills_raw = card.get("skills", [])
    skills: list[dict] = []
    tools: list[str] = _to_str_list(card.get("tools", []))
    if isinstance(skills_raw, list):
        for skill in skills_raw:
            if isinstance(skill, dict):
                skills.append(skill)
                # Backfill capabilities and tools from skill metadata
                if "name" in skill and skill["name"] not in capabilities:
                    capabilities.append(str(skill["name"]))
                for tag in skill.get("tags", []):
                    if str(tag) not in tools:
                        tools.append(str(tag))

    # ── Input / output modalities (Google A2A specific) ──────────────────────
    input_modes = _to_str_list(card.get(_A2A_DEFAULT_INPUT_MODES, ["text"]))
    output_modes = _to_str_list(card.get(_A2A_DEFAULT_OUTPUT_MODES, ["text"]))
    if not input_modes:
        input_modes = ["text"]
    if not output_modes:
        output_modes = ["text"]

    return AgentConfig(
        agent_name=agent_name,
        endpoint=endpoint,
        protocol=protocol,
        auth_type=auth_type,
        auth_value=auth_value,
        input_field=input_field,
        output_field=output_field,
        capabilities=capabilities,
        tools=tools,
        memory_type=str(card.get("memory_type", "unknown")),
        supports_streaming=supports_streaming,
        description=str(card.get("description", "")),
        version=str(card.get("version", "1.0")),
        a2a_version=str(card.get("a2a_version", "")),
        skills=skills,
        input_modes=input_modes,
        output_modes=output_modes,
        raw_card=card,
    )


def _extract_openapi_endpoint(card: dict[str, Any]) -> str:
    """Extract the best POST endpoint URL from an OpenAPI/Swagger spec."""
    paths = card.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI card is missing a valid 'paths' object.")

    post_paths = [
        path
        for path, methods in paths.items()
        if isinstance(methods, dict)
        and any(m.lower() == "post" for m in methods)
    ]
    if not post_paths:
        raise ValueError("OpenAPI card does not define any POST endpoints.")

    preferred = _select_preferred_path(post_paths)

    servers = card.get("servers", [])
    base_url = ""
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        base_url = str(servers[0].get("url", "")).rstrip("/")
    # Swagger 2 host + basePath
    if not base_url:
        host = card.get("host", "")
        base_path = card.get("basePath", "")
        schemes = card.get("schemes", ["https"])
        scheme = schemes[0] if schemes else "https"
        if host:
            base_url = f"{scheme}://{host}{base_path}"

    return f"{base_url}{preferred}" if base_url else preferred


def _select_preferred_path(paths: list[str]) -> str:
    """Select the most semantically appropriate path from a list."""
    for fragment in PREFERRED_OPENAPI_PATH_FRAGMENTS:
        for path in paths:
            if fragment in path.lower():
                return path
    return paths[0]


def _extract_auth(auth_config: Any) -> tuple[str, str]:
    """Return (auth_type, auth_value) from a ChaosAgent or A2A auth block.

    ChaosAgent format:
        {"type": "bearer", "token": "sk-xxx"}
        {"type": "api_key", "key": "abc"}
        {"type": "basic", "username": "u", "password": "p"}

    Google A2A format:
        {"schemes": [{"type": "bearer"}, ...]}
        The auth_value cannot be extracted from A2A cards (they carry no secrets).
    """
    if not isinstance(auth_config, dict):
        return ("none", "")

    # Google A2A: authentication.schemes is a list of scheme objects
    if "schemes" in auth_config:
        schemes = auth_config["schemes"]
        if isinstance(schemes, list) and schemes:
            first = schemes[0]
            if isinstance(first, dict):
                scheme_type = str(first.get("type", first.get("scheme", "none"))).lower()
                if scheme_type in {"bearer", "http"}:
                    return ("bearer", "")
                if scheme_type in {"apikey", "api_key"}:
                    return ("api_key", "")
                if scheme_type == "basic":
                    return ("basic", "")
                if scheme_type in {"oauth2", "openidconnect", "openid_connect"}:
                    return ("oauth2", str(first.get("token_url", "")))
        return ("none", "")

    # ChaosAgent format
    auth_type = str(auth_config.get("type", "none")).lower()
    if auth_type == "bearer":
        return ("bearer", str(auth_config.get("token", "")))
    if auth_type == "api_key":
        return ("api_key", str(auth_config.get("key", "")))
    if auth_type == "basic":
        username = str(auth_config.get("username", ""))
        password = str(auth_config.get("password", ""))
        return ("basic", f"{username}:{password}")
    if auth_type in {"oauth2", "openidconnect"}:
        return ("oauth2", str(auth_config.get("token_url", "")))
    return ("none", "")


def _extract_primary_key(schema: Any, default: str) -> str:
    """Return first key from a dict schema, or fall back to default."""
    if isinstance(schema, dict) and schema:
        return str(next(iter(schema.keys())))
    return default


def _to_str_list(value: Any) -> list[str]:
    """Coerce any value to list[str]."""
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str) and value:
        return [value]
    return []


def _looks_like_url(value: str) -> bool:
    """Return True when value is an HTTP(S) or WS(S) URL."""
    parsed = urlparse(value)
    return bool(parsed.scheme in {"http", "https", "ws", "wss"} and parsed.netloc)