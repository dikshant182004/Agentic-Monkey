"""Streamlit frontend configuration loaded from secrets."""

from __future__ import annotations

import streamlit as st


def get_backend_url() -> str:
    """Return backend URL from Streamlit secrets with localhost default."""
    return str(st.secrets.get("BACKEND_URL", "http://localhost:8000"))


BACKEND_URL = get_backend_url()

