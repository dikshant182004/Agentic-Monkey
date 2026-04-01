"""Centralized HTTP client functions for Streamlit to backend calls."""

from __future__ import annotations

import requests

from streamlit_app.components.auth import get_headers
from streamlit_app.config import BACKEND_URL


def create_agent(card_content: str) -> dict:
    """Create agent from card content through backend API."""
    response = requests.post(f"{BACKEND_URL}/agents", headers=get_headers(), json={"card_content": card_content}, timeout=30)
    response.raise_for_status()
    return response.json()


def run_steady_state(agent_id: str, sample_size: int) -> dict:
    """Run steady-state baseline and return metrics payload."""
    response = requests.post(
        f"{BACKEND_URL}/steady-state/run/{agent_id}",
        headers=get_headers(),
        json={"sample_size": sample_size},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def create_run(payload: dict) -> dict:
    """Start chaos run and return run id payload."""
    response = requests.post(f"{BACKEND_URL}/runs", headers=get_headers(), json=payload, timeout=30)
    response.raise_for_status()
    return response.json()

