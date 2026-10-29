"""Plotly figures shared by every frontend (Streamlit uses st.plotly_chart, Reflex uses rx.plotly)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go

# One color per method/series, used everywhere so the same thing always looks the same.
COLORS = {
    "Per-event pings": "#9aa0a6",
    "Static points": "#c5a572",
    "Engine M1": "#7fa7d9",
    "Engine M2": "#1f6feb",
    "precise": "#7c3aed",
    "broad": "#0e9f6e",
    "TOFU": "#9aa0a6",
    "MOFU": "#e3a008",
    "BOFU": "#d03801",
    "TRIGGER": "#1f6feb",
    "NONE": "#9aa0a6",
}


def _color(name: str) -> str:
    for key, value in COLORS.items():
        if name.startswith(key):
            return value
    return "#555"


def _layout(fig: go.Figure, height: int = 360, **kw) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=-0.2), **kw)
    return fig


def weekly_alerts(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for method, g in df.groupby("method", sort=False):
        fig.add_bar(x=g["week_start"], y=g["alerts"], name=method, marker_color=_color(method))
    fig.update_yaxes(type="log", title="alerts per week (log scale)")
    return _layout(fig, barmode="group")


def tradeoff_curve(curve: pd.DataFrame, presets: dict[str, dict], chosen: float | None = None) -> go.Figure:
    """Recall vs alert volume, with precision on hover and the F1/F2 presets marked."""
    c = curve.sort_values("alerts")
    fig = go.Figure()
    fig.add_scatter(x=c["alerts"], y=c["recall"], mode="lines", name="recall", line=dict(color=COLORS["Engine M2"]),
                    customdata=c[["precision", "threshold"]], hovertemplate="alerts %{x}<br>recall %{y:.0%}<br>precision %{customdata[0]:.0%}<br>threshold %{customdata[1]:.1f}")
    fig.add_scatter(x=c["alerts"], y=c["precision"], mode="lines", name="precision", line=dict(color="#d03801", dash="dot"))
    for name, s in presets.items():
        fig.add_scatter(x=[s["alerts"]], y=[s["recall"]], mode="markers+text", text=[name], textposition="top center",
                        marker=dict(size=12, color=COLORS.get(name, "#000")), name=name, showlegend=False)
    if chosen is not None:
        fig.add_vline(x=chosen, line_dash="dash", line_color="#555")
    fig.update_xaxes(title="alerts in the 13-week window", type="log")
    fig.update_yaxes(title="share", tickformat=".0%", range=[0, 1.05])
    return _layout(fig)


def score_history(hist: pd.DataFrame, thresholds: dict[str, float], alerts: pd.DataFrame, meeting: date | None) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=hist["score_date"], y=hist["engine_score"], name="M2 score", line=dict(color=COLORS["Engine M2"], width=3))
    fig.add_scatter(x=hist["score_date"], y=hist["engine_score_m1"], name="M1 score", line=dict(color=COLORS["Engine M1"], dash="dot"))
    for prof, t in thresholds.items():
        fig.add_hline(y=t, line_dash="dash", line_color=COLORS[prof], annotation_text=f"{prof} threshold", annotation_position="top left")
    for prof, g in alerts.groupby("profile"):
        fig.add_scatter(x=g["alert_date"], y=g["engine_score"], mode="markers", name=f"alert ({prof})",
                        marker=dict(symbol="triangle-up", size=12, color=COLORS[prof]))
    if meeting is not None and not pd.isna(meeting):
        fig.add_vline(x=pd.Timestamp(meeting), line_color="#0e9f6e", annotation_text="meeting (synthetic truth)")
    fig.update_yaxes(title="score")
    return _layout(fig, height=380)


def breakdown(steps: pd.DataFrame) -> go.Figure:
    values = steps["value"].tolist()
    measures = ["absolute"] + ["relative"] * (len(values) - 1)
    deltas = [values[0]] + [b - a for a, b in zip(values, values[1:])]
    fig = go.Figure(go.Waterfall(x=steps["step"], y=deltas, measure=measures, text=[f"{v:.1f}" for v in values],
                                 textposition="outside", connector=dict(line=dict(color="#bbb")),
                                 increasing=dict(marker_color="#0e9f6e"), decreasing=dict(marker_color="#d03801"),
                                 totals=dict(marker_color=COLORS["Engine M2"])))
    fig.update_yaxes(title="score after each step")
    return _layout(fig, height=380, showlegend=False)


def event_timeline(events: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for stage, g in events.groupby("funnel_stage"):
        fig.add_scatter(x=g["occurred_at"], y=g["person"], mode="markers", name=stage,
                        marker=dict(size=9, color=COLORS.get(stage, "#555")), text=g["event_type"],
                        hovertemplate="%{text}<br>%{x}<extra></extra>")
    n_people = max(events["person"].nunique(), 1)
    return _layout(fig, height=min(120 + 28 * n_people, 700))


def decay_curves(curves: pd.DataFrame, on: date) -> go.Figure:
    fig = go.Figure()
    for event, g in curves.groupby("event", sort=False):
        fig.add_scatter(x=g["date"], y=g["contribution"], mode="lines", name=event)
    fig.add_vline(x=pd.Timestamp(on), line_dash="dash", line_color="#555", annotation_text="selected day")
    fig.update_yaxes(title="points contributed")
    return _layout(fig)


def contributions(contrib: pd.DataFrame) -> go.Figure:
    c = contrib.sort_values("contribution")
    fig = go.Figure(go.Bar(x=c["contribution"], y=c["signal"], orientation="h",
                           marker_color=[COLORS["TRIGGER"] if k == "trigger" else COLORS["MOFU"] for k in c["kind"]]))
    fig.update_xaxes(title="points on the selected day")
    return _layout(fig, height=max(200, 26 * len(c) + 60), showlegend=False)


def sandbox_comparison(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for (config, method), g in df.groupby(["config", "method"], sort=False):
        fig.add_scatter(x=g["alerts"], y=g["recall"], mode="lines+markers", name=f"{method} · {config}",
                        line=dict(color=_color(method), dash="solid" if config == "edited" else "dot"))
    fig.update_xaxes(title="alerts in window")
    fig.update_yaxes(title="recall", tickformat=".0%")
    return _layout(fig)
