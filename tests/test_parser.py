"""Tests for Agent Card parser normalization behavior."""

from backend.a2a.parser import parse_agent_card


def test_parse_full_card_format() -> None:
    """Parses the complete ChaosAgent card and preserves key fields."""
    raw = {
        "agent_name": "my-coding-assistant",
        "description": "Helps developers write and review Python code",
        "endpoint": "https://my-agent.example.com/chat",
        "protocol": "http",
        "auth": {"type": "bearer", "token": "sk-xxxx"},
        "input_schema": {"message": "string", "session_id": "string"},
        "output_schema": {"response": "string", "tool_calls": "array"},
        "capabilities": ["code_generation", "code_review"],
        "tools": ["python_executor"],
        "memory_type": "conversation_window",
        "supports_streaming": False,
    }
    cfg = parse_agent_card(raw)
    assert cfg.agent_name == "my-coding-assistant"
    assert cfg.endpoint == "https://my-agent.example.com/chat"
    assert cfg.auth_type == "bearer"
    assert cfg.input_field == "message"
    assert cfg.output_field == "response"


def test_parse_minimal_card_defaults() -> None:
    """Parses a minimal card and applies defaults."""
    cfg = parse_agent_card({"endpoint": "https://example.com/chat"})
    assert cfg.agent_name == "unnamed-agent"
    assert cfg.protocol == "http"
    assert cfg.auth_type == "none"
    assert cfg.input_field == "message"
    assert cfg.output_field == "response"


def test_parse_openapi_card_prefers_semantic_post_path() -> None:
    """Selects /chat-like path over non-semantic alternatives when available."""
    openapi_card = {
        "openapi": "3.1.0",
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/v1/internal/health-check": {"post": {"summary": "ping"}},
            "/v1/chat/completions": {"post": {"summary": "chat"}},
        },
    }
    cfg = parse_agent_card(openapi_card)
    assert cfg.endpoint == "https://api.example.com/v1/chat/completions"


def test_parse_plain_url_string() -> None:
    """Accepts plain URL input and converts to minimal card."""
    cfg = parse_agent_card("https://my-agent.example.com/chat")
    assert cfg.endpoint == "https://my-agent.example.com/chat"


def test_parse_yaml_card() -> None:
    """Parses YAML-formatted cards as a pre-processing fallback."""
    raw_yaml = """
agent_name: yaml-agent
endpoint: https://yaml.example.com/chat
auth:
  type: bearer
  token: abc123
"""
    cfg = parse_agent_card(raw_yaml)
    assert cfg.agent_name == "yaml-agent"
    assert cfg.auth_type == "bearer"
    assert cfg.auth_value == "abc123"

