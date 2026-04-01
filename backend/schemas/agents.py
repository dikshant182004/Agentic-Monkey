"""Pydantic schemas for agent registration and retrieval APIs."""

from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    """Payload to register a target agent from uploaded Agent Card."""

    card_content: str = Field(min_length=1)


class AgentResponse(BaseModel):
    """Serialized agent response model for API consumers."""

    id: str
    name: str
    description: str
    config: dict
    created_at: str

