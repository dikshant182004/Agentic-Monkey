"""Streamlit dashboard page for run analytics."""

import streamlit as st

from streamlit_app.components.auth import require_login
from streamlit_app.components.charts import score_radar, srq_over_time

require_login()
st.title("4. Dashboard")
st.subheader("Agentic Resilience")
st.metric("Last run score", st.session_state.last_run_score)
st.plotly_chart(srq_over_time([6.2, 6.8, 7.1, 7.4]), use_container_width=True)
st.plotly_chart(score_radar({"cognitive": 7.2, "tool": 6.8, "memory": 6.5, "security": 7.0, "autonomy": 6.6, "inter_agent": 6.2, "performance": 6.9}), use_container_width=True)
