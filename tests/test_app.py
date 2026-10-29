"""M3: the app's data layer, state, sandbox and a smoke test of every Streamlit page (against the small world)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from app import queries as q
from app import sandbox, state

ROOT = Path(__file__).resolve().parent.parent
VIEWS = ROOT / "app" / "streamlit_app" / "views"


@pytest.fixture()
def app_env(small_db, tmp_path, monkeypatch):
    """Point the app at the small world, a private state DB and a scratch copy of the seeds."""
    proj = sandbox._scratch_project(tmp_path, {})
    monkeypatch.setenv("SIGNAL_APP_DBS", f"holdout={small_db},dev={small_db}")
    monkeypatch.setenv("SIGNAL_APP_STATE", str(tmp_path / "state.duckdb"))
    monkeypatch.setenv("SIGNAL_SEEDS_DIR", str(proj / "seeds"))
    return {"db": small_db, "project": proj}


def an_alerted_account(db) -> tuple[str, date]:
    a = q.df(db, "select account_id, alert_date from gold.engine_alerts order by engine_score desc limit 1")
    return a.account_id[0], pd.Timestamp(a.alert_date[0]).date()


# ---------- query layer ----------

def test_breakdown_rebuilds_engine_score(small_db):
    account_id, on = an_alerted_account(small_db)
    steps = q.score_breakdown(small_db, account_id, on)
    score = q.df(small_db, "select engine_score from gold.account_daily_scores where account_id = ? and score_date = ?",
                 [account_id, on]).engine_score[0]
    assert steps.value.iloc[-1] == pytest.approx(score)
    assert steps.step.iloc[0].startswith("Activity")


def test_profile_summary_and_weekly(small_db):
    ev = q.evaluation(small_db)
    summary = q.profile_summary(ev)
    assert list(summary.key) == ["pings", "precise", "broad"]
    weekly = q.weekly_alerts(small_db, "broad")
    assert weekly.method.nunique() == 4 and (weekly.alerts >= 0).all()
    assert set(q.positives_caught(ev, "broad").account_id) == set(ev["positives"].account_id)
    assert q.hard_negatives(ev, "precise")["planted"].sum() == 8


def test_feed_matches_alert_table(small_db):
    win = q.window(small_db)
    feed = q.alert_feed(small_db, "broad", win.end, days=91)
    n = q.df(small_db, "select count(*) n from gold.engine_alerts where profile = 'broad' and alert_date between ? and ?",
             [win.start, win.end]).n[0]
    assert len(feed) == n
    assert feed.reason.notna().all()


def test_decay_curve_halves_each_half_life():
    ev = pd.DataFrame([{"occurred_at": pd.Timestamp("2026-07-01"), "event_type": "pricing_page", "weight": 5.0, "half_life_days": 5.0}])
    c = q.decay_curves(ev, date(2026, 7, 20)).set_index("date").contribution
    assert c[date(2026, 7, 1)] == pytest.approx(5.0)
    assert c[date(2026, 7, 6)] == pytest.approx(2.5)
    assert c[date(2026, 7, 11)] == pytest.approx(1.25)


def test_queries_never_hold_the_warehouse(small_db, tmp_path):
    """After any query the file is closed, so a writer (dbt) can open it."""
    q.account_list(small_db)
    con = duckdb.connect(str(small_db))  # read-write; fails if a read-only handle were still open in this process
    con.close()


# ---------- state ----------

def test_feedback_roundtrip(app_env):
    state.record_feedback("acc_1", date(2026, 7, 1), "broad", "accepted", "alok")
    state.record_feedback("acc_1", date(2026, 7, 1), "broad", "dismissed", "alok")  # latest wins
    fb = state.feedback()
    assert len(fb) == 1 and fb.outcome[0] == "dismissed"
    with pytest.raises(ValueError):
        state.record_feedback("acc_1", date(2026, 7, 1), "broad", "maybe", "alok")


def test_active_profile_change_is_applied_and_logged(app_env, db_copy):
    assert state.active_profile() == "broad"
    with pytest.raises(ValueError):
        state.set_active_profile("precise", "alok", "", dbs=[db_copy], project_dir=app_env["project"])
    state.set_active_profile("precise", "alok", "testing", dbs=[db_copy], project_dir=app_env["project"])
    assert state.active_profile() == "precise"
    active = q.df(db_copy, "select distinct profile from gold.engine_alerts where is_active")
    assert active.profile.tolist() == ["precise"]
    log = state.audit_log()
    assert (log.old_value[0], log.new_value[0], log.user_name[0]) == ("broad", "precise", "alok")
    real = (ROOT / "dbt_project" / "seeds" / "scoring_params.csv").read_text()
    assert "active_profile,broad" in real  # the repo's config was never touched


# ---------- sandbox ----------

def test_sandbox_compares_current_and_edited(small_db, tmp_path):
    params = sandbox.read_seed("scoring_params")
    params.loc[params.param == "no_bofu_multiplier", "value"] = "1.0"
    out = sandbox.compare(Path(small_db), {"scoring_params": params}, work_dir=tmp_path / "sb")
    assert set(out.config) == {"current", "edited"}
    assert set(out.method) == {"Engine M2", "Engine M1"}
    m1 = out[out.method == "Engine M1"].pivot_table(index="budget", columns="config", values="recall")
    assert (m1["current"] == m1["edited"]).all()  # the gate is an M2 term; M1 must not move


# ---------- Streamlit pages ----------

@pytest.mark.parametrize("view", ["overview", "alerts", "account", "sandbox", "settings"])
def test_page_renders(app_env, view):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(VIEWS / f"{view}.py"), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title, "page has a title"
    leaked = [m.value for m in at.markdown if "DeltaGenerator" in m.value]
    assert not leaked, f"Streamlit magic printed an object: {leaked[:1]}"


def test_accept_button_records_feedback(app_env):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(VIEWS / "alerts.py"), default_timeout=120)
    at.run()
    at.selectbox[1].set_value(30).run()  # widen the window so there is at least one alert
    accept = [b for b in at.button if b.label == "Accept"]
    if not accept:
        pytest.skip("no alerts in the small world's last 30 days")
    accept[0].click().run()
    assert len(state.feedback()) == 1
