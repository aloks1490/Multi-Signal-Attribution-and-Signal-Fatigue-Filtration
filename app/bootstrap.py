"""Build the synthetic worlds when the app starts without them (a fresh clone, or a hosted copy whose disk starts empty).

UI-free, so a Reflex version can call it unchanged. The calibrated thresholds are committed in the seeds, so a
rebuild is just generate + dbt build and gives the same numbers as `make m1`.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from app.dbt_runner import run_dbt

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WORLDS = {"holdout": 7, "dev": 42}  # holdout first: it is the default view
_lock = threading.Lock()  # one build per process; other sessions wait for it


class BootstrapError(RuntimeError):
    pass


def missing(data_dir: Path = DATA_DIR) -> list[str]:
    return [name for name in WORLDS if not (data_dir / f"{name}.duckdb").exists()]


def build_world(name: str, data_dir: Path = DATA_DIR, profile: str = "standard") -> Path:
    """Generate one world and run dbt build on it. Builds in a side folder and moves the file at the end, so the
    app never sees a half-built warehouse. The file keeps its final name throughout, because dbt-duckdb names
    the catalog after it and views refer to that name."""
    final = data_dir / f"{name}.duckdb"
    work = data_dir / ".building"
    work.mkdir(parents=True, exist_ok=True)
    tmp = work / final.name
    for p in (tmp, tmp.with_name(tmp.name + ".wal")):
        p.unlink(missing_ok=True)
    res = subprocess.run(
        [sys.executable, "-m", "generator", "--profile", profile, "--seed", str(WORLDS[name]), "--db", str(tmp)],
        cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        raise BootstrapError(f"generator failed for {name}:\n{(res.stdout + res.stderr)[-3000:]}")
    run_dbt(tmp, "build")
    tmp.replace(final)
    if not any(work.iterdir()):
        work.rmdir()
    return final


def ensure(data_dir: Path = DATA_DIR, on_step: Callable[[str], None] | None = None, profile: str = "standard") -> list[str]:
    """Build every missing world. Returns the names built (empty when everything was already there)."""
    if not missing(data_dir):
        return []
    with _lock:
        todo = missing(data_dir)  # another session may have finished while this one waited
        for name in todo:
            if on_step:
                on_step(name)
            build_world(name, data_dir, profile)
        return todo
