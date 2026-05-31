"""
ChaosAgent Graph State Schemas — updated for v2.

Changes from v1:
  OrchestratorState:
    + refinement_budget      int  — remaining refinement calls this run
    + refinement_used        int  — total refinements used this run
    + current_attack_angle   str  — attack angle used this turn (from generator)
    + current_attack_surface str  — seed attack surface for precise evaluator guidance  ← NEW BUG-2
    + current_seed_id        str  — seed ID used this turn (for logging)
    + auto_planned           bool — whether experiment was auto-planned from A2A card

  ScenarioGenState:
    + selected_seed          dict | None — seed selected for this turn
    + agent_config           dict — agent config passed through for Layer 2 context
    + turn_scores            list[dict] — turn history for Layer 3 context
    + current_turn           int — current turn number for seed cycling
    + current_response       str — agent response (for refinement Layer 4)
    + current_safety_score   float — current safety score (for refinement gate)
    + refinement_budget      int — remaining budget (for refinement gate)
    + is_refined             bool — whether this turn was already refined
    + attack_angle           str — output: angle used
"""

from typing import Literal, Optional, TypedDict


class ScenarioGenState(TypedDict):
    """State for one scenario_generator graph invocation."""

    # Inputs
    seed_scenario: str           # legacy field, kept for compatibility
    agent_capabilities: list[str]
    agent_tools: list[str]
    monkey_type: str
    intensity: int               # 1-5

    # NEW: full agent config for Layer 2 context
    agent_config: dict

    # NEW: selected seed dict from seed library
    selected_seed: Optional[dict]

    # NEW: turn history for Layer 3 context
    turn_scores: list[dict]
    current_turn: int

    # NEW: refinement gate inputs
    current_response: str        # agent response from previous attempt
    current_safety_score: float  # score from evaluator (gate: only refine if > 6)
    refinement_budget: int       # decremented by orchestrator when refinement fires
    is_refined: bool             # True after first refinement — prevents double-refine

    # Outputs set by generator nodes
    system_prompt: str
    elaborated_prompt: str
    expected_behavior: str
    failure_hypothesis: str
    attack_angle: str            # social engineering angle used
    openpipe_request_id: str


class FailureInjectorState(TypedDict):
    """State for one failure_injector graph invocation (short-lived, deterministic)."""

    tool_response: dict
    failure_mode: str
    tool_name: str

    # Output
    mutated_response: dict | str


class EvaluatorState(TypedDict):
    """State for one evaluator graph invocation."""

    agent_id: str
    prompt: str
    agent_response: str
    monkey_type: str
    baseline_srq: float
    baseline_hrt: float

    # Technique context for more precise evaluation
    atlas_id: str                # MITRE ATLAS technique used
    owasp_category: str          # OWASP ASI category
    attack_surface: str          # what was targeted (reasoning/tools/memory/identity/…)
    failure_hypothesis: str      # what failure we were testing for
    attack_angle: str            # social engineering angle used

    # LTM context loaded by memory_loader
    past_afp_patterns: list[str]

    # Outputs
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
    """Main orchestrator state — persisted in Redis for the full run."""

    # ── Run identity ──────────────────────────────────────────────────────────
    run_id: str
    agent_id: str
    user_id: str
    agent_config: dict

    # ── LTM snapshot ──────────────────────────────────────────────────────────
    steady_state: dict

    # ── Experiment config ─────────────────────────────────────────────────────
    blast_radius: str
    monkeys_selected: list[str]
    intensity: int
    auto_planned: bool           # True if auto-planned from A2A card

    # ── Run-time accumulation ─────────────────────────────────────────────────
    current_turn: int
    total_turns_planned: int
    turn_scores: list[dict]
    afp_discoveries: list[dict]
    estimated_cost_usd: float
    consecutive_errors: int
    running_srq: float

    # ── Refinement budget ────────────────────────────────────────────────────
    refinement_budget: int       # decremented each time refinement fires
    refinement_used: int         # total refinements used this run

    # ── HITL fields ───────────────────────────────────────────────────────────
    hitl_pending: bool
    hitl_interaction_id: Optional[str]
    hitl_decision: Optional[Literal["approved", "rejected"]]
    hitl_required: bool

    # ── Terminal status ───────────────────────────────────────────────────────
    status: Literal["running", "paused_hitl", "paused_blast", "complete", "failed"]
    final_report: Optional[dict]

    # ── Per-turn staging fields ───────────────────────────────────────────────
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

    # ── Seed / technique metadata for logging ─────────────────────────────────
    current_attack_angle: str        # social engineering angle used this turn
    current_attack_surface: str      # seed attack surface (BUG-2 fix) ← NEW
    current_seed_id: str             # seed ID for reproducibility
    current_atlas_id: str            # MITRE ATLAS technique
    current_owasp_category: str      # OWASP ASI category
    current_failure_hypothesis: str  # what we were testing for