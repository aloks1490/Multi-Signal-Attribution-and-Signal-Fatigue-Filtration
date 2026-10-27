"""T-G: the synthetic world has the shape the evaluation depends on."""
from __future__ import annotations

import csv
import hashlib
from datetime import timedelta
from pathlib import Path

import pandas as pd

from generator import catalog
from generator import config as cfg
from generator.__main__ import build
from generator.writer import frames

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "dbt_project" / "seeds"


def digest(fr: dict[str, pd.DataFrame]) -> str:
    h = hashlib.sha256()
    for name in sorted(fr):
        h.update(name.encode())
        h.update(pd.util.hash_pandas_object(fr[name].astype(str), index=False).values.tobytes())
    return h.hexdigest()


def first_party(fr) -> pd.DataFrame:
    """All web/product/marketing events with the account they belong to (by email domain or IP)."""
    accounts = fr["bronze.accounts"][["account_id", "domain"]]
    ipmap = fr["bronze.ip_company_map"]
    web = fr["bronze.web_events"].merge(ipmap, on="ip", how="left")
    web["domain"] = web["contact_email"].str.split("@").str[1].fillna(web["domain"])
    prod = fr["bronze.product_events"].assign(domain=lambda d: d["user_email"].str.split("@").str[1])
    mkt = fr["bronze.marketing_events"].assign(domain=lambda d: d["contact_email"].str.split("@").str[1])
    cols = ["event_id", "occurred_at", "domain"]
    allev = pd.concat([web[cols], prod[cols], mkt[cols]])
    return allev.merge(accounts, on="domain", how="inner")


def test_g1_same_seed_same_world(small_frames):
    assert digest(small_frames) == digest(frames(build("small", 42)))


def test_g2_different_seed_different_world(small_frames):
    assert digest(small_frames) != digest(frames(build("small", 7)))


def test_g3_referential_integrity(small_frames):
    acc = set(small_frames["bronze.accounts"]["account_id"])
    contacts = small_frames["bronze.contacts"]
    assert set(contacts["account_id"]) <= acc
    known = small_frames["bronze.web_events"]["contact_email"].dropna()
    assert set(known) <= set(contacts["email"])
    assert set(small_frames["bronze.marketing_events"]["contact_email"]) <= set(contacts["email"])
    assert set(small_frames["bronze.trigger_events"]["account_domain"]) <= set(small_frames["bronze.accounts"]["domain"])
    assert small_frames["bronze.accounts"]["domain"].is_unique
    assert contacts["email"].is_unique


def test_g4_events_inside_simulation(small_frames):
    for name in ("web_events", "product_events", "marketing_events", "trigger_events"):
        d = small_frames[f"bronze.{name}"]["occurred_at"].dt.date
        assert d.min() >= cfg.SIM_START and d.max() <= cfg.SIM_END, name


