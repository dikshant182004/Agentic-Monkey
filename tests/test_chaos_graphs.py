"""Tests for chaos graph state transitions and utility functions.

Coverage added vs original:
  - 3 new monkey types: rag_poisoning, supply_chain, privilege_escalation
  - inter_agent and performance monkey functions
  - seed_library: get_seed, get_seeds, get_intensity_appropriate_seeds,
    ALL_MONKEY_TYPES completeness, CAPABILITY_MONKEY_AFFINITY structure
  - experiment_planner: deterministic scoring helpers
  - build_report: afp_count and overall_safety keys present (regression guard)
"""

from __future__ import annotations

import pytest

from backend.chaos.graphs.states import OrchestratorState
from backend.chaos.hypothesis import generate_hypothesis, validate_hypothesis
from backend.evaluation.metrics import (
    compute_afp_density,
    compute_overall_hrt,
    compute_overall_srq,
)
from backend.evaluation.report import build_report
from backend.injectors.cti_monkey import contradictory_instructions, hallucination_bait
from backend.injectors.tool_vortex_monkey import FAILURE_MODES, generate_vortex_scenarios
from backend.injectors.security_storm_monkey import prompt_injection_attacks
from backend.injectors.memory_entropy_monkey import context_overflow_probe
from backend.injectors.autonomy_probe_monkey import escalating_ambiguity_probes
from backend.injectors.inter_agent_monkey import (
    fabricated_consensus_probe,
    orchestrator_manipulation_probe,
    peer_agent_impersonation,
    trust_escalation_probe,
)
from backend.injectors.performance_monkey import (
    bias_amplification_probe,
    cost_chaos_scenarios,
    ethical_drift_sequence,
    resource_exhaustion_probe,
)
from backend.injectors.seed_library import (
    ALL_MONKEY_TYPES,
    CAPABILITY_MONKEY_AFFINITY,
    SEED_REGISTRY,
    TOOL_MONKEY_AFFINITY,
    get_intensity_appropriate_seeds,
    get_seed,
    get_seeds,
)
from backend.chaos.experiment_planner import (
    _recommend_blast_radius,
    _recommend_intensity,
    _score_monkeys_from_card,
)
from backend.a2a.parser import AgentConfig
from backend.memory.stm import init_stm, update_stm_with_turn


# ── Hypothesis helpers ────────────────────────────────────────────────────────

def test_generate_hypothesis_includes_monkeys():
    h = generate_hypothesis(["cti", "tool_vortex"], 3)
    assert "cti" in h
    assert "tool_vortex" in h
    assert "3" in h


def test_validate_hypothesis_rejects_short():
    assert validate_hypothesis("ok") is False


def test_validate_hypothesis_accepts_long_enough():
    assert validate_hypothesis("This is a valid hypothesis statement.") is True


# ── Evaluation metrics ────────────────────────────────────────────────────────

_SAMPLE_TURNS = [
    {"srq_score": 8.0, "hrt_score": 7.0, "is_afp": False, "safety_score": 9.0},
    {"srq_score": 4.0, "hrt_score": 3.0, "is_afp": True,  "safety_score": 2.0},
    {"srq_score": 6.0, "hrt_score": 6.0, "is_afp": False, "safety_score": 7.0},
]


def test_compute_overall_srq():
    assert abs(compute_overall_srq(_SAMPLE_TURNS) - 6.0) < 0.01


def test_compute_overall_hrt():
    assert abs(compute_overall_hrt(_SAMPLE_TURNS) - (16.0 / 3)) < 0.01


def test_compute_afp_density():
    assert abs(compute_afp_density(_SAMPLE_TURNS) - (1 / 3)) < 0.01


def test_compute_metrics_empty_list():
    assert compute_overall_srq([]) == 0.0
    assert compute_overall_hrt([]) == 0.0
    assert compute_afp_density([]) == 0.0


def test_build_report_shape():
    report = build_report("run-abc", _SAMPLE_TURNS)
    assert report["run_id"] == "run-abc"
    assert "overall_srq" in report
    assert "overall_hrt" in report
    assert "afp_density" in report
    assert "agentic_resilience_score" in report
    assert 0.0 <= report["agentic_resilience_score"] <= 100.0


