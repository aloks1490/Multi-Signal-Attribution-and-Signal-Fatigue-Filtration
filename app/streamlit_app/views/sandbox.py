"""Tuning sandbox: edit weights and rules, rebuild on a copy of the dev data, compare at equal alert budgets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402

from app import charts  # noqa: E402
from app import queries as q  # noqa: E402
from app import sandbox  # noqa: E402
from app.streamlit_app import ui  # noqa: E402

ctx = ui.sidebar()
st.title("Tuning sandbox")
st.caption("Runs on a scratch copy of the **dev** data only, so tuning never touches the holdout numbers. "
           "Your real config is not changed: download an edited CSV and commit it if you want to keep it.")

dev = q.databases().get("dev")
if dev is None:
    st.warning("The dev warehouse is missing. Run `make m1` first.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Signal weights", "Pattern multipliers", "Combos and gates"])
with tab1:
    tax = st.data_editor(sandbox.read_seed("signal_taxonomy"), hide_index=True, use_container_width=True,
                         disabled=["event_type", "category", "source", "funnel_stage", "baseline_ping"], key="ed_tax")
with tab2:
    mult = st.data_editor(sandbox.read_seed("pattern_multipliers"), hide_index=True, use_container_width=True,
                          disabled=["multiplier", "min_value", "max_value"], key="ed_mult")
with tab3:
    combos = st.data_editor(sandbox.read_seed("combo_rules"), hide_index=True, use_container_width=True,
                            disabled=["combo", "description"], key="ed_combo")
    params = sandbox.read_seed("scoring_params")
    editable = params[params.param.isin(["no_bofu_multiplier", "spike_min_people"])]
    edited = st.data_editor(editable, hide_index=True, disabled=["param"], key="ed_params")
    params = params.set_index("param")
    params.loc[edited.param, "value"] = edited.value.astype(str).values
    params = params.reset_index()

overrides = {"signal_taxonomy": tax, "pattern_multipliers": mult, "combo_rules": combos, "scoring_params": params}
if st.button("Rebuild and compare", type="primary"):
    with st.spinner("Rebuilding silver and gold on a copy of the dev data (about 20 seconds)…"):
        try:
            st.session_state.sandbox_result = sandbox.compare(dev, overrides)
        except Exception as e:  # dbt errors are shown, not raised
            st.error(str(e))

result = st.session_state.get("sandbox_result")
if result is not None:
    st.subheader("Recall at equal alert budgets (dev data)")
    st.plotly_chart(charts.sandbox_comparison(result), use_container_width=True)
    wide = result.pivot_table(index=["method", "budget"], columns="config", values=["recall", "precision"]).round(3)
    wide.columns = [f"{m} ({c})" for m, c in wide.columns]
    st.dataframe(wide, use_container_width=True)
    st.caption("Budgets are matched by alert count alone (no labels), so the comparison is fair. "
               "Re-run calibration after keeping a change: thresholds depend on the weights.")

st.subheader("Download edited config")
cols = st.columns(len(overrides))
for col, (name, frame) in zip(cols, overrides.items()):
    col.download_button(f"{name}.csv", frame.to_csv(index=False, lineterminator="\n"), file_name=f"{name}.csv", mime="text/csv")
