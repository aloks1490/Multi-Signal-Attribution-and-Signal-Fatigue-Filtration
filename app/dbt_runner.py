"""Run dbt in a subprocess against one DuckDB file (the subprocess closes the file when done)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt_project"


class DbtError(RuntimeError):
    pass


def run_dbt(db: str | Path, *args: str, project_dir: Path = DBT_DIR, work_dir: Path | None = None) -> str:
    dbt = Path(sys.executable).parent / "dbt"
    cmd = [str(dbt), *args, "--project-dir", str(project_dir), "--profiles-dir", str(project_dir)]
    if work_dir is not None:
        cmd += ["--target-path", str(work_dir / "target"), "--log-path", str(work_dir / "logs")]
    res = subprocess.run(cmd, env={**os.environ, "SIGNAL_DB": str(db)}, capture_output=True, text=True)
    if res.returncode != 0:
        raise DbtError(f"dbt {' '.join(args)} failed:\n{res.stdout[-3000:]}")
    return res.stdout
