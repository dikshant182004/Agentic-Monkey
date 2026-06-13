"""Centralized HTTP client functions for Streamlit to backend calls."""

from __future__ import annotations

import requests

from streamlit_app.components.auth import get_headers
from streamlit_app.config import BACKEND_URL


# ── Agent ──────────────────────────────────────────────────────────────────────

def create_agent(card_content: str) -> dict:
    """Create agent from card content through backend API."""
    response = requests.post(
        f"{BACKEND_URL}/agents",
        headers=get_headers(),
        json={"card_content": card_content},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# ── Steady-state ───────────────────────────────────────────────────────────────

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


# ── Runs ───────────────────────────────────────────────────────────────────────

def create_run(payload: dict) -> dict:
    """Start chaos run and return run id payload."""
    response = requests.post(
        f"{BACKEND_URL}/runs",
        headers=get_headers(),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_runs() -> list[dict]:
    """Return all runs for the current user (reverse-chronological).

    BUG-11 addition — needed by the dashboard run selector.
    """
    response = requests.get(f"{BACKEND_URL}/runs", headers=get_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def get_run_details(run_id: str) -> dict:
    """Fetch full run record including all aggregate metrics.

    BUG-11 addition — needed by the dashboard KPI cards.
    """
    response = requests.get(
        f"{BACKEND_URL}/runs/{run_id}",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_interactions(run_id: str) -> list[dict]:
    """Fetch per-turn interaction data for a run.

    BUG-11 addition — needed by SRQ-over-time and score-trend charts.
    """
    response = requests.get(
        f"{BACKEND_URL}/runs/{run_id}/interactions",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_afps(run_id: str) -> list[dict]:
    """Fetch AFP discoveries for a run.

    BUG-11 addition — needed by the AFP heatmap on the dashboard.
    """
    response = requests.get(
        f"{BACKEND_URL}/runs/{run_id}/afps",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# ── Live run helpers ───────────────────────────────────────────────────────────

def get_live_state(run_id: str) -> dict:
    """Fetch live orchestrator state snapshot for an active run."""
    response = requests.get(
        f"{BACKEND_URL}/runs/{run_id}/live-state",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def approve_turn(run_id: str) -> dict:
    """Approve a paused HITL turn and resume the graph."""
    response = requests.post(
        f"{BACKEND_URL}/runs/{run_id}/approve",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def reject_turn(run_id: str) -> dict:
    """Reject a paused HITL turn and resume the graph (skip)."""
    response = requests.post(
        f"{BACKEND_URL}/runs/{run_id}/reject",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()