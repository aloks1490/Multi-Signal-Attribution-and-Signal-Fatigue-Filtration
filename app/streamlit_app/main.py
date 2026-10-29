"""Signal Engine app. Run with: make app"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Signal Engine", page_icon="📡", layout="wide")

VIEWS = Path(__file__).resolve().parent / "views"
nav = st.navigation([
    st.Page(VIEWS / "overview.py", title="Overview", icon="📊", default=True),
    st.Page(VIEWS / "alerts.py", title="Alert feed", icon="🔔"),
    st.Page(VIEWS / "account.py", title="Account deep-dive", icon="🔎"),
    st.Page(VIEWS / "sandbox.py", title="Tuning sandbox", icon="🧪"),
    st.Page(VIEWS / "settings.py", title="Settings", icon="⚙️"),
])
nav.run()
