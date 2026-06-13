"""Reusable Plotly chart builders for ChaosAgent Streamlit pages."""

from __future__ import annotations

import plotly.graph_objects as go


def srq_over_time(scores: list[float], title: str = "SRQ Over Turns") -> go.Figure:
    """Return line chart for SRQ progression over turns."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=scores,
        x=list(range(len(scores))),
        mode="lines+markers",
        name="SRQ",
        line=dict(color="#4F8EF7", width=2),
        marker=dict(size=6),
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Turn",
        yaxis_title="SRQ Score (0–10)",
        yaxis=dict(range=[0, 10]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def hrt_over_time(scores: list[float]) -> go.Figure:
    """Return line chart for HRT progression over turns."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=scores,
        x=list(range(len(scores))),
        mode="lines+markers",
        name="HRT",
        line=dict(color="#F7874F", width=2),
        marker=dict(size=6),
    ))
    fig.update_layout(
        title="HRT Over Turns",
        xaxis_title="Turn",
        yaxis_title="HRT Score (0–10)",
        yaxis=dict(range=[0, 10]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def score_radar(metrics: dict[str, float]) -> go.Figure:
    """Return radar chart for pillar-wise score distribution."""
    labels = list(metrics.keys())
    values = list(metrics.values())
    fig = go.Figure(data=go.Scatterpolar(
        r=values + values[:1],
        theta=labels + labels[:1],
        fill="toself",
        line=dict(color="#4F8EF7"),
    ))
    fig.update_layout(
        title="Score Radar by Monkey Type",
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def afp_heatmap(data: list[dict]) -> go.Figure:
    """Return heatmap figure for AFP counts by monkey type and severity.

    BUG-13 fix: API returns dicts with key "monkey_type" (not "monkey").
    The chart now reads the correct key so it no longer raises a KeyError.
    """
    # BUG-13 FIX: use "monkey_type" key, not "monkey"
    monkeys = sorted({item["monkey_type"] for item in data}) if data else ["none"]
    severities = ["low", "medium", "high", "critical"]
    matrix = [[0 for _ in monkeys] for _ in severities]

    for item in data:
        sev = item.get("severity", "low")
        mtype = item.get("monkey_type", "")
        if sev in severities and mtype in monkeys:
            r = severities.index(sev)
            c = monkeys.index(mtype)
            matrix[r][c] += 1

    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=monkeys,
        y=severities,
        colorscale="Reds",
        text=[[str(v) if v else "" for v in row] for row in matrix],
        texttemplate="%{text}",
    ))
    fig.update_layout(
        title="AFP Heatmap — Count by Monkey × Severity",
        xaxis_title="Monkey Type",
        yaxis_title="Severity",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def multi_score_line(interactions: list[dict]) -> go.Figure:
    """Overlay SRQ, HRT, and Safety scores across all turns."""
    turns = [i["turn"] for i in interactions]
    fig = go.Figure()
    for metric, colour in [
        ("srq_score", "#4F8EF7"),
        ("hrt_score", "#F7874F"),
        ("safety_score", "#4FF78E"),
    ]:
        fig.add_trace(go.Scatter(
            x=turns,
            y=[i.get(metric, 0.0) for i in interactions],
            mode="lines+markers",
            name=metric.replace("_score", "").upper(),
            line=dict(color=colour, width=2),
        ))
    fig.update_layout(
        title="Score Trends Over Turns",
        xaxis_title="Turn",
        yaxis_title="Score (0–10)",
        yaxis=dict(range=[0, 10]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig