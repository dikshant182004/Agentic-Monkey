"""Schemas for chaos run creation and response payloads."""

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    """Payload for launching a chaos experiment."""

    agent_id: str
    monkeys_selected: list[str] = Field(default_factory=list)
    intensity: int = Field(default=3, ge=1, le=5)
    blast_radius: str = Field(default="staging")
    hypothesis: str = Field(default="")


class RunResponse(BaseModel):
    """Response containing run summary details."""

    id: str
    status: str
    blast_radius: str
    overall_srq: float = 0.0
    overall_hrt: float = 0.0
    overall_safety: float = 0.0

