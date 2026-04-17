"""Streamlit page to launch chaos runs with SSE updates and HITL controls."""

from __future__ import annotations

import json
import time

import requests
import streamlit as st

from streamlit_app.components.api_client import (
    approve_turn,
    create_run,
    get_live_state,
    reject_turn,
)
from streamlit_app.components.auth import get_headers, require_login
from streamlit_app.config import BACKEND_URL

st.set_page_config(page_title="ChaosAgent - Run Chaos", layout="wide")
require_login()

st.title("3. Run Chaos")

if not st.session_state.get("connected_agent_id"):
    st.warning("Connect an agent first on page 1.")
    st.stop()

# ── Experiment config ─────────────────────────────────────────────────────────

st.subheader("Configure Experiment")

monkeys = st.multiselect(
    "Monkeys",
    [
        "cti",
        "tool_vortex",
        "memory_entropy",
        "security_storm",
        "autonomy_probe",
        "inter_agent",
        "performance",
    ],
    default=["cti"],
)

col1, col2 = st.columns(2)
with col1:
    intensity = st.slider("Intensity", min_value=1, max_value=5, value=2)
with col2:
    blast = st.radio("Blast radius", ["canary", "staging", "dev"], index=0)

hypothesis = st.text_input(
    "Hypothesis",
    placeholder="e.g. Agent will reflect all injected content without resistance",
)

# ── SSE streaming ─────────────────────────────────────────────────────────────

def _stream_events(run_id: str, max_retries: int = 5) -> None:
    """Stream SSE events from the backend with automatic reconnect."""
    retries = 0
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    while retries < max_retries:
        session = requests.Session()
        try:
            session.headers.update(get_headers())
            resp = session.get(
                f"{BACKEND_URL}/runs/{run_id}/stream",
                stream=True,
                timeout=None,
            )
            resp.raise_for_status()

            # Parse SSE manually — most reliable across sseclient-py versions
            event_type = "message"
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    event_type = "message"  # blank line = event boundary, reset
                    continue

                if raw_line.startswith("event:"):
                    event_type = raw_line[6:].strip()
                    continue

                if not raw_line.startswith("data:"):
                    continue

                raw_data = raw_line[5:].strip()
                if not raw_data or raw_data == "{}":
                    continue

                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                # ── Handle each event type ────────────────────────────────────

                if event_type == "heartbeat":
                    retries = 0  # connection alive, reset retry counter
                    continue

                elif event_type == "progress":
                    retries = 0
                    turn = data.get("turn", 0)
                    monkey = data.get("monkey_type", "")
                    srq = data.get("running_srq", 0.0)
                    run_status = data.get("status", "running")
                    with progress_placeholder.container():
                        st.markdown(
                            f"**Turn {turn}** — monkey: `{monkey}` "
                            f"— running SRQ: `{srq:.2f}` "
                            f"— status: `{run_status}`"
                        )

                elif event_type == "hitl_required":
                    turn = data.get("turn", 0)
                    safety = data.get("safety_score", "?")
                    severity = data.get("severity", "?")
                    agent_resp = str(data.get("agent_response", ""))[:600]
                    status_placeholder.error(
                        f"🚨 **HITL Required**\n\n"
                        f"Safety score: `{safety}` | Severity: `{severity}`\n\n"
                        f"**Agent response:**\n{agent_resp}",
                    )
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Approve & Continue", key=f"approve_{turn}"):
                        try:
                            approve_turn(run_id)
                            st.success("Approved — run resuming.")
                        except Exception as e:
                            st.error(f"Approve failed: {e}")
                    if c2.button("❌ Reject & Skip", key=f"reject_{turn}"):
                        try:
                            reject_turn(run_id)
                            st.warning("Rejected — turn skipped.")
                        except Exception as e:
                            st.error(f"Reject failed: {e}")

                elif event_type == "complete":
                    progress_placeholder.empty()
                    st.success("✅ Run complete!")
                    summary = data.get("summary", {})
                    if summary:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Overall SRQ", f"{summary.get('overall_srq', 0):.2f}")
                        c2.metric("Overall HRT", f"{summary.get('overall_hrt', 0):.2f}")
                        c3.metric("AFPs Found", summary.get("afp_count", 0))
                        st.json(summary)
                    st.session_state.last_run_score = summary.get("overall_srq", 0.0)
                    return  # clean exit

                elif event_type == "error":
                    st.error(f"❌ Run failed: {data.get('error', 'unknown error')}")
                    return

                # Periodic live-state sync for dashboard
                try:
                    get_live_state(run_id)
                except Exception:
                    pass

            # iter_lines exited without complete/error — stream ended early
            raise RuntimeError("Stream ended without a complete or error event")

        except Exception as exc:
            retries += 1
            if retries >= max_retries:
                st.error(f"Stream failed after {max_retries} retries. Last error: {exc}")
                return
            st.warning(
                f"Stream dropped ({exc}) — reconnecting in 2s... "
                f"({retries}/{max_retries})"
            )
            time.sleep(2)

        finally:
            session.close()


# ── Launch button ─────────────────────────────────────────────────────────────

if st.button("🚀 Launch Experiment", type="primary", disabled=not monkeys):
    if not hypothesis.strip():
        st.warning("Add a hypothesis before launching.")
        st.stop()

    with st.spinner("Starting run..."):
        try:
            run = create_run(
                {
                    "agent_id": st.session_state.connected_agent_id,
                    "monkeys_selected": monkeys,
                    "intensity": intensity,
                    "blast_radius": blast,
                    "hypothesis": hypothesis,
                }
            )
        except Exception as e:
            st.error(f"Failed to create run: {e}")
            st.stop()

    run_id = run["run_id"]
    st.session_state.active_run_id = run_id
    st.info(f"Run ID: `{run_id}` — streaming events...")

    # Small delay so graph writes its first checkpoint before we connect
    time.sleep(0.5)

    _stream_events(run_id)


# ── Reconnect to existing run ─────────────────────────────────────────────────

if st.session_state.get("active_run_id"):
    st.divider()
    run_id = st.session_state.active_run_id
    st.write(f"Previous run: `{run_id}`")
    if st.button("↩️ Reconnect to existing run stream"):
        _stream_events(run_id)