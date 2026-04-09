"""Streamlit page to launch chaos runs with SSE updates and HITL controls."""

import json
import streamlit as st
from sseclient import SSEClient

from streamlit_app.components.api_client import create_run
from streamlit_app.components.auth import get_headers, require_login
from streamlit_app.config import BACKEND_URL
from streamlit_app.components.api_client import approve_turn, reject_turn, get_live_state

require_login()
st.title("3. Run Chaos")
if not st.session_state.connected_agent_id:
    st.warning("Connect an agent first.")
    st.stop()
monkeys = st.multiselect("Monkeys", ["cti", "tool_vortex", "memory_entropy", "security_storm", "autonomy_probe", "inter_agent", "performance"], default=["cti"])
intensity = st.slider("Intensity", 1, 5, 3)
blast = st.radio("Blast radius", ["dev", "staging", "canary"], index=1)
hypothesis = st.text_input("Hypothesis")
if st.button("Launch experiment"):
    run = create_run({"agent_id": st.session_state.connected_agent_id, "monkeys_selected": monkeys, "intensity": intensity, "blast_radius": blast, "hypothesis": hypothesis})
    st.session_state.active_run_id = run["run_id"]
    st.success(f"Run started: {run['run_id']}")

run_id = st.session_state.active_run_id
if run_id:
    if st.button("Start Stream"):
        live_state_cache: dict | None = None
        last_poll_ts = 0.0
        stream = SSEClient(f"{BACKEND_URL}/runs/{run_id}/stream", headers=get_headers())
        for event in stream:
            if event.event == "heartbeat":
                continue
            data = json.loads(event.data)
            if event.event == "hitl_required":
                st.error(
                    "HITL required. The agent response was flagged for potential unsafe or critical autonomy behavior.\n\n"
                    f"Reason: safety_score={data.get('safety_score')} severity={data.get('severity')}\n\n"
                    f"Agent response (truncated): {str(data.get('agent_response', ''))[:600]}",
                    icon="🚨",
                )
                c1, c2 = st.columns(2)
                if c1.button("Approve & Continue", key="hitl_approve"):
                    approve_turn(run_id)
                if c2.button("Reject & Skip", key="hitl_reject"):
                    reject_turn(run_id)
            elif event.event == "progress":
                live_state_cache = data
                st.write(
                    {
                        "turn": data.get("turn"),
                        "monkey_type": data.get("monkey_type"),
                        "running_srq": data.get("running_srq"),
                        "status": data.get("status"),
                    }
                )
            elif event.event == "complete":
                st.success("Run complete")
                st.write(data)
                break
            try:
                # Poll when enough wall time has passed since last poll.
                import time

                now = time.time()
                if now - last_poll_ts >= 2.0:
                    last_poll_ts = now
                    get_live_state(run_id)  # best-effort
            except Exception:
                # Don't break the SSE loop on polling failures.
                pass
