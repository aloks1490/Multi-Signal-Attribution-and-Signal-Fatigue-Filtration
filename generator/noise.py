"""Heavy-tailed background activity and background triggers for every account."""
from __future__ import annotations

from datetime import timedelta

import numpy as np

from generator import catalog
from generator import config as cfg
from generator.world import Account, World


def event_count(w: World, level: str) -> int:
    if level == "unaware":
        return int(w.rng.integers(0, 4))
    if level == "low":
        return int(w.rng.integers(5, 31))
    return int(np.clip(w.rng.lognormal(np.log(80), 0.8), 30, 300))


def background_activity(w: World, a: Account) -> None:
    level = w.weighted_key(cfg.AWARENESS_SHARE)
    for _ in range(event_count(w, level)):
        kind = w.weighted_key(cfg.NOISE_MIX)
        ts = w.random_ts(cfg.SIM_START, cfg.SIM_END)
        r = w.rng.random()
        if kind in catalog.MARKETING_EVENTS:
            w.emit_marketing(w.choice(a.contacts), kind, ts)
        elif r < cfg.KNOWN_WEB_SHARE:
            w.emit_web(a, kind, ts, contact=w.choice(a.contacts), known=True)
        elif r < cfg.KNOWN_WEB_SHARE + 0.3:
            w.emit_web(a, kind, ts, contact=w.choice(a.contacts), known=False)
        else:
            w.emit_web(a, kind, ts)  # stranger at the company

    if w.rng.random() < cfg.NOISE_TRIAL_PROB[level]:
        person = w.choice(a.contacts)
        t0 = w.random_ts(cfg.SIM_START, cfg.SIM_END)
        w.emit_product(person.email, "trial_started", t0)
        if w.rng.random() < 0.5:
            _maybe(w, person.email, "mailbox_connected", t0 + timedelta(days=int(w.rng.integers(0, 4)), hours=1))
        if w.rng.random() < 0.3:
            _maybe(w, person.email, "sequence_created", t0 + timedelta(days=int(w.rng.integers(1, 8)), hours=2))

    if a.customer_status == "customer":
        users = [a.contacts[i] for i in w.rng.permutation(len(a.contacts))[: int(w.rng.integers(2, 7))]]
        for _ in range(int(w.rng.integers(10, 41))):
            name = w.weighted_key({"sequence_created": 6, "mailbox_connected": 1, "teammate_invited": 1, "crm_connected": 1})
            w.emit_product(w.choice(users).email, name, w.random_ts(cfg.SIM_START, cfg.SIM_END))


def background_triggers(w: World, a: Account) -> None:
    for kind, rate in cfg.TRIGGER_RATES.items():
        if w.rng.random() >= rate:
            continue
        if kind == "sdr_job_post":
            for _ in range(int(w.rng.integers(1, 5))):
                posted = w.random_ts(cfg.SIM_START, cfg.SIM_END)
                closed = posted + timedelta(days=int(w.rng.integers(20, 61)))
                w.emit_trigger(a, kind, posted, closed if closed.date() <= cfg.SIM_END else None)
        else:
            w.emit_trigger(a, kind, w.random_ts(cfg.SIM_START, cfg.SIM_END))


def _maybe(w: World, email: str, name: str, ts) -> None:
    ts = w.clamp(ts)
    if ts is not None:
        w.emit_product(email, name, ts)
