"""SQLAlchemy ORM models for ChaosAgent persistent storage.

Fix applied: replaced all `datetime.utcnow()` defaults with
`datetime.now(timezone.utc)` — `utcnow()` is deprecated in Python 3.12+
and removed in 3.14. The timezone-aware form is the correct replacement.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for all ORM models."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    agents: Mapped[list["Agent"]] = relationship(back_populates="user")
    runs: Mapped[list["Run"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"User(id={self.id!s}, email={self.email!r})"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_card: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="agents")
    steady_states: Mapped[list["SteadyState"]] = relationship(back_populates="agent")
    runs: Mapped[list["Run"]] = relationship(back_populates="agent")
    afps: Mapped[list["AFP"]] = relationship(back_populates="agent")

    def __repr__(self) -> str:
        return f"Agent(id={self.id!s}, name={self.name!r}, user_id={self.user_id!s})"


class SteadyState(Base):
    __tablename__ = "steady_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    baseline_srq: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_hrt: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_latency_p50: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_latency_p95: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_cost_per_task: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    agent: Mapped[Agent] = relationship(back_populates="steady_states")

    def __repr__(self) -> str:
        return f"SteadyState(id={self.id!s}, agent_id={self.agent_id!s})"


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    blast_radius: Mapped[str] = mapped_column(String(32), nullable=False)
    monkeys_selected: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    overall_srq: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overall_hrt: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overall_safety: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    afp_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ethical_drift_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    agentic_resilience_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped[Agent] = relationship(back_populates="runs")
    user: Mapped[User] = relationship(back_populates="runs")
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="run")
    afps: Mapped[list["AFP"]] = relationship(back_populates="run")

    def __repr__(self) -> str:
        return f"Run(id={self.id!s}, status={self.status!r}, agent_id={self.agent_id!s})"


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    monkey_type: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    agent_response: Mapped[str] = mapped_column(Text, nullable=False)
    failure_injected: Mapped[str] = mapped_column(Text, nullable=False, default="")
    srq_score: Mapped[float] = mapped_column(Float, nullable=False)
    hrt_score: Mapped[float] = mapped_column(Float, nullable=False)
    safety_score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning_score: Mapped[float] = mapped_column(Float, nullable=False)
    tool_recovery_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_afp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    self_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hitl_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hitl_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    openpipe_request_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    run: Mapped[Run] = relationship(back_populates="interactions")
    afps: Mapped[list["AFP"]] = relationship(back_populates="interaction")

    def __repr__(self) -> str:
        return f"Interaction(id={self.id!s}, run_id={self.run_id!s}, turn={self.turn})"


class AFP(Base):
    __tablename__ = "afps"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interaction_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monkey_type: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    agent_response: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    run: Mapped[Run] = relationship(back_populates="afps")
    interaction: Mapped[Interaction] = relationship(back_populates="afps")
    agent: Mapped[Agent] = relationship(back_populates="afps")

    def __repr__(self) -> str:
        return f"AFP(id={self.id!s}, run_id={self.run_id!s}, severity={self.severity!r})"