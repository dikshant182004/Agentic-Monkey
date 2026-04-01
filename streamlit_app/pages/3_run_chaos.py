"""Streamlit page to launch chaos runs with SSE updates and HITL controls."""

import json
import requests
import streamlit as st
from sseclient import SSEClient

from streamlit_app.components.api_client import create_run
from streamlit_app.components.auth import get_headers, require_login
from streamlit_app.config import BACKEND_URL

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
        stream = SSEClient(f"{BACKEND_URL}/runs/{run_id}/stream", headers=get_headers())
        for event in stream:
            if event.event == "heartbeat":
                continue
            data = json.loads(event.data)
            if event.event == "hitl_required":
                st.error(f"HITL required: {data.get('agent_response', '')}")
                c1, c2 = st.columns(2)
                if c1.button("Approve & Continue"):
                    requests.post(f"{BACKEND_URL}/runs/{run_id}/approve", headers=get_headers(), timeout=30)
                if c2.button("Reject & Skip"):
                    requests.post(f"{BACKEND_URL}/runs/{run_id}/reject", headers=get_headers(), timeout=30)
            elif event.event == "progress":
                st.write(data)
            elif event.event == "complete":
                st.success("Run complete")
                st.write(data)
                break
