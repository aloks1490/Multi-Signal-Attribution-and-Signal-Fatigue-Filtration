"""Shared Streamlit pieces: path bootstrap, sidebar controls and cached wrappers around app.queries."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app import bootstrap  # noqa: E402
from app import queries as q  # noqa: E402
from app import state  # noqa: E402

PROFILE_SHORT = {"precise": "Precise", "broad": "Broad"}


def _key(db: Path) -> tuple[str, float]:
    """Cache key that changes whenever dbt rewrites the warehouse file."""
    return str(db), db.stat().st_mtime


@st.cache_data(show_spinner="Evaluating methods…")
def evaluation(db_key: tuple[str, float]) -> dict:
    return q.evaluation(db_key[0])


@st.cache_data(show_spinner="Tracing the precision/recall curve…")
def threshold_curve(db_key: tuple[str, float]):
    return q.threshold_curve(db_key[0])


@st.cache_data
def weekly_alerts(db_key: tuple[str, float], profile: str):
    return q.weekly_alerts(db_key[0], profile)


@st.cache_data
def account_list(db_key: tuple[str, float]):
    return q.account_list(db_key[0])


@st.cache_data
def params(db_key: tuple[str, float]) -> dict:
    return q.params(db_key[0])


def is_demo() -> bool:
    """The public hosted copy sets SIGNAL_DEMO=1 (environment or Streamlit secrets)."""
    if os.environ.get("SIGNAL_DEMO") == "1":
        return True
    try:
        return str(st.secrets.get("SIGNAL_DEMO", "")) == "1"
    except Exception:  # no secrets file
        return False


def ensure_data() -> None:
    """On a fresh clone or a hosted copy, build the synthetic worlds before the first page renders."""
    if os.environ.get("SIGNAL_APP_DBS") or not bootstrap.missing():
        return
    with st.status("First start: building the synthetic worlds (2,000 companies each, 1–3 minutes)…",
                   expanded=True) as status:
        try:
            built = bootstrap.ensure(on_step=lambda name: status.write(f"Generating and scoring the {name} world…"))
        except Exception as e:
            status.update(label="Building the data failed", state="error")
            st.error(str(e))
            st.stop()
        status.update(label=f"Built: {', '.join(built) or 'ready'}", state="complete", expanded=False)
    st.cache_data.clear()


def sidebar() -> dict:
    """Data source, explore profile and viewer name. Returns the current choices."""
    ensure_data()
    dbs = q.databases()
    if not dbs:
        st.error("No warehouse found. Run `make m1` first.")
        st.stop()
    with st.sidebar:
        if is_demo():
            st.caption("Public demo on synthetic data. Changes you make here stay in this copy and reset when it restarts.")
        name = st.selectbox("Data", list(dbs), help="holdout = headline numbers; dev = where thresholds were tuned")
        db = dbs[name]
        active = state.active_profile()
        if "explore_profile" not in st.session_state:
            st.session_state.explore_profile = active
        explore = st.segmented_control(
            "Explore profile", options=list(q.PROFILES), format_func=lambda p: PROFILE_SHORT[p],
            key="explore_profile", help="Changes only what you see. Settings → Active profile changes what reps receive.",
        ) or active
        st.caption(f"{q.PROFILE_LABELS[explore]}")
        st.caption(f"Reps currently receive: **{PROFILE_SHORT[active]}**")
        user = st.text_input("Your name", value=st.session_state.get("user", os.environ.get("SIGNAL_USER", "")),
                             placeholder="for feedback and the audit log", key="user").strip() or "anonymous"
    return {"db": db, "db_name": name, "db_key": _key(db), "explore": explore, "active": active, "user": user}


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"