def test_build_report_has_afp_count_and_safety():
    """Regression guard: finalize_run accesses these keys — must not be missing."""
    report = build_report("run-xyz", _SAMPLE_TURNS)
    assert "afp_count" in report, "afp_count missing from report — finalize_run will KeyError"
    assert "overall_safety" in report, "overall_safety missing — finalize_run will KeyError"
    assert report["afp_count"] == 1


# ── Legacy injector scenario generators ──────────────────────────────────────

def test_cti_contradictory_instructions_returns_list():
    results = contradictory_instructions(["code_generation", "summarization"])
    assert len(results) == 2
    assert all(isinstance(s, str) for s in results)


def test_cti_hallucination_bait_fallback_on_empty():
    results = hallucination_bait([])
    assert len(results) == 1
    assert "general" in results[0]


def test_tool_vortex_failure_modes_cover_all_types():
    modes = set(FAILURE_MODES.keys())
    expected = {
        "timeout", "wrong_result", "empty_response", "malformed_json",
        "quota_exceeded", "wrong_type", "partial_response", "malicious_data",
        "infinite_loop_hint",
    }
    assert modes == expected


def test_tool_vortex_timeout_mode():
    result = FAILURE_MODES["timeout"]({"result": "ok"})
    assert "error" in result
    assert "timed out" in result["error"].lower()


def test_tool_vortex_malicious_data_contains_sql():
    result = FAILURE_MODES["malicious_data"]({"result": "clean"})
    assert "DROP TABLE" in str(result)


def test_generate_vortex_scenarios_cross_product():
    scenarios = generate_vortex_scenarios(["tool_a", "tool_b"])
    assert len(scenarios) == 18   # 2 tools × 9 failure modes
    for s in scenarios:
        assert "tool_name" in s
        assert "failure_mode" in s


def test_security_storm_returns_strings():
    results = prompt_injection_attacks(["search", "code_exec"])
    assert all(isinstance(s, str) for s in results)


def test_memory_entropy_context_overflow():
    results = context_overflow_probe(["summarize"])
    assert len(results) == 1
    assert "oversized" in results[0].lower()


def test_autonomy_probe_escalating_ambiguity():
    results = escalating_ambiguity_probes(["file_management"])
    assert len(results) == 1
    assert "clarifying" in results[0].lower()


# ── Inter-agent monkey (was untested) ────────────────────────────────────────

def test_inter_agent_orchestrator_manipulation():
    results = orchestrator_manipulation_probe(["data_processing"])
    assert len(results) == 1
    assert "override" in results[0].lower() or "orchestrator" in results[0].lower()


def test_inter_agent_peer_impersonation():
    results = peer_agent_impersonation(["summarize"])
    assert len(results) == 1
    assert isinstance(results[0], str)


def test_inter_agent_trust_escalation():
    results = trust_escalation_probe(["file_management"])
    assert len(results) == 1
    assert "elevated" in results[0].lower() or "permissions" in results[0].lower()


def test_inter_agent_fabricated_consensus():
    results = fabricated_consensus_probe(["payment"])
    assert len(results) == 1
    assert "voted" in results[0].lower() or "consensus" in results[0].lower()


def test_inter_agent_fallback_on_empty_caps():
    results = orchestrator_manipulation_probe([])
    assert len(results) == 1
    assert "general" in results[0]


# ── Performance monkey (was untested) ────────────────────────────────────────

def test_performance_ethical_drift_returns_list():
    results = ethical_drift_sequence(["summarize", "translate"])
    assert len(results) == 2
    assert all(isinstance(s, str) for s in results)


def test_performance_cost_chaos():
    results = cost_chaos_scenarios(["code_gen"])
    assert len(results) == 1
    assert "token" in results[0].lower() or "output" in results[0].lower()


def test_performance_bias_amplification():
    results = bias_amplification_probe(["analysis"])
    assert len(results) == 1
    assert isinstance(results[0], str)


def test_performance_resource_exhaustion():
    results = resource_exhaustion_probe(["db_query", "api_call"])
    assert len(results) == 2
    for r in results:
        assert "guardrail" in r.lower() or "cost" in r.lower() or "repeated" in r.lower()


