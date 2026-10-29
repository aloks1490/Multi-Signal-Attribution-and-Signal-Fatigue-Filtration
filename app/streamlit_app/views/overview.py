"""Overview: per-event pings vs static points vs the engine, and the precise/broad trade-off."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402

from app import charts  # noqa: E402
from app import queries as q  # noqa: E402
from app.streamlit_app import ui  # noqa: E402

ctx = ui.sidebar()
ev = ui.evaluation(ctx["db_key"])
prof = ctx["explore"]

st.title("Fewer alerts, more buyers")
st.caption(f"{ctx['db_name']} data · 13 weeks · 5 AEs · {len(ev['positives'])} real buyers hidden in 2,000 accounts. "
           "Buyer labels come from the synthetic world and are used only for evaluation.")

summary = q.profile_summary(ev).set_index("key")
pings, eng = summary.loc["pings"], summary.loc[prof]
c1, c2, c3 = st.columns(3)
c1.metric("Alerts per AE per week", f"{eng.alerts_per_ae_week:.1f}", f"{eng.alerts_per_ae_week - pings.alerts_per_ae_week:+.1f} vs per-event pings",
          delta_color="inverse")
c2.metric("Alerted accounts that were buyers", ui.pct(eng.precision_accounts),
          f"{(eng.precision_accounts - pings.precision_accounts) * 100:+.0f} pts vs pings")
c3.metric(f"Buyers caught before the meeting ({eng.caught} of {eng.positives})", ui.pct(eng.recall),
          f"{(eng.recall - pings.recall) * 100:+.0f} pts vs pings")

st.subheader("Two profiles, one engine")
cols = st.columns(2)
for col, key in zip(cols, q.PROFILES):
    r = summary.loc[key]
    tags = []
    if key == prof:
        tags.append("exploring")
    if key == ctx["active"]:
        tags.append("reps receive this")
    with col.container(border=True):
        st.markdown(f"**{q.PROFILE_LABELS[key]}**" + (f"  ·  _{', '.join(tags)}_" if tags else ""))
        st.markdown(f"{r.alerts} alerts in 13 weeks · {ui.pct(r.precision_accounts)} were buyers · caught {r.caught} of {r.positives}")

with st.expander("Explore the full trade-off curve", expanded=False):
    curve = ui.threshold_curve(ctx["db_key"])
    presets = {k: {"alerts": summary.loc[k].alerts, "recall": summary.loc[k].recall} for k in q.PROFILES}
    lo, hi = float(curve.threshold.min()), float(curve.threshold.max())
    t = st.slider("Threshold (score needed to alert)", lo, hi, float(ui.params(ctx["db_key"])[f"engine_threshold_{prof}"]))
    s = q.alerts_at_threshold(ctx["db"], t)
    st.markdown(f"At **{t:.1f}**: {s['alerts']} alerts · {ui.pct(s['precision_accounts'])} were buyers · caught {len(s['caught_ids'])} of {s['positives']}")
    st.plotly_chart(charts.tradeoff_curve(curve, presets, chosen=s["alerts"]), use_container_width=True)
    st.caption("Exploring only. To change what reps receive, use Settings.")

st.subheader("Alerts per week")
st.plotly_chart(charts.weekly_alerts(ui.weekly_alerts(ctx["db_key"], prof)), use_container_width=True)

st.subheader("All methods")
rows = q.method_rows(ev)
st.dataframe(
    rows, hide_index=True, use_container_width=True,
    column_config={
        "precision_accounts": st.column_config.ProgressColumn("Alerted accounts that were buyers", format="percent", min_value=0, max_value=1),
        "recall": st.column_config.ProgressColumn("Buyers caught", format="percent", min_value=0, max_value=1),
        "alerts_per_ae_week": "Alerts/AE/week", "median_lead_days": "Median days of warning",
    },
)

left, right = st.columns(2)
with left:
    st.subheader("Real buyers: days of warning")
    st.caption("Days between the first useful alert and the meeting. Empty = missed.")
    st.dataframe(q.positives_caught(ev, prof), hide_index=True, use_container_width=True)
with right:
    st.subheader("Look-alikes that fooled each method")
    st.caption("Accounts that resemble buyers but are not (bots, single-person hammering, content bingers…).")
    st.dataframe(q.hard_negatives(ev, prof), hide_index=True, use_container_width=True)
