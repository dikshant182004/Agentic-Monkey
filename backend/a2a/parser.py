"""Agent Card parser that normalizes multiple input formats into AgentConfig."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

import yaml

PREFERRED_OPENAPI_PATH_FRAGMENTS = ["/chat", "/invoke", "/messages", "/completions", "/run"]


@dataclass
class AgentConfig:
    """Normalized A2A target agent configuration derived from uploaded cards."""

    agent_name: str
    endpoint: str
    protocol: str = "http"
    auth_type: str = "none"
    auth_value: str = ""
    input_field: str = "message"
    output_field: str = "response"
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    memory_type: str = "unknown"
    supports_streaming: bool = False
    description: str = ""
    raw_card: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the config dataclass to a serializable dictionary."""
        return asdict(self)


def parse_agent_card(raw_input: str | dict[str, Any]) -> AgentConfig:
    """Parse an agent card string/dict and return a normalized AgentConfig."""
    card = _normalize_to_dict(raw_input)
    if "openapi" in card or "swagger" in card:
        endpoint = _extract_openapi_endpoint(card)
        normalized_card = {"endpoint": endpoint, **card}
    else:
        normalized_card = card
    return _build_agent_config(normalized_card)


def _normalize_to_dict(raw_input: str | dict[str, Any]) -> dict[str, Any]:
    """Normalize input into a dictionary using JSON, YAML, or URL parsing."""
    if isinstance(raw_input, dict):
        return raw_input

    content = raw_input.strip()
    if _looks_like_url(content):
        return {"endpoint": content}

    try:
        parsed_json: Any = json.loads(content)
        if isinstance(parsed_json, dict):
            return parsed_json
        raise ValueError("JSON input must be an object")
    except json.JSONDecodeError:
        pass

    parsed_yaml: Any = yaml.safe_load(content)
    if isinstance(parsed_yaml, dict):
        return parsed_yaml

    raise ValueError("Unsupported agent card format. Expected dict, JSON, YAML, OpenAPI, or URL.")


def _build_agent_config(card: dict[str, Any]) -> AgentConfig:
    """Construct AgentConfig with defaults and schema-driven field extraction."""
    endpoint = str(card.get("endpoint", "")).strip()
    if not endpoint:
        raise ValueError("Agent card must include a valid endpoint.")
    protocol = str(card.get("protocol", "http")).lower()
    auth_type, auth_value = _extract_auth(card.get("auth", {}))
    input_field = _extract_primary_key(card.get("input_schema"), default="message")
    output_field = _extract_primary_key(card.get("output_schema"), default="response")

    return AgentConfig(
        agent_name=str(card.get("agent_name", "unnamed-agent")),
        endpoint=endpoint,
        protocol=protocol if protocol in {"http", "websocket"} else "http",
        auth_type=auth_type,
        auth_value=auth_value,
        input_field=input_field,
        output_field=output_field,
        capabilities=_to_str_list(card.get("capabilities", [])),
        tools=_to_str_list(card.get("tools", [])),
        memory_type=str(card.get("memory_type", "unknown")),
        supports_streaming=bool(card.get("supports_streaming", False)),
        description=str(card.get("description", "")),
        raw_card=card,
    )


def _extract_openapi_endpoint(card: dict[str, Any]) -> str:
    """Extract the first preferred POST endpoint from OpenAPI/Swagger specs."""
    paths = card.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI card is missing a valid paths object.")

    post_paths = [
        path
        for path, methods in paths.items()
        if isinstance(methods, dict) and "post" in {k.lower(): v for k, v in methods.items()}
    ]
    if not post_paths:
        raise ValueError("OpenAPI card does not define any POST endpoints.")

    preferred = _select_preferred_path(post_paths)
    servers = card.get("servers", [])
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        base_url = str(servers[0].get("url", "")).rstrip("/")
    else:
        base_url = ""
    if base_url:
        return f"{base_url}{preferred}"
    return preferred


def _select_preferred_path(paths: list[str]) -> str:
    """Select semantic OpenAPI path first, then fallback to document order."""
    for fragment in PREFERRED_OPENAPI_PATH_FRAGMENTS:
        for path in paths:
            if fragment in path.lower():
                return path
    return paths[0]


def _extract_auth(auth_config: Any) -> tuple[str, str]:
    """Extract auth type and value from auth object."""
    if not isinstance(auth_config, dict):
        return ("none", "")
    auth_type = str(auth_config.get("type", "none")).lower()
    if auth_type == "bearer":
        return ("bearer", str(auth_config.get("token", "")))
    if auth_type == "api_key":
        return ("api_key", str(auth_config.get("key", "")))
    if auth_type == "basic":
        username = str(auth_config.get("username", ""))
        password = str(auth_config.get("password", ""))
        return ("basic", f"{username}:{password}")
    return ("none", "")


def _extract_primary_key(schema: Any, default: str) -> str:
    """Extract first field name from schema dictionaries."""
    if isinstance(schema, dict) and schema:
        return str(next(iter(schema.keys())))
    return default


def _to_str_list(value: Any) -> list[str]:
    """Ensure a value is represented as a list of strings."""
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _looks_like_url(value: str) -> bool:
    """Return true if value appears to be an HTTP(S) or WS(S) URL."""
    parsed = urlparse(value)
    return bool(parsed.scheme in {"http", "https", "ws", "wss"} and parsed.netloc)

