"""TypedDict graph state schemas used by ChaosAgent LangGraph flows.

Every field that is accessed in any graph node MUST be declared here.
Nodes return {**state, ...updated_keys...} — undeclared keys are dropped
by LangGraph's state reducer.
"""

from typing import Literal, Optional, TypedDict


class ScenarioGenState(TypedDict):
    """STM for one scenario_generator graph invocation (short-lived)."""

    seed_scenario: str
    agent_capabilities: list[str]
    agent_tools: list[str]
    monkey_type: str
    intensity: int              # 1–5

    # Set by nodes:
    system_prompt: str
    elaborated_prompt: str
    expected_behavior: str
    failure_hypothesis: str
    openpipe_request_id: str


class FailureInjectorState(TypedDict):
    """STM for one failure_injector graph invocation (short-lived, deterministic)."""

    tool_response: dict
    failure_mode: str
    tool_name: str

    # Output:
    mutated_response: dict | str


class EvaluatorState(TypedDict):
    """STM for one evaluator graph invocation.

    NOTE: agent_id is required by the memory_loader node so it can scope
    AFP pattern queries to the specific agent under test (not all agents).
    The original implementation was missing this field and queried across
    all agents — that has been corrected.
    """

    agent_id: str               # ← required for LTM scoped AFP queries
    prompt: str
    agent_response: str
    monkey_type: str
    baseline_srq: float
    baseline_hrt: float

    # LTM context loaded by memory_loader node (PostgreSQL → STM):
    past_afp_patterns: list[str]

    # Outputs set by judge_response node:
    srq_score: float
    hrt_score: float
    safety_score: float
    reasoning_score: float
    tool_recovery_score: float
    is_afp: bool
    afp_description: str
    severity: Literal["low", "medium", "high", "critical"]
    self_corrected: bool
    notes: str
    openpipe_request_id: str


class OrchestratorState(TypedDict):
    """STM for the main orchestrator graph — persisted in Redis for the full run.

    This is the single source of truth for a live chaos experiment.
    Redis checkpointer snapshots this after every node boundary.

    STM vs LTM:
    - All fields here are STM (in-graph working memory for one run)
    - LTM lives in PostgreSQL: AFP table, SteadyState table, Interaction table
    - steady_state is loaded from LTM at run start and lives in STM from that point on
    """

    # ── Run identity ──────────────────────────────────────────────────────────
    run_id: str
    agent_id: str
    user_id: str
    agent_config: dict              # AgentConfig.to_dict() — serialised dataclass

    # ── LTM snapshot (loaded once at run start via load_context node) ─────────
    steady_state: dict              # SteadyState baseline metrics dict

    # ── Experiment config ─────────────────────────────────────────────────────
    blast_radius: str               # "dev" | "staging" | "canary"
    monkeys_selected: list[str]
    intensity: int                  # 1–5

    # ── Run-time accumulation (updated per turn) ──────────────────────────────
    current_turn: int
    total_turns_planned: int
    turn_scores: list[dict]         # one dict per completed turn
    afp_discoveries: list[dict]     # AFPs found this run (for in-run reference)
    estimated_cost_usd: float
    consecutive_errors: int
    running_srq: float              # rolling mean SRQ across completed turns

    # ── HITL fields ───────────────────────────────────────────────────────────
    hitl_pending: bool
    hitl_interaction_id: Optional[str]
    hitl_decision: Optional[Literal["approved", "rejected"]]
    hitl_required: bool             # ← True when this turn demanded HITL (for DB logging)

    # ── Terminal status ───────────────────────────────────────────────────────
    status: Literal["running", "paused_hitl", "paused_blast", "complete", "failed"]
    final_report: Optional[dict]

    # ── Per-turn staging fields (populated during a turn, consumed by log_and_continue) ──
    current_monkey: str
    current_prompt: str
    current_response: str
    current_latency: float
    current_safety_score: float
    current_is_afp: bool
    current_severity: str
    current_srq_score: float
    current_hrt_score: float
    current_reasoning_score: float
    current_tool_recovery_score: float
    current_self_corrected: bool
    current_notes: str
    current_afp_description: str
    current_openpipe_request_id: str
    current_interaction_id: str     # UUID string — generated fresh each turn
    current_token_cost_usd: float