"""
Streamlit page for chaos experiment configuration and streaming — v2.

New in v2:
  - Auto-plan mode: fetch plan from GET /runs/plan, show it to user,
    user can accept or override before launching.
  - New monkey types shown in multiselect.
  - HITL panel shows attack angle and ATLAS technique for context.
  - Refinement budget shown in run status.
"""

from __future__ import annotations

import json
import time

import requests
import streamlit as st

from streamlit_app.components.api_client import (
    approve_turn,
    create_run,
    get_live_state,
    reject_turn,
)
from streamlit_app.components.auth import get_headers, require_login
from streamlit_app.config import BACKEND_URL

st.set_page_config(page_title="ChaosAgent — Run Chaos", layout="wide")
require_login()

st.title("3. Run Chaos Experiment")

if not st.session_state.get("connected_agent_id"):
    st.warning("Connect an agent first on page 1.")
    st.stop()

# ── Session state ──────────────────────────────────────────────────────────────

for key, default in {
    "active_run_id": "",
    "hitl_payload": None,
    "hitl_counter": 0,
    "run_complete": False,
    "run_summary": None,
    "run_error": None,
    "auto_plan": None,          # cached plan from /runs/plan
    "use_auto_plan": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

ALL_MONKEYS = [
    "cti",
    "tool_vortex",
    "memory_entropy",
    "security_storm",
    "autonomy_probe",
    "inter_agent",
    "performance",
    "rag_poisoning",
    "supply_chain",
    "privilege_escalation",
]

MONKEY_LABELS = {
    "cti":                  "CTI — Cognitive Turbulence (false priors, contradictions)",
    "tool_vortex":          "Tool Vortex (timeouts, malformed responses, chain attacks)",
    "memory_entropy":       "Memory Entropy (context corruption, history poisoning)",
    "security_storm":       "Security Storm (injection, jailbreak, exfil)",
    "autonomy_probe":       "Autonomy Probe (HITL bypass, irreversible action pressure)",
    "inter_agent":          "Inter-Agent (fake orchestrators, peer impersonation)",
    "performance":          "Performance (ethical drift, cost abuse, load pressure)",
    "rag_poisoning":        "RAG Poisoning (retrieval injection, document trust abuse) ★ NEW",
    "supply_chain":         "Supply Chain (rogue tools, MCP poisoning, dependency attacks) ★ NEW",
    "privilege_escalation": "Privilege Escalation (role claims, permission bleeding) ★ NEW",
}

# ── Auto-plan section ─────────────────────────────────────────────────────────

st.subheader("Experiment Configuration")

col_mode1, col_mode2 = st.columns(2)
with col_mode1:
    use_auto = st.toggle(
        "🤖 Auto-plan from Agent Card",
        value=False,
        help="Let ChaosAgent analyse the agent's A2A card and recommend monkeys, intensity, and hypothesis.",
    )

if use_auto:
    if st.button("📋 Generate Plan", type="secondary"):
        with st.spinner("Analysing agent capabilities..."):
            try:
                resp = requests.get(
                    f"{BACKEND_URL}/runs/plan",
                    headers=get_headers(),
                    params={"agent_id": st.session_state.connected_agent_id},
                    timeout=30,
                )
                resp.raise_for_status()
                st.session_state.auto_plan = resp.json()
            except Exception as e:
                st.error(f"Plan generation failed: {e}")

    plan = st.session_state.auto_plan
    if plan:
        st.success("Auto-plan generated — review and launch or override below.")
        st.markdown(f"**Hypothesis:** {plan['hypothesis']}")
        st.markdown(f"**Blast radius:** `{plan['blast_radius']}` | **Intensity:** `{plan['intensity']}/5` | **Turns:** `{plan['total_turns']}`")
        if plan.get("plan_notes"):
            st.caption(f"ℹ️ {plan['plan_notes']}")

        with st.expander("Monkey priority ranking"):
            for r in plan.get("monkey_rankings", []):
                st.markdown(
                    f"**{r['monkey_type']}** (score: {r['priority_score']:.2f}) — {r['reason']}"
                )

        monkeys = plan["monkeys_selected"]
        intensity = plan["intensity"]
        blast = plan["blast_radius"]
        hypothesis = plan["hypothesis"]
        st.session_state.use_auto_plan = True
    else:
        st.info("Click 'Generate Plan' to analyse the agent card.")
        monkeys = []
        intensity = 2
        blast = "canary"
        hypothesis = ""
        st.session_state.use_auto_plan = False
else:
    st.session_state.auto_plan = None
    st.session_state.use_auto_plan = False
    monkeys = []
    intensity = 2
    blast = "canary"
    hypothesis = ""

# ── Manual override / standalone config ───────────────────────────────────────

st.divider()
st.markdown("**Override or configure manually:**")

monkeys = st.multiselect(
    "Monkey types",
    options=ALL_MONKEYS,
    format_func=lambda m: MONKEY_LABELS.get(m, m),
    default=monkeys or ["cti"],
)

col1, col2 = st.columns(2)
with col1:
    intensity = st.slider("Intensity", min_value=1, max_value=5, value=intensity,
                          help="1=subtle, 3=moderate, 5=maximum pressure")
with col2:
    blast = st.radio(
        "Blast radius",
        ["canary", "staging", "dev"],
        index=["canary", "staging", "dev"].index(blast),
        help="canary=safe/few turns, staging=moderate, dev=full test",
    )

hypothesis = st.text_input(
    "Hypothesis",
    value=hypothesis,
    placeholder="e.g. Agent will accept false authority claims under CTI attack",
)

# Refinement budget preview
budget_map = {"canary": 0, "staging": 3, "dev": 8}
budget = budget_map.get(blast, 3)
st.caption(
    f"Refinement budget: **{budget}** retries available for this blast radius "
    f"(only used at intensity ≥ 3 when agent resists)."
)

# ── HITL controls ─────────────────────────────────────────────────────────────

hitl_payload = st.session_state.get("hitl_payload")
if hitl_payload and st.session_state.get("active_run_id"):
    run_id = st.session_state.active_run_id
    counter = st.session_state.hitl_counter

    st.error(
        f"🚨 **Human Review Required**\n\n"
        f"Safety score: `{hitl_payload.get('safety_score', '?')}` | "
        f"Severity: `{hitl_payload.get('severity', '?')}`\n\n"
        f"**Technique:** `{hitl_payload.get('atlas_id', 'unknown')}` | "
        f"**Angle:** `{hitl_payload.get('attack_angle', 'unknown')}`\n\n"
        f"**Agent response:**\n{str(hitl_payload.get('agent_response', ''))[:600]}"
    )

    c1, c2 = st.columns(2)
    if c1.button("✅ Approve & Continue", key=f"approve_{run_id[:8]}_{counter}"):
        try:
            approve_turn(run_id)
            st.success("Approved — run resuming.")
        except Exception as e:
            st.error(f"Approve failed: {e}")
        st.session_state.hitl_payload = None
        st.session_state.hitl_counter += 1
        st.rerun()

    if c2.button("❌ Reject & Skip", key=f"reject_{run_id[:8]}_{counter}"):
        try:
            reject_turn(run_id)
            st.warning("Rejected — turn skipped.")
        except Exception as e:
            st.error(f"Reject failed: {e}")
        st.session_state.hitl_payload = None
        st.session_state.hitl_counter += 1
        st.rerun()

# ── Run complete / error banners ───────────────────────────────────────────────

if st.session_state.get("run_complete") and st.session_state.get("run_summary"):
    summary = st.session_state.run_summary
    st.success("✅ Experiment complete!")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall SRQ", f"{summary.get('overall_srq', 0):.2f}")
    c2.metric("Overall HRT", f"{summary.get('overall_hrt', 0):.2f}")
    c3.metric("AFPs Found", summary.get("afp_count", 0))
    c4.metric("Refinements Used", summary.get("refinement_used", 0))
    with st.expander("Full report"):
        st.json(summary)

if st.session_state.get("run_error"):
    st.error(f"❌ Run failed: {st.session_state.run_error}")


# ── SSE streaming ─────────────────────────────────────────────────────────────

def _stream_events(run_id: str, max_retries: int = 5) -> None:
    retries = 0
    progress_placeholder = st.empty()

    while retries < max_retries:
        if st.session_state.get("hitl_payload"):
            return

        session = requests.Session()
        try:
            session.headers.update(get_headers())
            resp = session.get(
                f"{BACKEND_URL}/runs/{run_id}/stream",
                stream=True,
                timeout=None,
            )
            resp.raise_for_status()

            event_type = "message"
            for raw_line in resp.iter_lines(decode_unicode=True):
                if st.session_state.get("hitl_payload"):
                    return

                if not raw_line:
                    event_type = "message"
                    continue
                if raw_line.startswith("event:"):
                    event_type = raw_line[6:].strip()
                    continue
                if not raw_line.startswith("data:"):
                    continue

                raw_data = raw_line[5:].strip()
                if not raw_data or raw_data == "{}":
                    continue

                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                if event_type == "heartbeat":
                    retries = 0
                    continue

                elif event_type == "progress":
                    retries = 0
                    turn = data.get("turn", 0)
                    monkey = data.get("monkey_type", "")
                    srq = data.get("running_srq", 0.0)
                    angle = data.get("attack_angle", "")
                    with progress_placeholder.container():
                        st.markdown(
                            f"**Turn {turn}** | monkey: `{monkey}` | "
                            f"running SRQ: `{srq:.2f}`"
                            + (f" | angle: `{angle}`" if angle else "")
                        )

                elif event_type == "hitl_required":
                    st.session_state.hitl_payload = {
                        "turn":           data.get("turn", 0),
                        "safety_score":   data.get("safety_score", "?"),
                        "severity":       data.get("severity", "?"),
                        "agent_response": data.get("agent_response", ""),
                        "interaction_id": data.get("interaction_id", ""),
                        "atlas_id":       data.get("atlas_id", ""),
                        "attack_angle":   data.get("attack_angle", ""),
                    }
                    st.session_state.hitl_counter += 1
                    progress_placeholder.empty()
                    st.rerun()
                    return

                elif event_type == "complete":
                    progress_placeholder.empty()
                    summary = data.get("summary", {})
                    st.session_state.run_complete = True
                    st.session_state.run_summary = summary
                    st.session_state.last_run_score = summary.get("overall_srq", 0.0)
                    st.rerun()
                    return

                elif event_type == "error":
                    st.session_state.run_error = data.get("error", "unknown error")
                    st.rerun()
                    return

            raise RuntimeError("Stream ended without complete or error event")

        except Exception as exc:
            retries += 1
            if retries >= max_retries:
                st.error(f"Stream failed after {max_retries} retries. Last error: {exc}")
                return
            st.warning(f"Stream dropped ({exc}) — reconnecting in 2s... ({retries}/{max_retries})")
            time.sleep(2)

        finally:
            session.close()


# ── Launch button ─────────────────────────────────────────────────────────────

launch_disabled = not monkeys
if st.button("🚀 Launch Experiment", type="primary", disabled=launch_disabled):
    if not hypothesis.strip():
        st.warning("Please add a hypothesis before launching.")
        st.stop()

    st.session_state.run_complete = False
    st.session_state.run_summary = None
    st.session_state.run_error = None
    st.session_state.hitl_payload = None

    with st.spinner("Starting run..."):
        try:
            run = create_run({
                "agent_id": st.session_state.connected_agent_id,
                "monkeys_selected": monkeys,
                "intensity": intensity,
                "blast_radius": blast,
                "hypothesis": hypothesis,
                "auto_plan": False,  # manual config always uses explicit monkeys
            })
        except Exception as e:
            st.error(f"Failed to create run: {e}")
            st.stop()

    run_id = run["run_id"]
    st.session_state.active_run_id = run_id
    st.info(
        f"Run ID: `{run_id}` | "
        f"Refinement budget: `{run.get('refinement_budget', 0)}`"
    )

    time.sleep(0.5)
    _stream_events(run_id)


# ── Auto-plan launch ──────────────────────────────────────────────────────────

if use_auto and st.session_state.auto_plan and st.button("🤖 Launch Auto-Planned Experiment", type="primary"):
    st.session_state.run_complete = False
    st.session_state.run_summary = None
    st.session_state.run_error = None
    st.session_state.hitl_payload = None

    with st.spinner("Launching auto-planned experiment..."):
        try:
            run = create_run({
                "agent_id": st.session_state.connected_agent_id,
                "monkeys_selected": [],   # empty → auto_plan derives it
                "intensity": intensity,   # may be user-overridden
                "blast_radius": blast,
                "hypothesis": hypothesis,
                "auto_plan": True,
            })
        except Exception as e:
            st.error(f"Failed to create run: {e}")
            st.stop()

    run_id = run["run_id"]
    st.session_state.active_run_id = run_id
    st.info(f"Auto-planned run: `{run_id}`")

    time.sleep(0.5)
    _stream_events(run_id)


# ── Reconnect ─────────────────────────────────────────────────────────────────

if st.session_state.get("active_run_id") and not st.session_state.get("hitl_payload"):
    st.divider()
    run_id = st.session_state.active_run_id
    st.caption(f"Previous run: `{run_id}`")
    if st.button("↩️ Reconnect to run stream"):
        st.session_state.run_complete = False
        st.session_state.run_error = None
        _stream_events(run_id)