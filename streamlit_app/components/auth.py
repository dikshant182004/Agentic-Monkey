"""Auth helpers for Streamlit frontend session handling."""

from jose import jwt
import streamlit as st

from streamlit_app.config import BACKEND_URL


def require_login() -> None:
    """Require token in query params or session state and stop page otherwise."""
    token = st.query_params.get("token")
    if "jwt_token" not in st.session_state:
        st.session_state.jwt_token = ""
    if token:
        st.session_state.jwt_token = token
        st.query_params.clear()
    if not st.session_state.jwt_token:
        st.title("ChaosAgent Login")
        st.link_button("Login with Google", f"{BACKEND_URL}/auth/google")
        st.stop()
    try:
        jwt.get_unverified_claims(st.session_state.jwt_token)
    except Exception:
        st.session_state.jwt_token = ""
        st.error("Session token invalid. Please login again.")
        st.stop()


def get_headers() -> dict[str, str]:
    """Return auth headers for backend API calls."""
    return {"Authorization": f"Bearer {st.session_state.jwt_token}"}

