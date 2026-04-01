"""Streamlit page for uploading and validating target Agent Card."""

import streamlit as st

from streamlit_app.components.api_client import create_agent
from streamlit_app.components.auth import require_login

require_login()
st.title("1. Connect Agent")
card_file = st.file_uploader("Upload Agent Card", type=["json", "yaml", "txt"])
raw_text = st.text_area("Or paste raw card JSON/YAML/URL")
content = raw_text
if card_file is not None:
    content = card_file.getvalue().decode("utf-8")
if st.button("Connect Agent") and content:
    data = create_agent(content)
    st.session_state.connected_agent_id = data["id"]
    st.session_state.connected_agent_name = data["name"]
    st.success("Agent connected")
    st.json(data)