# ── Seed library — new coverage ───────────────────────────────────────────────

def test_all_monkey_types_present():
    """All 10 monkey types must be in the registry."""
    expected = {
        "cti", "tool_vortex", "memory_entropy", "security_storm",
        "autonomy_probe", "inter_agent", "performance",
        "rag_poisoning", "supply_chain", "privilege_escalation",
    }
    assert set(ALL_MONKEY_TYPES) == expected


def test_seed_registry_covers_all_monkey_types():
    for monkey in ALL_MONKEY_TYPES:
        seeds = get_seeds(monkey)
        assert len(seeds) >= 1, f"{monkey} has no seeds in SEED_REGISTRY"


def test_get_seed_cycles_correctly():
    seeds = get_seeds("cti")
    n = len(seeds)
    for turn in range(n * 2):
        seed = get_seed("cti", turn)
        assert seed is not None
        assert seed["id"] == seeds[turn % n]["id"]


def test_get_seed_unknown_monkey_returns_none():
    assert get_seed("nonexistent_monkey", 0) is None


def test_get_intensity_appropriate_seeds_filters():
    # intensity=1 should return only seeds with intensity_min <= 1
    seeds_i1 = get_intensity_appropriate_seeds("cti", 1)
    for s in seeds_i1:
        assert s["intensity_min"] <= 1

    # intensity=5 should return all seeds (none filtered out)
    seeds_i5 = get_intensity_appropriate_seeds("cti", 5)
    all_seeds = get_seeds("cti")
    assert len(seeds_i5) == len(all_seeds)


def test_seeds_have_required_fields():
    required_fields = {
        "id", "description", "atlas_id", "owasp_category",
        "attack_surface", "intensity_min", "failure_hypo" , "weak_example", "strong_example",
    }
    # failure_hypothesis OR failure_hypo (both names used across seeds)
    flexible_field = {"failure_hypothesis", "failure_hypo"}
    for monkey in ALL_MONKEY_TYPES:
        for seed in get_seeds(monkey):
            for field in required_fields - flexible_field:
                assert field in seed, f"{monkey} seed {seed.get('id')} missing field '{field}'"
            assert flexible_field & seed.keys(), (
                f"{monkey} seed {seed.get('id')} missing failure_hypothesis/failure_hypo"
            )


# ── New monkey types: rag_poisoning ──────────────────────────────────────────

def test_rag_poisoning_seeds_exist():
    seeds = get_seeds("rag_poisoning")
    assert len(seeds) >= 3


def test_rag_poisoning_atlas_ids():
    for seed in get_seeds("rag_poisoning"):
        assert seed["atlas_id"].startswith("AML."), f"Bad atlas_id in {seed['id']}"
        assert seed["owasp_category"].startswith("ASI")


def test_rag_poisoning_attack_surface():
    for seed in get_seeds("rag_poisoning"):
        assert seed["attack_surface"] == "rag"


# ── New monkey types: supply_chain ────────────────────────────────────────────

def test_supply_chain_seeds_exist():
    seeds = get_seeds("supply_chain")
    assert len(seeds) >= 3


def test_supply_chain_atlas_ids():
    for seed in get_seeds("supply_chain"):
        assert seed["atlas_id"] == "AML.T0097", (
            f"supply_chain seed {seed['id']} should use AML.T0097"
        )


def test_supply_chain_attack_surface():
    for seed in get_seeds("supply_chain"):
        assert seed["attack_surface"] == "supply_chain"


# ── New monkey types: privilege_escalation ────────────────────────────────────

def test_privilege_escalation_seeds_exist():
    seeds = get_seeds("privilege_escalation")
    assert len(seeds) >= 4


def test_privilege_escalation_owasp():
    for seed in get_seeds("privilege_escalation"):
        assert seed["owasp_category"] == "ASI03", (
            f"privilege_escalation seed {seed['id']} should be ASI03"
        )


def test_privilege_escalation_intensity_range():
    """Should have at least one low-intensity seed (intensity_min=1) for canary runs."""
    low = [s for s in get_seeds("privilege_escalation") if s["intensity_min"] == 1]
    assert len(low) >= 1, "privilege_escalation needs at least one intensity_min=1 seed"


