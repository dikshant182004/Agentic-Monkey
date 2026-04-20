"""Streamlit page to launch chaos runs with SSE updates and HITL controls.

Fixes applied
─────────────
HITL duplicate-key crash: when the SSE stream dropped and reconnected, the
  hitl_required event fired again for the same turn. Each reconnect rendered
  st.button(..., key=f"approve_{turn}") with turn=0 — the same key appeared
  twice in the Streamlit tree, throwing a DuplicateWidgetID error which itself
  caused another stream drop, creating an infinite retry loop.

Fix:
  1. HITL state (payload + decision) is stored in st.session_state, NOT rendered
     inline inside the SSE while-loop. The loop just saves the payload and breaks.
  2. HITL controls are rendered AFTER the loop in a dedicated block, using a key
     that includes run_id + turn + a session counter so it is always unique across
     reconnects.
  3. After approve/reject the HITL state is cleared and the stream reconnects.
"""

from __future__ import annotations

import json
import time
import uuid

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

# ── Session state initialisation ───────────────────────────────────────────────

for key, default in {
    "active_run_id": "",
    "hitl_payload": None,       # dict when HITL is pending, None otherwise
    "hitl_counter": 0,          # incremented each time HITL fires → unique widget keys
    "run_complete": False,
    "run_summary": None,
    "run_error": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Experiment config ──────────────────────────────────────────────────────────

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

# ── HITL controls (rendered OUTSIDE the stream loop) ──────────────────────────
# Rendered here so they exist exactly once in the Streamlit tree, regardless of
# how many times the SSE stream has reconnected.

hitl_payload = st.session_state.get("hitl_payload")
if hitl_payload and st.session_state.get("active_run_id"):
    run_id = st.session_state.active_run_id
    turn = hitl_payload.get("turn", 0)
    safety = hitl_payload.get("safety_score", "?")
    severity = hitl_payload.get("severity", "?")
    agent_resp = str(hitl_payload.get("agent_response", ""))[:600]
    counter = st.session_state.hitl_counter  # unique per HITL event

    st.error(
        f"🚨 **HITL Required**\n\n"
        f"Safety score: `{safety}` | Severity: `{severity}`\n\n"
        f"**Agent response:**\n{agent_resp}"
    )

    c1, c2 = st.columns(2)
    # Keys include run_id slice + counter so they are globally unique even after
    # reconnects or multiple HITL events in the same run.
    approve_key = f"approve_{run_id[:8]}_{counter}"
    reject_key  = f"reject_{run_id[:8]}_{counter}"

    if c1.button("✅ Approve & Continue", key=approve_key):
        try:
            approve_turn(run_id)
            st.success("Approved — run resuming.")
        except Exception as e:
            st.error(f"Approve failed: {e}")
        # Clear HITL state so the buttons disappear and stream resumes
        st.session_state.hitl_payload = None
        st.session_state.hitl_counter += 1
        st.rerun()

    if c2.button("❌ Reject & Skip", key=reject_key):
        try:
            reject_turn(run_id)
            st.warning("Rejected — turn skipped.")
        except Exception as e:
            st.error(f"Reject failed: {e}")
        st.session_state.hitl_payload = None
        st.session_state.hitl_counter += 1
        st.rerun()

# ── Run complete / error banners ───────────────────────────────────────────────

if st.session_state.get("run_complete") and st.session_state.get("run_summary"):
    summary = st.session_state.run_summary
    st.success("✅ Run complete!")
    c1, c2, c3 = st.columns(3)
    c1.metric("Overall SRQ", f"{summary.get('overall_srq', 0):.2f}")
    c2.metric("Overall HRT", f"{summary.get('overall_hrt', 0):.2f}")
    c3.metric("AFPs Found", summary.get("afp_count", 0))
    st.json(summary)

if st.session_state.get("run_error"):
    st.error(f"❌ Run failed: {st.session_state.run_error}")

# ── SSE streaming ──────────────────────────────────────────────────────────────

def _stream_events(run_id: str, max_retries: int = 5) -> None:
    """Stream SSE events from the backend.

    HITL events do NOT render buttons inline. Instead they save the payload
    to st.session_state.hitl_payload and return immediately so Streamlit
    re-renders the page — the HITL controls above pick up the payload and
    render exactly once with a unique key.
    """
    retries = 0
    progress_placeholder = st.empty()

    while retries < max_retries:
        # If HITL is pending, stop streaming — wait for operator decision.
        if st.session_state.get("hitl_payload"):
            return

        session = requests.Session()
        try:
            session.headers.update(get_headers())
            resp = session.get(
                f"{BACKEND_URL}/runs/{run_id}/stream",
                stream=True,
                timeout=None,
            )
            resp.raise_for_status()

            event_type = "message"
            for raw_line in resp.iter_lines(decode_unicode=True):
                # If HITL became pending mid-stream, stop reading
                if st.session_state.get("hitl_payload"):
                    return

                if not raw_line:
                    event_type = "message"
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

                if event_type == "heartbeat":
                    retries = 0
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
                    # Save to session state and return — buttons rendered above.
                    st.session_state.hitl_payload = {
                        "turn":           data.get("turn", 0),
                        "safety_score":   data.get("safety_score", "?"),
                        "severity":       data.get("severity", "?"),
                        "agent_response": data.get("agent_response", ""),
                        "interaction_id": data.get("interaction_id", ""),
                    }
                    st.session_state.hitl_counter += 1
                    progress_placeholder.empty()
                    st.rerun()
                    return  # rerun() raises internally but return is belt-and-suspenders

                elif event_type == "complete":
                    progress_placeholder.empty()
                    summary = data.get("summary", {})
                    st.session_state.run_complete = True
                    st.session_state.run_summary = summary
                    st.session_state.last_run_score = summary.get("overall_srq", 0.0)
                    st.rerun()
                    return

                elif event_type == "error":
                    st.session_state.run_error = data.get("error", "unknown error")
                    st.rerun()
                    return

                # Periodic live-state sync (best-effort)
                try:
                    get_live_state(run_id)
                except Exception:
                    pass

            raise RuntimeError("Stream ended without a complete or error event")

        except Exception as exc:
            retries += 1
            if retries >= max_retries:
                st.error(
                    f"Stream failed after {max_retries} retries. Last error: {exc}"
                )
                return
            st.warning(
                f"Stream dropped ({exc}) — reconnecting in 2s... "
                f"({retries}/{max_retries})"
            )
            time.sleep(2)

        finally:
            session.close()


# ── Launch button ──────────────────────────────────────────────────────────────

if st.button("🚀 Launch Experiment", type="primary", disabled=not monkeys):
    if not hypothesis.strip():
        st.warning("Add a hypothesis before launching.")
        st.stop()

    # Reset run state
    st.session_state.run_complete = False
    st.session_state.run_summary = None
    st.session_state.run_error = None
    st.session_state.hitl_payload = None

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

    time.sleep(0.5)
    _stream_events(run_id)


# ── Reconnect to existing run ──────────────────────────────────────────────────

if st.session_state.get("active_run_id") and not st.session_state.get("hitl_payload"):
    st.divider()
    run_id = st.session_state.active_run_id
    st.write(f"Previous run: `{run_id}`")
    if st.button("↩️ Reconnect to existing run stream"):
        st.session_state.run_complete = False
        st.session_state.run_error = None
        _stream_events(run_id)