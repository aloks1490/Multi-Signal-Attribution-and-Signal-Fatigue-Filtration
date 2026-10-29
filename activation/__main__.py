"""CLI: python -m activation --db data/holdout.duckdb [--as-of 2026-08-03] [--dry-run] [--force]"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from activation.run import run


def main() -> None:
    ap = argparse.ArgumentParser(description="Explain today's alerts and post the Slack digest.")
    ap.add_argument("--db", default="data/holdout.duckdb")
    ap.add_argument("--as-of", type=date.fromisoformat, help="day to replay (default: the replay clock)")
    ap.add_argument("--dry-run", action="store_true", help="never post; write the digest file only")
    ap.add_argument("--force", action="store_true", help="post even if this day was already posted")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    result = run(args.db, args.as_of, args.dry_run, Path(args.out), args.force)
    print(" · ".join(f"{k}={v}" for k, v in result.items()))


if __name__ == "__main__":
    main()
