"""Initial schema with six core models.

Revision ID: 20260401_0001
Revises:
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260401_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all base ChaosAgent tables and indexes."""
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("raw_card", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "steady_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_srq", sa.Float(), nullable=False),
        sa.Column("baseline_hrt", sa.Float(), nullable=False),
        sa.Column("baseline_latency_p50", sa.Float(), nullable=False),
        sa.Column("baseline_latency_p95", sa.Float(), nullable=False),
        sa.Column("baseline_cost_per_task", sa.Float(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_steady_states_agent_id", "steady_states", ["agent_id"], unique=False)

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blast_radius", sa.String(length=32), nullable=False),
        sa.Column("monkeys_selected", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("overall_srq", sa.Float(), nullable=False),
        sa.Column("overall_hrt", sa.Float(), nullable=False),
        sa.Column("overall_safety", sa.Float(), nullable=False),
        sa.Column("afp_count", sa.Integer(), nullable=False),
        sa.Column("ethical_drift_score", sa.Float(), nullable=False),
        sa.Column("agentic_resilience_score", sa.Float(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_runs_agent_id", "runs", ["agent_id"], unique=False)
    op.create_index("ix_runs_user_id", "runs", ["user_id"], unique=False)

    op.create_table(
        "interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("monkey_type", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("agent_response", sa.Text(), nullable=False),
        sa.Column("failure_injected", sa.Text(), nullable=False),
        sa.Column("srq_score", sa.Float(), nullable=False),
        sa.Column("hrt_score", sa.Float(), nullable=False),
        sa.Column("safety_score", sa.Float(), nullable=False),
        sa.Column("reasoning_score", sa.Float(), nullable=False),
        sa.Column("tool_recovery_score", sa.Float(), nullable=False),
        sa.Column("is_afp", sa.Boolean(), nullable=False),
        sa.Column("self_corrected", sa.Boolean(), nullable=False),
        sa.Column("hitl_required", sa.Boolean(), nullable=False),
        sa.Column("hitl_decision", sa.String(length=16), nullable=True),
        sa.Column("openpipe_request_id", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_interactions_run_id", "interactions", ["run_id"], unique=False)

    op.create_table(
        "afps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monkey_type", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("agent_response", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_afps_agent_id", "afps", ["agent_id"], unique=False)
    op.create_index("ix_afps_interaction_id", "afps", ["interaction_id"], unique=False)
    op.create_index("ix_afps_run_id", "afps", ["run_id"], unique=False)


def downgrade() -> None:
    """Drop all base ChaosAgent tables in reverse dependency order."""
    op.drop_index("ix_afps_run_id", table_name="afps")
    op.drop_index("ix_afps_interaction_id", table_name="afps")
    op.drop_index("ix_afps_agent_id", table_name="afps")
    op.drop_table("afps")
    op.drop_index("ix_interactions_run_id", table_name="interactions")
    op.drop_table("interactions")
    op.drop_index("ix_runs_user_id", table_name="runs")
    op.drop_index("ix_runs_agent_id", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_steady_states_agent_id", table_name="steady_states")
    op.drop_table("steady_states")
    op.drop_table("agents")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

