"""TypedDict graph state schemas used by ChaosAgent LangGraph flows."""

from typing import Literal, Optional, TypedDict


class ScenarioGenState(TypedDict):
    """STM for scenario generator graph invocation."""

    seed_scenario: str
    agent_capabilities: list[str]
    agent_tools: list[str]
    monkey_type: str
    intensity: int
    system_prompt: str
    elaborated_prompt: str
    expected_behavior: str
    failure_hypothesis: str
    openpipe_request_id: str


class FailureInjectorState(TypedDict):
    """STM for failure injector graph invocation."""

    tool_response: dict
    failure_mode: str
    tool_name: str
    mutated_response: dict | str


class EvaluatorState(TypedDict):
    """STM for evaluator graph invocation."""

    agent_id: str
    prompt: str
    agent_response: str
    monkey_type: str
    baseline_srq: float
    baseline_hrt: float
    past_afp_patterns: list[str]
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
    """STM for main orchestrator graph run with Redis checkpoint persistence."""

    run_id: str
    agent_id: str
    user_id: str
    agent_config: dict
    steady_state: dict
    blast_radius: str
    monkeys_selected: list[str]
    intensity: int
    current_turn: int
    total_turns_planned: int
    turn_scores: list[dict]
    afp_discoveries: list[dict]
    estimated_cost_usd: float
    consecutive_errors: int
    running_srq: float
    hitl_pending: bool
    hitl_interaction_id: Optional[str]
    hitl_decision: Optional[Literal["approved", "rejected"]]
    hitl_required: bool
    status: Literal["running", "paused_hitl", "paused_blast", "complete", "failed"]
    final_report: Optional[dict]
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
    current_interaction_id: str
    current_token_cost_usd: float

