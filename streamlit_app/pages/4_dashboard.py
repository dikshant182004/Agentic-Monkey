"""
Streamlit dashboard page — real data from the backend.

BUG-8 fix: the original page used hardcoded placeholder scores.
This version fetches live data from the backend API:
  - GET /runs             → run selector list
  - GET /runs/{id}        → KPI cards
  - GET /runs/{id}/interactions → trend charts + interaction table
  - GET /runs/{id}/afps   → AFP heatmap

Layout:
  1. Run selector (latest 20 runs)
  2. KPI row: SRQ · HRT · Safety · AFPs · Resilience score
  3. Trend chart: SRQ + HRT + Safety over turns
  4. Col A: Monkey score radar   |   Col B: AFP heatmap
  5. Interaction log table (collapsed)
"""

from __future__ import annotations

from collections import defaultdict

import streamlit as st

from streamlit_app.components.api_client import (
    get_run_details,
    list_afps,
    list_interactions,
    list_runs,
)
from streamlit_app.components.auth import require_login
from streamlit_app.components.charts import (
    afp_heatmap,
    multi_score_line,
    score_radar,
    srq_over_time,
)

st.set_page_config(page_title="ChaosAgent — Dashboard", layout="wide")
require_login()

st.title("4. Dashboard")

# ── 1. Run selector ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def _fetch_runs() -> list[dict]:
    try:
        return list_runs()
    except Exception as exc:
        st.warning(f"Could not load runs: {exc}")
        return []


runs_list = _fetch_runs()

if not runs_list:
    st.info("No runs found. Complete an experiment on the **3. Run Chaos** page first.")
    st.stop()

# Build display labels
run_options = {
    f"[{r['status'].upper()}] {r['id'][:8]}… — "
    f"SRQ {r['overall_srq']:.2f} | {r['blast_radius']} | "
    f"{r['started_at'][:10]}": r["id"]
    for r in runs_list[:20]
}

selected_label = st.selectbox(
    "Select run",
    options=list(run_options.keys()),
    help="Showing up to 20 most recent runs.",
)
run_id = run_options[selected_label]

# ── 2. Fetch run data ──────────────────────────────────────────────────────────

@st.cache_data(ttl=15, show_spinner=False)
def _fetch_run(rid: str) -> dict:
    return get_run_details(rid)


@st.cache_data(ttl=15, show_spinner=False)
def _fetch_interactions(rid: str) -> list[dict]:
    try:
        return list_interactions(rid)
    except Exception:
        return []


@st.cache_data(ttl=15, show_spinner=False)
def _fetch_afps(rid: str) -> list[dict]:
    try:
        return list_afps(rid)
    except Exception:
        return []


with st.spinner("Loading run data…"):
    run = _fetch_run(run_id)
    interactions = _fetch_interactions(run_id)
    afps = _fetch_afps(run_id)

# ── 3. KPI row ─────────────────────────────────────────────────────────────────

st.subheader("Run Summary")

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Status", run["status"].upper())
k2.metric("SRQ", f"{run['overall_srq']:.2f}")
k3.metric("HRT", f"{run['overall_hrt']:.2f}")
k4.metric("Safety", f"{run['overall_safety']:.2f}")
k5.metric("AFPs", run["afp_count"])
k6.metric("Resilience", f"{run['agentic_resilience_score']:.1f}")

meta_cols = st.columns(4)
meta_cols[0].caption(f"Blast radius: **{run['blast_radius']}**")
meta_cols[1].caption(f"Monkeys: **{', '.join(run.get('monkeys_selected', []))}**")
meta_cols[2].caption(f"Started: {run['started_at'][:19].replace('T', ' ')}")
finished = run.get("finished_at")
meta_cols[3].caption(f"Finished: {finished[:19].replace('T', ' ') if finished else 'in progress'}")

hypothesis = run.get("config", {}).get("hypothesis", "")
if hypothesis:
    st.caption(f"**Hypothesis:** {hypothesis}")

st.divider()

# ── 4. Trend charts ────────────────────────────────────────────────────────────

if not interactions:
    st.info("No interaction data yet — run is still in progress or has no turns.")
else:
    st.subheader("Score Trends")
    st.plotly_chart(multi_score_line(interactions), use_container_width=True)

    # ── 5. Radar + heatmap side by side ───────────────────────────────────────

    col_radar, col_heatmap = st.columns(2)

    with col_radar:
        # Average safety_score per monkey_type for the radar
        monkey_safety: dict[str, list[float]] = defaultdict(list)
        for ix in interactions:
            monkey_safety[ix["monkey_type"]].append(ix.get("safety_score", 0.0))

        radar_data = {
            mtype: round(sum(scores) / len(scores), 2)
            for mtype, scores in monkey_safety.items()
        }

        if radar_data:
            st.plotly_chart(score_radar(radar_data), use_container_width=True)
        else:
            st.info("Not enough data for radar chart.")

    with col_heatmap:
        if afps:
            st.plotly_chart(afp_heatmap(afps), use_container_width=True)
        else:
            st.success("✅ No AFPs found in this run.")

    st.divider()

    # ── 6. AFP list ────────────────────────────────────────────────────────────

    if afps:
        st.subheader(f"Autonomy Fracture Points ({len(afps)})")
        for a in afps:
            severity_icon = {"low": "🟡", "medium": "🟠", "high": "🔴", "critical": "🚨"}.get(
                a["severity"], "⚪"
            )
            with st.expander(
                f"{severity_icon} [{a['severity'].upper()}] {a['monkey_type']} — {a['description'][:80]}"
            ):
                st.markdown(f"**Description:** {a['description']}")
                st.markdown(f"**Recommendation:** {a['recommendation']}")

        st.divider()

    # ── 7. Interaction log ─────────────────────────────────────────────────────

    with st.expander(f"Interaction log ({len(interactions)} turns)"):
        table_rows = [
            {
                "Turn": i["turn"],
                "Monkey": i["monkey_type"],
                "SRQ": f"{i['srq_score']:.2f}",
                "HRT": f"{i['hrt_score']:.2f}",
                "Safety": f"{i['safety_score']:.2f}",
                "AFP": "⚠️" if i["is_afp"] else "✓",
                "HITL": "🔒" if i["hitl_required"] else "—",
                "Notes": i.get("notes", "")[:80],
            }
            for i in interactions
        ]
        st.dataframe(table_rows, use_container_width=True)

# ── 8. Refresh button ──────────────────────────────────────────────────────────

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()