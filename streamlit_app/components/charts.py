"""Reusable Plotly chart builders for ChaosAgent Streamlit pages."""

import plotly.graph_objects as go


def srq_over_time(scores: list[float]) -> go.Figure:
    """Return line chart for SRQ progression over turns."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=scores, mode="lines+markers", name="SRQ"))
    fig.update_layout(title="SRQ Over Time", yaxis_title="SRQ")
    return fig


def score_radar(metrics: dict) -> go.Figure:
    """Return radar chart for pillar-wise score distribution."""
    labels = list(metrics.keys())
    values = list(metrics.values())
    fig = go.Figure(data=go.Scatterpolar(r=values + values[:1], theta=labels + labels[:1], fill="toself"))
    fig.update_layout(title="Pillar Score Radar", polar=dict(radialaxis=dict(visible=True, range=[0, 10])))
    return fig


def afp_heatmap(data: list[dict]) -> go.Figure:
    """Return heatmap figure for AFP counts by monkey and severity."""
    monkeys = sorted({item["monkey"] for item in data}) if data else ["none"]
    severities = ["low", "medium", "high", "critical"]
    matrix = [[0 for _ in monkeys] for _ in severities]
    for item in data:
        r = severities.index(item["severity"])
        c = monkeys.index(item["monkey"])
        matrix[r][c] += 1
    fig = go.Figure(data=go.Heatmap(z=matrix, x=monkeys, y=severities, colorscale="Reds"))
    fig.update_layout(title="AFP Heatmap")
    return fig

