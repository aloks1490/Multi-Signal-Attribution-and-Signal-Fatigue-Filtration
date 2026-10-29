"""Tuning sandbox: rebuild scores with edited seeds on a scratch copy of the dev warehouse, then compare.

Only the dev seed is used, so tuning never touches the holdout numbers. Nothing here changes the real seeds;
an edited CSV is offered as a download and goes through git like any other config change.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from app.dbt_runner import DBT_DIR, run_dbt
from eval.calibrate import load_params, window_from
from eval.report import BUDGETS, budget_table

EDITABLE_SEEDS = ("signal_taxonomy", "pattern_multipliers", "combo_rules", "scoring_params")


def read_seed(name: str, seeds_dir: Path = DBT_DIR / "seeds") -> pd.DataFrame:
    return pd.read_csv(seeds_dir / f"{name}.csv", dtype={"value": str} if name == "scoring_params" else None)


def _scratch_project(work: Path, overrides: dict[str, pd.DataFrame]) -> Path:
    proj = work / "project"
    proj.mkdir()
    for name in ("models", "macros"):
        (proj / name).symlink_to(DBT_DIR / name, target_is_directory=True)
    shutil.copy(DBT_DIR / "dbt_project.yml", proj / "dbt_project.yml")
    shutil.copy(DBT_DIR / "profiles.yml", proj / "profiles.yml")
    shutil.copytree(DBT_DIR / "seeds", proj / "seeds")
    for name, frame in overrides.items():
        if name not in EDITABLE_SEEDS:
            raise ValueError(f"{name} is not an editable seed")
        frame.to_csv(proj / "seeds" / f"{name}.csv", index=False, lineterminator="\n")
    return proj


def compare(base_db: Path, overrides: dict[str, pd.DataFrame], work_dir: Path | None = None) -> pd.DataFrame:
    """Precision and recall at equal alert budgets, current config vs edited config, for engine M2 and M1."""
    work = Path(work_dir or tempfile.mkdtemp(prefix="signal_sandbox_"))
    work.mkdir(parents=True, exist_ok=True)
    proj = _scratch_project(work, overrides)
    db = work / "sandbox.duckdb"
    shutil.copy(base_db, db)
    run_dbt(db, "seed", project_dir=proj, work_dir=work)
    run_dbt(db, "run", "--select", "silver", "gold", project_dir=proj, work_dir=work)

    rows = []
    for label, path in (("current", base_db), ("edited", db)):
        con = duckdb.connect(str(path), read_only=True)
        try:
            p = load_params(con)
            win = window_from(p, 5)
            truth = con.execute("select * from labels.account_truth").df()
            table = budget_table(con, p, truth, win)
        finally:
            con.close()
        for method in ("Engine M2", "Engine M1"):
            for b in BUDGETS:
                s = table[method][b]
                rows.append({"config": label, "method": method, "budget": b, "alerts": s["alerts"],
                             "precision": s["precision_accounts"], "recall": s["recall"]})
    return pd.DataFrame(rows)