def test_g5_heavy_tail():
    fr = frames(build("standard", 42))
    per_account = first_party(fr).groupby("account_id").size().reindex(fr["bronze.accounts"]["account_id"], fill_value=0)
    top = per_account.sort_values(ascending=False)
    assert top.head(len(top) // 10).sum() >= 0.5 * top.sum()
    assert (per_account <= 3).mean() >= 0.40


def test_g6_triggers_not_exclusive_to_buyers(small_world, small_frames):
    truth = small_world.truth
    non_pos = small_frames["bronze.accounts"][~small_frames["bronze.accounts"]["account_id"].map(
        lambda a: truth.get(a, {}).get("truth_class") in ("planted_buyer", "random_converter"))]
    trig = small_frames["bronze.trigger_events"].merge(
        small_frames["bronze.accounts"][["account_id", "domain"]], left_on="account_domain", right_on="domain")
    trig = trig[trig["account_id"].isin(non_pos["account_id"])]
    n = len(non_pos)
    share = lambda t: trig.loc[trig["trigger_type"] == t, "account_id"].nunique() / n
    assert share("funding_round") >= 0.05
    assert share("new_sales_leader") >= 0.05
    assert share("sdr_job_post") >= 0.10


def test_g7_planted_buyer_shape(small_world, small_frames):
    fr = small_frames
    accounts = {a.account_id: a for a in small_world.accounts}
    planted = [t for t in small_world.truth.values() if t["truth_class"] == "planted_buyer"]
    assert {t["archetype"] for t in planted} == set(cfg.ARCHETYPE_SHARE)
    for t in planted:
        assert cfg.EVAL_START <= t["meeting_date"] <= cfg.EVAL_END
        lead = (t["meeting_date"] - t["intent_start_date"]).days
        assert cfg.INTENT_LEAD_DAYS[0] <= lead <= cfg.INTENT_LEAD_DAYS[1]
        if t["archetype"] != "committee":
            continue
        start, end = t["intent_start_date"], t["meeting_date"] - timedelta(days=1)
        a = accounts[t["account_id"]]
        by_cookie = {c.cookie: c.contact_id for c in a.contacts}
        by_email = {c.email: c.contact_id for c in a.contacts}

        def in_episode(df):
            return df[df["occurred_at"].dt.date.between(start, end)]

        web = in_episode(fr["bronze.web_events"])
        web = web[web["anonymous_id"].isin(by_cookie)]
        prod = in_episode(fr["bronze.product_events"])
        prod = prod[prod["user_email"].isin(by_email)]
        mkt = in_episode(fr["bronze.marketing_events"])
        mkt = mkt[mkt["contact_email"].isin(by_email)]

        people = {by_cookie[c] for c in web["anonymous_id"]} | {by_email[e] for e in prod["user_email"]} | {by_email[e] for e in mkt["contact_email"]}
        sources = {name for name, df in (("web", web), ("product", prod), ("marketing", mkt)) if len(df)}
        assert len(people) >= 3, t["account_id"]
        assert len(sources) >= 2, t["account_id"]


def test_g8_hard_negative_shapes(small_world, small_frames):
    fr = small_frames
    by_type = {}
    for t in small_world.truth.values():
        if t["truth_class"] == "hard_negative":
            by_type.setdefault(t["archetype"], []).append(t["account_id"])
    assert set(by_type) == set(cfg.NEGATIVE_TYPES)
    acc = {a.account_id: a for a in small_world.accounts}
    w = fr["bronze.web_events"]

    for aid in by_type["pricing_hammerer"]:
        cookies = {c.cookie for c in acc[aid].contacts}
        ev = w[w["anonymous_id"].isin(cookies) & w["page_path"].str.match(r"^/(pricing|vs/)")]
        per_person_days = ev.groupby("anonymous_id")["occurred_at"].apply(lambda s: s.dt.date.nunique())
        assert per_person_days.max() >= 10

    for aid in by_type["bot_burst"]:
        ev = w[w["ip"].isin(acc[aid].ips)].sort_values("occurred_at")
        bursts = ev.groupby("anonymous_id")["occurred_at"].agg(lambda s: (s.max() - s.min(), len(s)))
        assert any(n >= 100 for span, n in bursts if span <= pd.Timedelta(minutes=30) or n >= 100)

    domains = {acc[a].domain for a in by_type["trigger_only"]}
    fp = first_party(fr)
    assert not fp["domain"].isin(domains).any()
    assert fr["bronze.trigger_events"]["account_domain"].isin(domains).any()


def test_g9_emitted_names_exist_in_taxonomy(small_frames):
    taxonomy = {r["event_type"] for r in csv.DictReader((SEEDS / "signal_taxonomy.csv").open())}
    rules = [r["path_pattern"].replace("%", "") for r in csv.DictReader((SEEDS / "page_rules.csv").open())]
    for kind, paths in catalog.WEB_PAGES.items():
        if kind in ("unmapped_page", "ad_click"):
            continue
        for path in paths:
            assert any(path.startswith(prefix) for prefix in rules), path
    assert set(small_frames["bronze.product_events"]["event_name"]) <= taxonomy
    assert set(small_frames["bronze.marketing_events"]["event_name"]) <= taxonomy
    assert set(small_frames["bronze.trigger_events"]["trigger_type"]) <= taxonomy
    assert "ad_click" in taxonomy


def test_g10_generator_never_reads_weights():
    for f in (ROOT / "generator").glob("*.py"):
        text = f.read_text()
        assert "dbt_project" not in text and "signal_taxonomy" not in text and "scoring_params" not in text, f.name
