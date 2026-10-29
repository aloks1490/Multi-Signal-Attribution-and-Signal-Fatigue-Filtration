"""Alert feed: what an AE sees, with reasons and accept/dismiss."""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402

from app import queries as q  # noqa: E402
from app import state  # noqa: E402
from app.streamlit_app import ui  # noqa: E402

ctx = ui.sidebar()
prof = ctx["explore"]
win = q.window(ctx["db"])

st.title("Alert feed")
if prof != ctx["active"]:
    st.warning(f"Previewing the **{ui.PROFILE_SHORT[prof]}** profile. Reps currently receive **{ui.PROFILE_SHORT[ctx['active']]}**.")

c1, c2, c3 = st.columns([2, 1, 1])
as_of = c1.slider("As of", min_value=win.start, max_value=win.end, value=win.end, step=timedelta(days=1), format="ddd D MMM")
ae = c2.selectbox("AE", ["All"] + q.owners(ctx["db"]))
days = c3.selectbox("Show last", [7, 14, 30], format_func=lambda d: f"{d} days")
ae = None if ae == "All" else ae

feed = q.alert_feed(ctx["db"], prof, as_of, days=days, ae=ae)
fb = state.feedback()
st.caption(f"{len(feed)} alerts in the last {days} days. Each alert fires once, when an account first crosses the threshold.")

for _, a in feed.iterrows():
    done = fb[(fb.account_id == a.account_id) & (fb.alert_date.dt.date == a.alert_date.date()) & (fb.profile == prof)] if len(fb) else fb
    with st.container(border=True):
        left, right = st.columns([5, 2])
        left.markdown(f"**{a.company_name}** · {a.account_id} · fit {a.fit_grade} · {a.owner_ae_id} · {a.alert_date:%a %d %b}")
        left.markdown(a.reason)
        if len(done):
            right.success(f"{done.iloc[0].outcome} by {done.iloc[0].user_name}")
        else:
            b1, b2 = right.columns(2)
            if b1.button("Accept", key=f"acc_{prof}_{a.account_id}_{a.alert_date:%Y%m%d}"):
                state.record_feedback(a.account_id, a.alert_date.date(), prof, "accepted", ctx["user"])
                st.rerun()
            if b2.button("Dismiss", key=f"dis_{prof}_{a.account_id}_{a.alert_date:%Y%m%d}"):
                state.record_feedback(a.account_id, a.alert_date.date(), prof, "dismissed", ctx["user"])
                st.rerun()

st.subheader(f"Tiers on {as_of:%d %b}")
st.caption("Hot accounts are above the threshold (they alerted when they crossed it). Warm and Watch are visible here but never ping.")
st.dataframe(q.watchlist(ctx["db"], prof, as_of, ae=ae), hide_index=True, use_container_width=True)