# ── CAPABILITY_MONKEY_AFFINITY / TOOL_MONKEY_AFFINITY structure ───────────────

def test_capability_affinity_values_are_valid_monkey_types():
    for keyword, monkeys in CAPABILITY_MONKEY_AFFINITY.items():
        for m in monkeys:
            assert m in ALL_MONKEY_TYPES, (
                f"CAPABILITY_MONKEY_AFFINITY['{keyword}'] references unknown monkey '{m}'"
            )


def test_tool_affinity_values_are_valid_monkey_types():
    for keyword, monkeys in TOOL_MONKEY_AFFINITY.items():
        for m in monkeys:
            assert m in ALL_MONKEY_TYPES, (
                f"TOOL_MONKEY_AFFINITY['{keyword}'] references unknown monkey '{m}'"
            )


# ── Experiment planner: deterministic helpers ─────────────────────────────────

def _make_config(**kwargs) -> AgentConfig:
    defaults = dict(
        agent_name="test-agent",
        endpoint="https://example.com/chat",
        capabilities=[],
        tools=[],
        memory_type="unknown",
        a2a_version="",
        skills=[],
        description="",
        version="1.0",
    )
    defaults.update(kwargs)
    return AgentConfig(**defaults)


def test_score_monkeys_returns_all_types():
    cfg = _make_config()
    scores = _score_monkeys_from_card(cfg)
    assert set(scores.keys()) == set(ALL_MONKEY_TYPES)


def test_score_monkeys_rag_affinity():
    cfg = _make_config(capabilities=["rag_search", "vector_retrieval"])
    scores = _score_monkeys_from_card(cfg)
    assert scores["rag_poisoning"] > scores["performance"], (
        "RAG agent should score rag_poisoning above performance"
    )


def test_score_monkeys_inter_agent_affinity_from_a2a():
    cfg = _make_config(a2a_version="1.0")
    scores = _score_monkeys_from_card(cfg)
    assert scores["inter_agent"] > 0


def test_recommend_intensity_low_risk():
    cfg = _make_config(capabilities=["summarize"], tools=[])
    intensity = _recommend_intensity(cfg)
    assert 1 <= intensity <= 3


def test_recommend_intensity_high_risk():
    cfg = _make_config(
        capabilities=["code_execution", "database_admin"],
        tools=["python_executor", "shell"],
    )
    intensity = _recommend_intensity(cfg)
    assert intensity >= 2


def test_recommend_blast_radius_for_low_intensity():
    cfg = _make_config()
    blast = _recommend_blast_radius(cfg, intensity=1)
    assert blast == "canary"


def test_recommend_blast_radius_for_high_intensity():
    cfg = _make_config(tools=["python_executor", "shell", "db_query"])
    blast = _recommend_blast_radius(cfg, intensity=3)
    assert blast == "staging"


# ── STM helpers ───────────────────────────────────────────────────────────────

def test_init_stm_sets_defaults():
    steady = {"baseline_srq": 7.5, "baseline_hrt": 8.0}
    stm = init_stm(steady)
    assert stm["steady_state"] == steady
    assert stm["current_turn"] == 0
    assert stm["running_srq"] == 7.5
    assert stm["hitl_pending"] is False
    assert stm["status"] == "running"


def test_update_stm_with_turn_increments_srq():
    steady = {"baseline_srq": 7.0}
    state = {**init_stm(steady), "turn_scores": [], "estimated_cost_usd": 0.0}
    updated = update_stm_with_turn(state, {"srq_score": 9.0, "token_cost": 0.01})
    assert len(updated["turn_scores"]) == 1
    assert updated["running_srq"] == 9.0
    assert abs(updated["estimated_cost_usd"] - 0.01) < 0.001


def test_update_stm_averages_multiple_turns():
    steady = {"baseline_srq": 7.0}
    state = {**init_stm(steady), "turn_scores": [], "estimated_cost_usd": 0.0}
    state = update_stm_with_turn(state, {"srq_score": 8.0, "token_cost": 0.0})
    state = update_stm_with_turn(state, {"srq_score": 4.0, "token_cost": 0.0})
    assert abs(state["running_srq"] - 6.0) < 0.01