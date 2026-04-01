"""Exports for ChaosAgent Agentic Simian Army injectors."""

from backend.injectors.autonomy_probe_monkey import (
    escalating_ambiguity_probes,
    forced_loop_detection,
    hitl_trigger_mapping,
    silent_failure_traps,
    unsafe_action_boundary_probes,
)
from backend.injectors.cti_monkey import (
    contradictory_instructions,
    context_window_poisoning,
    false_prior_injection,
    hallucination_bait,
    reasoning_drift_trap,
)
from backend.injectors.memory_entropy_monkey import (
    context_overflow_probe,
    inject_false_memory,
    inject_history_corruption,
    memory_reset_attack,
)
from backend.injectors.performance_monkey import (
    bias_amplification_probe,
    cost_chaos_scenarios,
    ethical_drift_sequence,
    parallel_load_test,
    resource_exhaustion_probe,
)
from backend.injectors.security_storm_monkey import (
    action_hijack_probes,
    data_exfil_probes,
    indirect_injection_probes,
    jailbreak_probes,
    prompt_injection_attacks,
)
from backend.injectors.tool_vortex_monkey import FAILURE_MODES, generate_vortex_scenarios, inject_tool_failure

__all__ = [
    "FAILURE_MODES",
    "inject_tool_failure",
    "generate_vortex_scenarios",
    "contradictory_instructions",
    "false_prior_injection",
    "context_window_poisoning",
    "reasoning_drift_trap",
    "hallucination_bait",
    "inject_history_corruption",
    "inject_false_memory",
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

