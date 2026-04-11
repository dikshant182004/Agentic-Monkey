"""Streamlit page for OpenPipe fine-tune operations."""

import streamlit as st
from streamlit_app.components.auth import require_login
from streamlit_app.components.api_client import finetune_stats, finetune_trigger

st.set_page_config(page_title="ChaosAgent - Fine-tune", layout="wide")
require_login()

st.title("5. Fine-tune")
st.write("Manage OpenPipe fine-tune jobs.")
if st.button("Fetch stats"):
    stats = finetune_stats()
    st.json(stats)
if st.button("Trigger fine-tune"):
    resp = finetune_trigger()
    st.json(resp)