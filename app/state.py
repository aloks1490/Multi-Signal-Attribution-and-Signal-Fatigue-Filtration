"""App-owned state, kept out of the warehouse: rep feedback on alerts and the active-profile audit log.

The team-level active profile itself lives in dbt_project/seeds/scoring_params.csv (config under git), so a change
is visible in code review and in the audit log here.
"""
from __future__ import annotations

import csv
import os
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from app.dbt_runner import DBT_DIR, run_dbt

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ("accepted", "dismissed")


def state_path() -> Path:
    return Path(os.environ.get("SIGNAL_APP_STATE", ROOT / "data" / "app_state.duckdb"))


def seeds_dir() -> Path:
    return Path(os.environ.get("SIGNAL_SEEDS_DIR", DBT_DIR / "seeds"))


@contextmanager
def _state():
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute("""
            create table if not exists feedback (
                account_id varchar, alert_date date, profile varchar, outcome varchar,
                note varchar, user_name varchar, created_at timestamp
            )""")
        con.execute("""
            create table if not exists settings_audit (
                setting varchar, old_value varchar, new_value varchar, user_name varchar,
                reason varchar, created_at timestamp
            )""")
        yield con
    finally:
        con.close()


# ---------- feedback ----------

def record_feedback(account_id: str, alert_date: date, profile: str, outcome: str, user: str, note: str = "") -> None:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    with _state() as con:
        con.execute("delete from feedback where account_id = ? and alert_date = ? and profile = ?", [account_id, alert_date, profile])
        con.execute("insert into feedback values (?, ?, ?, ?, ?, ?, ?)",
                    [account_id, alert_date, profile, outcome, note, user, datetime.now()])


def feedback() -> pd.DataFrame:
    with _state() as con:
        return con.execute("select * from feedback order by created_at desc").df()


# ---------- active profile ----------

def read_param(name: str) -> str:
    with (seeds_dir() / "scoring_params.csv").open() as f:
        for row in csv.DictReader(f):
            if row["param"] == name:
                return row["value"]
    raise KeyError(name)


def active_profile() -> str:
    return read_param("active_profile")


def _write_param(name: str, value: str) -> None:
    path = seeds_dir() / "scoring_params.csv"
    rows = list(csv.DictReader(path.open()))
    for r in rows:
        if r["param"] == name:
            r["value"] = value
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["param", "value"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def set_active_profile(new: str, user: str, reason: str, dbs: list[Path], project_dir: Path = DBT_DIR) -> None:
    """Change who gets pinged: update the seed, rebuild the alert flags in each warehouse, log the change.

    The warehouse files must not be open elsewhere (the app opens them per query, so this is safe).
    """
    if new not in ("precise", "broad"):
        raise ValueError("profile must be 'precise' or 'broad'")
    if not user.strip() or not reason.strip():
        raise ValueError("a name and a reason are required")
    old = active_profile()
    if old == new:
        return
    _write_param("active_profile", new)
    try:
        for db in dbs:
            run_dbt(db, "seed", "--select", "scoring_params", project_dir=project_dir)
            run_dbt(db, "run", "--select", "engine_alerts", project_dir=project_dir)
    except Exception:
        _write_param("active_profile", old)  # leave config and warehouse consistent
        raise
    with _state() as con:
        con.execute("insert into settings_audit values (?, ?, ?, ?, ?, ?)",
                    ["active_profile", old, new, user.strip(), reason.strip(), datetime.now()])


def audit_log() -> pd.DataFrame:
    with _state() as con:
        return con.execute("select * from settings_audit order by created_at desc").df()
