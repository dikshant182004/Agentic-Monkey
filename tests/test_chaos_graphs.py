"""Tests for chaos graph state transitions and utility functions."""

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
    {"srq_score": 8.0, "hrt_score": 7.0, "is_afp": False},
    {"srq_score": 4.0, "hrt_score": 3.0, "is_afp": True},
    {"srq_score": 6.0, "hrt_score": 6.0, "is_afp": False},
]


def test_compute_overall_srq():
    result = compute_overall_srq(_SAMPLE_TURNS)
    assert abs(result - 6.0) < 0.01


def test_compute_overall_hrt():
    result = compute_overall_hrt(_SAMPLE_TURNS)
    assert abs(result - (16.0 / 3)) < 0.01


def test_compute_afp_density():
    result = compute_afp_density(_SAMPLE_TURNS)
    assert abs(result - (1 / 3)) < 0.01


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


# ── Injector scenario generators ──────────────────────────────────────────────

def test_cti_contradictory_instructions_returns_list():
    results = contradictory_instructions(["code_generation", "summarization"])
    assert len(results) == 2
    assert all(isinstance(s, str) for s in results)


def test_cti_hallucination_bait_fallback_on_empty():
    results = hallucination_bait([])
    assert len(results) == 1
    assert "general" in results[0]


def test_tool_vortex_failure_modes_cover_all_types():
    modes = list(FAILURE_MODES.keys())
    expected = {"timeout", "wrong_result", "empty_response", "malformed_json",
                "quota_exceeded", "wrong_type", "partial_response", "malicious_data",
                "infinite_loop_hint"}
    assert set(modes) == expected


def test_tool_vortex_timeout_mode():
    result = FAILURE_MODES["timeout"]({"result": "ok"})
    assert "error" in result
    assert "timed out" in result["error"].lower()


def test_tool_vortex_malicious_data_contains_sql():
    result = FAILURE_MODES["malicious_data"]({"result": "clean"})
    assert "DROP TABLE" in str(result)


def test_generate_vortex_scenarios_cross_product():
    scenarios = generate_vortex_scenarios(["tool_a", "tool_b"])
    # 2 tools × 9 failure modes = 18 scenarios
    assert len(scenarios) == 18
    for s in scenarios:
        assert "tool_name" in s
        assert "failure_mode" in s
        assert "scenario" in s


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