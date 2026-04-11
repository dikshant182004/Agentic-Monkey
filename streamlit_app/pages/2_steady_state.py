"""Streamlit page for steady-state baseline execution."""

import streamlit as st
from streamlit_app.components.api_client import run_steady_state
from streamlit_app.components.auth import require_login

st.set_page_config(page_title="ChaosAgent - Steady State", layout="wide")
require_login()

st.title("2. Steady State")
if not st.session_state.get("connected_agent_id"):
    st.warning("Connect an agent first on page 1.")
    st.stop()
sample_size = st.slider("Baseline task count", min_value=10, max_value=100, value=20)
if st.button("Run baseline"):
    with st.spinner("Running baseline..."):
        result = run_steady_state(st.session_state.connected_agent_id, sample_size)
    st.success("Baseline captured")
    st.table(result)