"""CLI: python -m generator --profile standard --seed 42 --db data/dev.duckdb"""
from __future__ import annotations

import argparse
from collections import Counter

from generator import buyers, negatives, noise, writer
from generator import config as cfg
from generator.world import Account, World


def pick(w: World, pool: list[Account], n: int, what: str) -> list[Account]:
    if len(pool) < n:
        raise ValueError(f"not enough accounts for {what}: need {n}, have {len(pool)}")
    idx = w.rng.choice(len(pool), size=n, replace=False)
    return [pool[i] for i in sorted(idx)]


def build(profile_name: str, seed: int) -> World:
    profile = cfg.PROFILES[profile_name]
    w = World(seed, profile)
    w.build_accounts()
    taken: set[str] = set()

    def free(pred) -> list[Account]:
        return [a for a in w.accounts if a.account_id not in taken and pred(a)]

    neg_assign: dict[str, list[Account]] = {}
    for t in cfg.NEGATIVE_TYPES:
        chosen = pick(w, free(lambda a, t=t: negatives.pool_for(t, a)), profile.n_per_negative_type, t)
        neg_assign[t] = chosen
        taken.update(a.account_id for a in chosen)

    n_ab = round(profile.n_planted * 0.8)
    planted = pick(w, free(lambda a: not a.excluded and a.grade in ("A", "B")), n_ab, "planted A/B")
    taken.update(a.account_id for a in planted)
    planted_c = pick(w, free(lambda a: not a.excluded and a.grade == "C"), profile.n_planted - n_ab, "planted C")
    taken.update(a.account_id for a in planted_c)
    converters = pick(w, free(lambda a: not a.excluded), profile.n_random_converters, "random converters")
    taken.update(a.account_id for a in converters)

    silent = {a.account_id for a in neg_assign["trigger_only"]}
    for a in w.accounts:
        if a.account_id not in silent:
            noise.background_activity(w, a)
        noise.background_triggers(w, a)

    negatives.plant_negatives(w, neg_assign)
    buyers.plant_buyers(w, planted + planted_c)
    buyers.random_converters(w, converters)
    return w


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the synthetic GTM world into DuckDB.")
    ap.add_argument("--profile", choices=sorted(cfg.PROFILES), default="standard")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--db", default="data/dev.duckdb")
    args = ap.parse_args()

    w = build(args.profile, args.seed)
    counts = writer.write(w, args.db)
    print(f"profile={args.profile} seed={args.seed} → {args.db}")
    for name, n in counts.items():
        print(f"  {name:28s} {n:>9,}")
    classes = Counter(t["truth_class"] for t in w.truth.values())
    print("  truth:", dict(classes), f"noise={len(w.accounts) - sum(classes.values())}")


if __name__ == "__main__":
    main()
