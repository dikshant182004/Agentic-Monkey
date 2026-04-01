"""Streamlit app entrypoint for shared session state and sidebar."""

import streamlit as st

from streamlit_app.components.auth import require_login

for key, default in {
    "jwt_token": "",
    "connected_agent_id": "",
    "connected_agent_name": "",
    "last_run_score": 0.0,
    "openpipe_model_status": "unknown",
    "redis_connected": False,
    "active_run_id": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

require_login()
st.set_page_config(page_title="ChaosAgent", layout="wide")
st.sidebar.title("ChaosAgent")
st.sidebar.write(f"Connected agent: {st.session_state.connected_agent_name or 'None'}")
st.sidebar.write(f"Last run score: {st.session_state.last_run_score}")
st.sidebar.write(f"OpenPipe model: {st.session_state.openpipe_model_status}")
st.sidebar.write(f"Redis: {'online' if st.session_state.redis_connected else 'offline'}")
st.title("ChaosAgent")
st.write("Use the pages in the left sidebar to connect an agent and run chaos experiments.")

