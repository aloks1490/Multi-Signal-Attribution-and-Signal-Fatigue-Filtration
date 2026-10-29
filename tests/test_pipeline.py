"""T-L, T-P, T-E: the truth wall, point-in-time invariance and the end-to-end run."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

from eval import report
from tests.conftest import DBT_DIR, run_dbt

CUTOFF = date(2026, 8, 10)


def test_l1_no_model_reads_labels(small_manifest):
    manifest = json.loads(Path(small_manifest).read_text())
    for uid, node in manifest["nodes"].items():
        if node["resource_type"] not in ("model", "test", "seed", "snapshot"):
            continue
        assert "labels" not in (node.get("schema") or ""), uid
        assert "labels." not in (node.get("raw_code") or ""), uid
        for dep in node.get("depends_on", {}).get("nodes", []):
            assert "labels" not in dep, (uid, dep)
    assert not any(s.get("schema") == "labels" for s in manifest["sources"].values())
    for sql in DBT_DIR.rglob("*.sql"):
        if "target" in sql.parts:
            continue
        assert "labels." not in sql.read_text(), sql


def test_p1_scores_ignore_the_future(db_copy, small_db, tmp_path):
    """Delete everything that happened on or after CUTOFF, rebuild: scores up to CUTOFF must not change."""
    con = duckdb.connect(str(db_copy))
    for t in ("web_events", "product_events", "marketing_events", "trigger_events"):
        con.execute(f"delete from bronze.{t} where occurred_at >= ?", [CUTOFF])
    con.execute("update bronze.trigger_events set closed_at = null where closed_at >= ?", [CUTOFF])
    con.close()
    run_dbt(db_copy, tmp_path, "run", "--select", "+account_daily_scores")

    q = """select account_id, score_date, activity_score, trigger_score, engine_score
           from gold.account_daily_scores where score_date <= ? order by 1, 2"""
    before = duckdb.connect(str(small_db), read_only=True).execute(q, [CUTOFF]).df()
    after = duckdb.connect(str(db_copy), read_only=True).execute(q, [CUTOFF]).df()
    assert len(before) == len(after) > 0
    assert (before[["account_id", "score_date"]].values == after[["account_id", "score_date"]].values).all()
    for col in ("activity_score", "trigger_score", "engine_score"):
        assert np.allclose(before[col], after[col], atol=1e-9), col


def test_e1_end_to_end_report(small_db, tmp_path):
    out = tmp_path / "results.md"
    text = report.write({"small": (str(small_db), "test")}, out, n_aes=5)
    assert out.exists()
    for method in ("Per-event pings", "Static points precise (F1)", "Engine M1 precise (F1)",
                   "Engine M2 precise (F1)", "Engine M2 broad (F2)"):
        assert f"| {method} |" in text
    assert "Equal alert budget" in text
