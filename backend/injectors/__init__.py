"""
ChaosAgent injectors package — v2.

Seed generation is now handled by seed_library.py (SEED_REGISTRY).
The old per-monkey template functions are kept for:
  - Backward compatibility with existing tests
  - Utility functions that do actual runtime work (not just strings):
      inject_history_corruption, inject_false_memory  (memory_entropy)
      FAILURE_MODES, inject_tool_failure              (tool_vortex)
      parallel_load_test                              (performance)

The 3 new monkey types (rag_poisoning, supply_chain, privilege_escalation)
have NO separate files — their seeds live entirely in seed_library.py.
Adding a new monkey type requires only adding seeds to seed_library.SEED_REGISTRY.
"""

# ── Runtime utility functions (still used by graph nodes) ─────────────────────

from backend.injectors.tool_vortex_monkey import (
    FAILURE_MODES,
    inject_tool_failure,
    generate_vortex_scenarios,
)

from backend.injectors.memory_entropy_monkey import (
    inject_history_corruption,
    inject_false_memory,
)

from backend.injectors.performance_monkey import (
    parallel_load_test,
)

# ── Legacy seed string generators (kept for test compatibility) ───────────────
# These are superseded by seed_library.py for actual chaos runs.

from backend.injectors.cti_monkey import (
    contradictory_instructions,
    context_window_poisoning,
    false_prior_injection,
    hallucination_bait,
    reasoning_drift_trap,
)

from backend.injectors.memory_entropy_monkey import (
    context_overflow_probe,
    memory_reset_attack,
)

from backend.injectors.security_storm_monkey import (
    action_hijack_probes,
    data_exfil_probes,
    indirect_injection_probes,
    jailbreak_probes,
    prompt_injection_attacks,
)

from backend.injectors.autonomy_probe_monkey import (
    escalating_ambiguity_probes,
    forced_loop_detection,
    hitl_trigger_mapping,
    silent_failure_traps,
    unsafe_action_boundary_probes,
)

from backend.injectors.performance_monkey import (
    bias_amplification_probe,
    cost_chaos_scenarios,
    ethical_drift_sequence,
    resource_exhaustion_probe,
)

# NOTE: inter_agent_monkey structured scenario functions (message_drop_simulation,
# rogue_agent_response, etc.) are NOT exported here — they take AgentConfig and
# are unused by any current graph node. Kept in the file for future use.

__all__ = [
    # Runtime utilities
    "FAILURE_MODES",
    "inject_tool_failure",
    "generate_vortex_scenarios",
    "inject_history_corruption",
    "inject_false_memory",
    "parallel_load_test",
    # Legacy seed generators (test compat)
    "contradictory_instructions",
    "false_prior_injection",
    "context_window_poisoning",
    "reasoning_drift_trap",
    "hallucination_bait",
    "context_overflow_probe",
    "memory_reset_attack",
    "prompt_injection_attacks",
    "jailbreak_probes",
    "data_exfil_probes",
    "action_hijack_probes",
    "indirect_injection_probes",
    "escalating_ambiguity_probes",
    "forced_loop_detection",
    "silent_failure_traps",
    "unsafe_action_boundary_probes",
    "hitl_trigger_mapping",
    "parallel_load_test",
    "cost_chaos_scenarios",
    "ethical_drift_sequence",
    "bias_amplification_probe",
    "resource_exhaustion_probe",
]