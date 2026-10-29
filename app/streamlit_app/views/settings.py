"""Settings: the team-level active profile (who gets pinged), with confirmation and an audit log."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402

from app import queries as q  # noqa: E402
from app import state  # noqa: E402
from app.streamlit_app import ui  # noqa: E402

ctx = ui.sidebar()
st.title("Settings")

st.subheader("Active profile")
st.markdown("This decides which alerts reach reps (Slack and HubSpot from M4). The **Explore** toggle in the sidebar "
            "only changes what you see; this setting changes what everyone receives.")
summary = q.profile_summary(ui.evaluation(ctx["db_key"])).set_index("key")
for key in q.PROFILES:
    r = summary.loc[key]
    mark = " (active ✅)" if key == ctx["active"] else ""
    st.markdown(f"- **{q.PROFILE_LABELS[key]}**{mark}: {r.alerts} alerts in 13 weeks, "
                f"{ui.pct(r.precision_accounts)} were buyers, caught {r.caught} of {r.positives} ({ctx['db_name']} data)")

with st.form("active_profile"):
    new = st.radio("Reps should receive", list(q.PROFILES), index=list(q.PROFILES).index(ctx["active"]),
                   format_func=lambda p: q.PROFILE_LABELS[p], horizontal=True)
    reason = st.text_input("Reason for the change (kept in the audit log)")
    confirm = st.checkbox("I understand this changes which alerts every rep receives")
    submitted = st.form_submit_button("Apply", type="primary")
if submitted:
    if new == ctx["active"]:
        st.info("That profile is already active.")
    elif not confirm:
        st.error("Tick the confirmation box to apply the change.")
    else:
        with st.spinner("Updating config and rebuilding alert flags…"):
            try:
                state.set_active_profile(new, ctx["user"], reason, dbs=list(q.databases().values()))
            except Exception as e:
                st.error(str(e))
            else:
                st.cache_data.clear()
                st.success(f"Reps now receive the {ui.PROFILE_SHORT[new]} profile.")
                st.rerun()

st.subheader("Change history")
log = state.audit_log()
if len(log):
    st.dataframe(log, hide_index=True, use_container_width=True)
else:
    st.caption("No changes yet.")

st.subheader("Rep feedback on alerts")
fb = state.feedback()
if len(fb):
    st.dataframe(fb, hide_index=True, use_container_width=True)
else:
    st.caption("No feedback yet.")
