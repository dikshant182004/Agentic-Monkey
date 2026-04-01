"""Streamlit page for OpenPipe fine-tune operations."""

import requests
import streamlit as st

from streamlit_app.components.auth import get_headers, require_login
from streamlit_app.config import BACKEND_URL

require_login()
st.title("5. Fine-tune")
st.write("Manage OpenPipe fine-tune jobs.")
if st.button("Fetch stats"):
    stats = requests.get(f"{BACKEND_URL}/finetune/stats", headers=get_headers(), timeout=30).json()
    st.json(stats)
if st.button("Trigger fine-tune"):
    resp = requests.post(f"{BACKEND_URL}/finetune/trigger", headers=get_headers(), timeout=30).json()
    st.json(resp)
