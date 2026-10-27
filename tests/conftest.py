"""Shared fixtures: one small-profile world, built and transformed once per test session."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from generator.__main__ import build
from generator.writer import frames, write

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt_project"
SEED = 42


def run_dbt(db: Path, work: Path, *args: str) -> None:
    """Run dbt in a subprocess against a given DuckDB file, keeping artifacts out of the repo.

    A subprocess (not dbtRunner) so the DuckDB file is closed and checkpointed when dbt finishes;
    an in-process dbt keeps its connection open and blocks read-only opens and file copies.
    """
    dbt = Path(sys.executable).parent / "dbt"
    res = subprocess.run(
        [str(dbt), *args,
         "--project-dir", str(DBT_DIR),
         "--profiles-dir", str(DBT_DIR),
         "--target-path", str(work / "target"),
         "--log-path", str(work / "logs")],
        env={**os.environ, "SIGNAL_DB": str(db)},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"dbt {' '.join(args)} failed:\n{res.stdout[-3000:]}"


@pytest.fixture(scope="session")
def small_world():
    return build("small", SEED)


@pytest.fixture(scope="session")
def small_frames(small_world):
    return frames(small_world)


@pytest.fixture(scope="session")
def small_db(tmp_path_factory, small_world) -> Path:
    work = tmp_path_factory.mktemp("small")
    db = work / "small.duckdb"
    write(small_world, db)
    run_dbt(db, work, "build")
    return db


@pytest.fixture(scope="session")
def small_manifest(small_db) -> Path:
    return small_db.parent / "target" / "manifest.json"


@pytest.fixture()
def con(small_db):
    c = duckdb.connect(str(small_db), read_only=True)
    yield c
    c.close()


@pytest.fixture()
def db_copy(small_db, tmp_path) -> Path:
    dst = tmp_path / "copy.duckdb"
    shutil.copy(small_db, dst)
    return dst
