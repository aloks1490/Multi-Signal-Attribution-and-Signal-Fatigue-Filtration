"""Buying-pattern episodes. Used by planted buyers and by hard negatives that imitate them."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from generator import catalog
from generator.world import Account, Contact, World

COMMITTEE_KINDS = {
    "pricing_page": 3,
    "comparison_page": 2,
    "integration_page": 2,
    "case_study_view": 2,
    "security_page": 1,
    "blog_visit": 1,
    "email_click": 1,
    "webinar_attended": 0.5,
}
QUIET_KINDS = {"pricing_page": 3, "integration_page": 2, "comparison_page": 2, "case_study_view": 1, "security_page": 0.5}


def ramp_ts(w: World, start: date, end: date) -> datetime:
    """A timestamp in [start, end], skewed toward the end (activity accelerates)."""
    span = max((end - start).days, 1)
    offset = int(round(w.rng.beta(2.2, 1.0) * span))
    return w.ts_on(start + timedelta(days=offset))


def buying_people(w: World, a: Account, n: int) -> list[Contact]:
    """n contacts from sales/revops covering at least two seniorities; adds contacts if the account is thin."""
    pool = [c for c in a.contacts if c.function in catalog.BUYING_FUNCTIONS]
    seniorities = ["manager", "exec", "ic", "ic", "manager"]
    while len(pool) < n or len({c.seniority for c in pool}) < 2:
        pool.append(w.add_contact(a, function=w.choice(list(catalog.BUYING_FUNCTIONS)), seniority=seniorities[len(pool) % 5]))
    order = list(w.rng.permutation(len(pool)))
    picked = [pool[i] for i in order[:n]]
    if len({c.seniority for c in picked}) < 2:
        other = next(c for c in pool if c.seniority != picked[0].seniority)
        picked[-1] = other
    return picked


def emit(w: World, a: Account, kind: str, ts: datetime, person: Contact | None, known_share: float = 0.5) -> None:
    ts = w.clamp(ts)
    if ts is not None:
        w.emit_engagement(a, kind, ts, person, known_share=known_share)


def emit_product(w: World, email: str, name: str, ts: datetime) -> None:
    ts = w.clamp(ts)
    if ts is not None:
        w.emit_product(email, name, ts)


def committee(w: World, a: Account, start: date, end: date, with_product: bool = True) -> list[Contact]:
    people = buying_people(w, a, int(w.rng.integers(3, 6)))
    for i, p in enumerate(people):
        n = int(w.rng.integers(4, 13))
        for j in range(n):
            kind = "pricing_page" if (i == 0 and j == 0) else w.weighted_key(COMMITTEE_KINDS)
            emit(w, a, kind, ramp_ts(w, start, end), p)
    # A committee always spans channels: at least one email click alongside the web visits.
    emit(w, a, "email_click", ramp_ts(w, start, end), people[-1])
    if with_product:
        span = max((end - start).days, 4)
        champion = next((p for p in people if p.seniority == "manager"), people[0])
        t0 = w.ts_on(start + timedelta(days=int(span * 0.3)))
        emit_product(w, champion.email, "trial_started", t0)
        emit_product(w, champion.email, "mailbox_connected", t0 + timedelta(days=int(w.rng.integers(0, 3)), hours=1))
        emit_product(w, champion.email, "sequence_created", t0 + timedelta(days=int(w.rng.integers(1, 5)), hours=2))
        t_inv = t0 + timedelta(days=int(w.rng.integers(2, 7)), hours=3)
        invitee = next((p for p in people if p is not champion), None)
        invitee_email = invitee.email if invitee else w.outsider_email(a)
        emit_product(w, champion.email, "teammate_invited", t_inv)
        emit_product(w, invitee_email, "sequence_created", t_inv + timedelta(days=int(w.rng.integers(1, 4))))
        if w.rng.random() < 0.6:
            emit_product(w, champion.email, "crm_connected", t0 + timedelta(days=int(w.rng.integers(3, 11)), hours=4))
    return people


def quiet(w: World, a: Account, start: date, end: date) -> list[Contact]:
    people = buying_people(w, a, 2)
    for p in people:
        for _ in range(int(w.rng.integers(3, 9))):
            emit(w, a, w.weighted_key(QUIET_KINDS), ramp_ts(w, start, end), p)
    return people


def plg(w: World, a: Account, start: date, end: date) -> list[Contact]:
    people = buying_people(w, a, int(w.rng.integers(2, 5)))
    first = people[0]
    t0 = w.ts_on(start + timedelta(days=int(w.rng.integers(0, 4))))
    emit_product(w, first.email, "trial_started", t0)
    emit_product(w, first.email, "mailbox_connected", t0 + timedelta(hours=2))
    emit_product(w, first.email, "sequence_created", t0 + timedelta(days=1))
    for p in people[1:]:
        t_inv = ramp_ts(w, start, end)
        emit_product(w, first.email, "teammate_invited", t_inv)
        for _ in range(int(w.rng.integers(1, 4))):
            emit_product(w, p.email, "sequence_created", t_inv + timedelta(days=int(w.rng.integers(0, 6)), hours=1))
    if w.rng.random() < 0.7:
        emit_product(w, first.email, "crm_connected", ramp_ts(w, start, end))
    if w.rng.random() < 0.6:
        emit_product(w, first.email, "usage_limit_hit", w.ts_on(end - timedelta(days=int(w.rng.integers(0, 5)))))
    for _ in range(int(w.rng.integers(1, 3))):
        emit(w, a, "pricing_page", ramp_ts(w, start, end), first)
    return people
