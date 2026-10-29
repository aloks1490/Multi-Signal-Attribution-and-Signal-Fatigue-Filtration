"""Account deep-dive: why an account scores what it scores."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import charts  # noqa: E402
from app import queries as q  # noqa: E402
from app.streamlit_app import ui  # noqa: E402

ctx = ui.sidebar()
st.title("Account deep-dive")

accounts = ui.account_list(ctx["db_key"])
labels = {
    r.account_id: f"{r.company_name} · {r.account_id} · peak {r.peak_score:.0f}" + (f" · {r.archetype or r.truth_class}" if r.truth_class != "noise" else "")
    for r in accounts.itertuples()
}
default = st.query_params.get("account", accounts.account_id.iloc[0])
ids = list(labels)
account_id = st.selectbox("Account", ids, index=ids.index(default) if default in ids else 0, format_func=labels.get)
st.query_params["account"] = account_id

info = q.account_profile(ctx["db"], account_id)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Fit", f"{info['fit_grade']} ({int(info['fit_points'])} pts)")
c2.metric("Employees", f"{info['employee_count']:,}")
c3.metric("Region", info["region"])
c4.metric("CRM", info["crm"])
c5.metric("Owner", info["owner_ae_id"])
if info["excluded"]:
    st.info(f"Excluded from alerts: **{info['exclusion']}**")
if info.get("truth_class") and info["truth_class"] != "noise":
    meeting = info["meeting_date"]
    st.caption(f"Synthetic truth (evaluation only): **{info['truth_class']}** {info['archetype'] or ''}"
               + (f", meeting on {pd.Timestamp(meeting):%d %b}" if pd.notna(meeting) else ""))

hist = q.score_history(ctx["db"], account_id)
alerts = q.account_alerts(ctx["db"], account_id)
st.plotly_chart(charts.score_history(hist, q.thresholds(ctx["db"]), alerts, info.get("meeting_date")), use_container_width=True)

dates = list(pd.to_datetime(hist.score_date).dt.date)
best = dates[int(hist.engine_score.idxmax())] if len(hist) else None
on = st.select_slider("Explain the score on", options=dates, value=best, format_func=lambda d: d.strftime("%a %d %b"))
row = hist[pd.to_datetime(hist.score_date).dt.date == on].iloc[0]
st.markdown(f"**Reason line:** {row.reason}")

left, right = st.columns(2)
with left:
    st.subheader("How the score is built")
    steps = q.score_breakdown(ctx["db"], account_id, on)
    st.plotly_chart(charts.breakdown(steps), use_container_width=True)
    st.dataframe(steps.assign(value=steps.value.round(2)), hide_index=True, use_container_width=True)
with right:
    st.subheader("Signals on that day")
    contrib = q.signal_contributions(ctx["db"], account_id, on)
    if len(contrib):
        st.plotly_chart(charts.contributions(contrib), use_container_width=True)
    else:
        st.caption("No signals contribute on this day.")

events = q.account_events(ctx["db"], account_id)
st.subheader("Decay: how the biggest signals fade")
st.caption("Each signal loses half its points every half-life, so last quarter's activity can't keep an account hot.")
curves = q.decay_curves(events, on)
if len(curves):
    st.plotly_chart(charts.decay_curves(curves, on), use_container_width=True)

st.subheader("Who did what")
if len(events):
    st.plotly_chart(charts.event_timeline(events), use_container_width=True)
    with st.expander(f"All {len(events)} events"):
        st.dataframe(events, hide_index=True, use_container_width=True)
else:
    st.caption("No first-party activity or triggers.")
