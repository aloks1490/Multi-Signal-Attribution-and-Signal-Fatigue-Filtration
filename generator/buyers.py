"""Positives: planted buyers (intent pattern before a meeting) and random converters (no pattern)."""
from __future__ import annotations

from datetime import timedelta

from generator import config as cfg
from generator import episodes
from generator.world import Account, World


def archetype_quota(w: World, n: int) -> list[str]:
    """Fixed archetype counts from ARCHETYPE_SHARE (largest remainder), shuffled, so small profiles keep the mix."""
    shares = cfg.ARCHETYPE_SHARE
    counts = {k: int(n * s) for k, s in shares.items()}
    by_remainder = sorted(shares, key=lambda k: n * shares[k] - counts[k], reverse=True)
    for k in by_remainder[: n - sum(counts.values())]:
        counts[k] += 1
    labels = [k for k, c in counts.items() for _ in range(c)]
    return [labels[i] for i in w.rng.permutation(n)]


def plant_buyers(w: World, accounts: list[Account]) -> None:
    for a, archetype in zip(accounts, archetype_quota(w, len(accounts))):
        meeting = w.random_day(cfg.EVAL_START + timedelta(days=14), cfg.EVAL_END)
        start = meeting - timedelta(days=int(w.rng.integers(cfg.INTENT_LEAD_DAYS[0], cfg.INTENT_LEAD_DAYS[1] + 1)))
        end = meeting - timedelta(days=1)

        if archetype == "committee":
            people = episodes.committee(w, a, start, end, with_product=w.rng.random() < 0.7)
        elif archetype == "quiet":
            people = episodes.quiet(w, a, start, end)
        else:
            people = episodes.plg(w, a, start, end)

        if w.rng.random() < cfg.BUYER_TRIGGER_PROB:
            kind = w.weighted_key({"new_sales_leader": 0.40, "sdr_job_post": 0.35, "funding_round": 0.25})
            max_lead = min(90, (start - cfg.SIM_START).days)
            t = w.ts_on(start - timedelta(days=int(w.rng.integers(min(5, max_lead), max_lead + 1))))
            if kind == "sdr_job_post":
                for _ in range(int(w.rng.integers(1, 4))):
                    w.emit_trigger(a, kind, t + timedelta(days=int(w.rng.integers(0, 10))), closed_at=None)
            else:
                w.emit_trigger(a, kind, t)

        if w.rng.random() < cfg.BUYER_DEMO_PROB:
            p = w.choice(people)
            ts = w.ts_on(meeting - timedelta(days=int(w.rng.integers(1, 8))))
            w.emit_web(a, "demo_request", ts, contact=p, known=True)

        w.set_truth(a, "planted_buyer", archetype, start, meeting)


def random_converters(w: World, accounts: list[Account]) -> None:
    for a in accounts:
        meeting = w.random_day(cfg.EVAL_START + timedelta(days=7), cfg.EVAL_END)
        if w.rng.random() < 0.5:
            ts = w.ts_on(meeting - timedelta(days=int(w.rng.integers(3, 30))))
            w.emit_web(a, "pricing_page", ts, contact=w.choice(a.contacts), known=False)
        w.set_truth(a, "random_converter", None, None, meeting)
