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


def get_live_state(run_id: str) -> dict:
    """Fetch live orchestrator state snapshot for an active run."""
    response = requests.get(f"{BACKEND_URL}/runs/{run_id}/live-state", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def approve_turn(run_id: str) -> dict:
    """Approve a paused HITL turn and resume the graph."""
    response = requests.post(f"{BACKEND_URL}/runs/{run_id}/approve", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def reject_turn(run_id: str) -> dict:
    """Reject a paused HITL turn and resume the graph (skip)."""
    response = requests.post(f"{BACKEND_URL}/runs/{run_id}/reject", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def finetune_stats() -> dict:
    """Get OpenPipe fine-tune dataset stats."""
    response = requests.get(f"{BACKEND_URL}/finetune/stats", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def finetune_trigger() -> dict:
    """Trigger OpenPipe fine-tune job."""
    response = requests.post(f"{BACKEND_URL}/finetune/trigger", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def finetune_status(job_id: str) -> dict:
    """Poll OpenPipe fine-tune status."""
    response = requests.get(f"{BACKEND_URL}/finetune/status/{job_id}", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def finetune_activate(model_id: str) -> dict:
    """Activate a specific fine-tuned model."""
    response = requests.post(f"{BACKEND_URL}/finetune/activate/{model_id}", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()

