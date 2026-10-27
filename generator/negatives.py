"""Hard negatives: accounts that look partly like buyers but are not."""
from __future__ import annotations

from datetime import date, timedelta

from generator import config as cfg
from generator import episodes
from generator.world import Account, World


def window(w: World, min_len: int = 21) -> tuple[date, date]:
    start = w.random_day(cfg.EVAL_START, cfg.EVAL_END - timedelta(days=min_len))
    return start, start + timedelta(days=min_len)


def pricing_hammerer(w: World, a: Account) -> None:
    person = next((c for c in a.contacts if c.seniority == "ic"), a.contacts[0])
    start, _ = window(w)
    for d in range(int(w.rng.integers(10, 21))):
        day = start + timedelta(days=d)
        for _ in range(int(w.rng.integers(1, 5))):
            kind = "pricing_page" if w.rng.random() < 0.7 else "comparison_page"
            episodes.emit(w, a, kind, w.ts_on(day), person, known_share=0.7)


def bot_burst(w: World, a: Account) -> None:
    cookie = w.new_cookie()
    kinds = ["pricing_page", "security_page", "comparison_page", "integration_page", "blog_visit", "case_study_view", "unmapped_page"]
    for _ in range(int(w.rng.integers(1, 4))):
        t0 = w.ts_on(w.random_day(cfg.EVAL_START, cfg.EVAL_END))
        for _ in range(int(w.rng.integers(100, 301))):
            ts = t0 + timedelta(seconds=int(w.rng.integers(0, 1800)))
            if w.clamp(ts) is not None:
                w.emit_web(a, w.choice(kinds), ts, cookie=cookie, unmapped_share=0.0)


def trigger_only(w: World, a: Account) -> None:
    start, _ = window(w, 60)
    w.emit_trigger(a, "funding_round", w.ts_on(start))
    w.emit_trigger(a, "new_sales_leader", w.ts_on(start + timedelta(days=int(w.rng.integers(5, 40)))))
    for _ in range(int(w.rng.integers(2, 4))):
        w.emit_trigger(a, "sdr_job_post", w.ts_on(start + timedelta(days=int(w.rng.integers(10, 60)))))


def content_binger(w: World, a: Account) -> None:
    marketers = [c for c in a.contacts if c.function == "marketing"]
    while len(marketers) < 4:
        marketers.append(w.add_contact(a, function="marketing", seniority=w.choice(["manager", "ic"])))
    people = marketers[: int(w.rng.integers(4, min(8, len(marketers)) + 1))]
    start, end = window(w)
    kinds = {"blog_visit": 4, "webinar_attended": 2, "content_download": 2, "email_click": 2, "case_study_view": 1}
    for p in people:
        for _ in range(int(w.rng.integers(5, 16))):
            episodes.emit(w, a, w.weighted_key(kinds), episodes.ramp_ts(w, start, end), p)


def buyer_lookalike(w: World, a: Account) -> None:
    start, end = window(w, 28)
    episodes.committee(w, a, start, end, with_product=True)


def stalled_trial(w: World, a: Account) -> None:
    person = a.contacts[int(w.rng.integers(0, len(a.contacts)))]
    t0 = w.ts_on(w.random_day(cfg.EVAL_START, cfg.EVAL_END - timedelta(days=7)))
    episodes.emit_product(w, person.email, "trial_started", t0)
    episodes.emit_product(w, person.email, "mailbox_connected", t0 + timedelta(days=int(w.rng.integers(0, 3)), hours=1))


BUILDERS = {
    "pricing_hammerer": pricing_hammerer,
    "bot_burst": bot_burst,
    "trigger_only": trigger_only,
    "content_binger": content_binger,
    "low_fit_active": buyer_lookalike,
    "customer_active": buyer_lookalike,
    "open_deal_active": buyer_lookalike,
    "stalled_trial": stalled_trial,
}


def pool_for(neg_type: str, a: Account) -> bool:
    """Which accounts may carry each negative type."""
    clean = not (a.customer_status == "customer" or a.is_competitor or a.has_open_deal or a.do_not_contact)
    if neg_type == "low_fit_active":
        return clean and a.grade == "D"
    if neg_type == "customer_active":
        return a.customer_status == "customer"
    if neg_type == "open_deal_active":
        return a.has_open_deal
    if neg_type in ("trigger_only", "stalled_trial"):
        return clean and a.grade in ("A", "B")
    return clean and a.grade in ("A", "B", "C")


def plant_negatives(w: World, assignments: dict[str, list[Account]]) -> None:
    for neg_type, accounts in assignments.items():
        for a in accounts:
            BUILDERS[neg_type](w, a)
            w.set_truth(a, "hard_negative", neg_type)
