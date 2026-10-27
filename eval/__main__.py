"""CLI.

python -m eval calibrate --db data/dev.duckdb
python -m eval report --run dev=data/dev.duckdb:seed42 --run holdout=data/holdout.duckdb:seed7
"""
from __future__ import annotations

import argparse
from pathlib import Path

from eval import calibrate, report

N_AES = 5
SEED_CSV = Path(__file__).resolve().parent.parent / "dbt_project" / "seeds" / "scoring_params.csv"


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate", help="set engine and points thresholds from rep capacity (writes scoring_params.csv)")
    c.add_argument("--db", required=True)
    r = sub.add_parser("report", help="write docs/results.md")
    r.add_argument("--run", action="append", required=True, help="name=path/to.duckdb:note")
    r.add_argument("--out", default="docs/results.md")
    args = ap.parse_args()

    if args.cmd == "calibrate":
        result = calibrate.run(args.db, SEED_CSV, N_AES)
        print("calibrated:", {k: round(v, 4) for k, v in result.items()}, "→", SEED_CSV)
    else:
        runs = {}
        for spec in args.run:
            name, rest = spec.split("=", 1)
            path, _, note = rest.partition(":")
            runs[name] = (path, note or name)
        print(report.write(runs, Path(args.out), N_AES))


if __name__ == "__main__":
    main()
