"""Auth helpers using Streamlit native OIDC (st.login / st.user)."""

from __future__ import annotations

import streamlit as st


def require_login() -> None:
    """Ensure user is logged in via Streamlit OIDC or stop the page."""
    if not getattr(st, "user", None) or not getattr(st.user, "is_logged_in", False):
        st.title("ChaosAgent Login")
        if st.button("Log in with Google"):
            st.login()
        st.stop()


def get_headers() -> dict[str, str]:
    """Return backend auth headers using exposed OIDC ID token."""
    token = ""
    try:
        token = st.user.tokens["id"]
    except Exception:
        token = ""
    return {"Authorization": f"Bearer {token}"} if token else {}

