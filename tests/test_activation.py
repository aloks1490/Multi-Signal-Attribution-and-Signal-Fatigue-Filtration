"""M4: explanations (checker, fallbacks, cache), the Slack digest, the replay clock and the daily run."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from activation import narrate, slack
from activation.run import replay_date, run
from app import queries as q

ROOT = Path(__file__).resolve().parent.parent

FACTS = {
    "company": "Acme Corp", "industry": "Fintech", "employees": 240, "region": "EU", "crm": "HubSpot", "fit_grade": "A",
    "score": 62, "people_active_14d": 3, "anonymous_visitors_14d": 1, "activity_vs_usual": 4.2,
    "combos": ["evaluation"],
    "signals_14d": [{"signal": "pricing_page", "stage": "BOFU", "count": 4}, {"signal": "integration_page", "stage": "MOFU", "count": 2},
                    {"signal": "blog_visit", "stage": "TOFU", "count": 9}],
    "triggers_90d": [{"trigger": "new_sales_leader", "detail": "VP Sales", "date": "2026-08-01"}],
    "people": [{"person_id": "p1", "name": "Dana Reyes", "title": "VP Sales", "seniority": "exec", "did": ["pricing_page"], "last_seen": "2026-08-20"},
               {"person_id": "p2", "name": "Omar Haddad", "title": "RevOps Manager", "seniority": "manager", "did": ["integration_page"], "last_seen": "2026-08-21"}],
}
GOOD = {
    "headline": "Acme Corp has 3 people on pricing and integrations after a new VP Sales joined",
    "why_now": ["Pricing visited 4 times in 14 days", "RevOps checked the HubSpot integration", "Activity is 4.2 times usual"],
    "contact_first": [{"person_id": "p1", "why": "The new VP Sales is driving the evaluation"}],
    "angle": "Open with what a ramped SDR team costs and how Seqly cuts it.",
}
CFG = narrate.LLMConfig("https://example.invalid/v1", "key", "some-free-model")


def reply(obj) -> callable:
    return lambda cfg, facts: obj if isinstance(obj, str) else json.dumps(obj)


# ---------- checker ----------

def test_checker_accepts_grounded_output():
    assert narrate.check(GOOD, FACTS) == []


@pytest.mark.parametrize("mutate, expected", [
    (lambda o: o["contact_first"].__setitem__(0, {"person_id": "p9", "why": "x"}), "unknown person_id"),
    (lambda o: o.__setitem__("headline", "Acme Corp raised 25 million"), "numbers not in facts"),
    (lambda o: o["why_now"].__setitem__(0, "Their champion Priya Nair asked for a demo"), "name or term not in facts"),
    (lambda o: o.__setitem__("why_now", []), "why_now"),
    (lambda o: o.__setitem__("headline", "x" * 200), "headline"),
])
def test_checker_rejects_invented_content(mutate, expected):
    out = json.loads(json.dumps(GOOD))
    mutate(out)
    assert any(expected in p for p in narrate.check(out, FACTS))


def test_parse_handles_fences_and_prose():
    assert narrate.parse("Sure! ```json\n{\"a\": 1}\n``` hope that helps") == {"a": 1}


# ---------- narrate fallbacks ----------

def test_no_config_uses_template():
    n = narrate.narrate(FACTS, None)
    assert n.source == "template" and narrate.check(n.content, FACTS) == []


def test_good_reply_is_used():
    n = narrate.narrate(FACTS, CFG, reply(GOOD))
    assert n.source == "llm" and n.content == GOOD


@pytest.mark.parametrize("bad", ["not json at all", {**GOOD, "contact_first": [{"person_id": "p7", "why": "x"}]}])
def test_bad_reply_falls_back_to_template(bad):
    n = narrate.narrate(FACTS, CFG, reply(bad))
    assert n.source == "template" and n.problems


def test_api_error_falls_back_to_template():
    def boom(cfg, facts):
        raise TimeoutError("rate limited")
    n = narrate.narrate(FACTS, CFG, boom)
    assert n.source == "template" and "rate limited" in n.problems[0]


def test_template_leads_with_intent_not_noise():
    t = narrate.template(FACTS)
    assert "pricing_page" in t["headline"] and "blog_visit" not in t["headline"]
    assert t["contact_first"][0]["person_id"] == "p1"  # most senior active person


def test_config_from_env(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert narrate.LLMConfig.from_env() is None
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1/")
    cfg = narrate.LLMConfig.from_env()
    assert cfg.base_url == "https://integrate.api.nvidia.com/v1" and cfg.model == "m"


# ---------- Slack ----------

def test_digest_escapes_and_sections():
    alert = {"account_id": "a1", "company_name": "R&D <Labs>", "owner_ae_id": "ae_1", "score": 62.0, "fit_grade": "A",
             "alert_kind": "jump", "narrative": GOOD, "people": FACTS["people"]}
    week = {"alerts_this_week": 3, "capacity": 50, "held_by_cooldown": 1, "deferred": 0}
    p = slack.build_digest(date(2026, 8, 24), "broad", [alert], [{"account_id": "a2", "company_name": "Beta", "owner_ae_id": "ae_2"}],
                           week, "https://app.example.com")
    text = json.dumps(p)
    assert "R&amp;D &lt;Labs&gt;" in text
    assert "Act now: demo requests" in text and "score jumped" in text and "Dana Reyes" in text
    assert "https://app.example.com/account?account=a1" in text
    quiet = slack.build_digest(date(2026, 8, 24), "broad", [], [], week, None)
    assert "Quiet days are the point" in json.dumps(quiet)


# ---------- replay clock ----------

def test_replay_clock_walks_the_window_and_loops():
    p = {"eval_start": "2026-06-29", "eval_end": "2026-09-27", "replay_launch_date": "2026-11-02"}
    assert replay_date(p, date(2026, 11, 2)) == date(2026, 6, 29)
    assert replay_date(p, date(2026, 11, 7)) == date(2026, 7, 4)
    assert replay_date(p, date(2027, 2, 1)) == date(2026, 6, 29)  # 91 days later: loops


# ---------- daily run ----------

@pytest.fixture()
def act_env(small_db, tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNAL_APP_STATE", str(tmp_path / "state.duckdb"))
    for var in ("LLM_API_KEY", "LLM_MODEL", "SLACK_WEBHOOK_URL", "APP_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    day = q.df(small_db, "select alert_date, count(*) n from gold.engine_alerts where is_active group by 1 order by n desc limit 1")
    return {"db": small_db, "day": day.alert_date[0].date(), "out": tmp_path / "out"}


def test_dry_run_writes_digest_and_posts_nothing(act_env):
    posted = []
    r = run(act_env["db"], act_env["day"], out_dir=act_env["out"], poster=lambda url, p: posted.append(p))
    assert r["status"] == "dry_run" and r["alerts"] >= 1 and not posted
    payload = json.loads(Path(r["file"]).read_text())
    assert payload["blocks"][0]["type"] == "header"


def test_post_once_then_skip_unless_forced(act_env, monkeypatch):
    from app import state

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.invalid/T/B/x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    posted, calls = [], []

    def fake_llm(cfg, facts):
        calls.append(1)
        return "no json"  # forces the template, still counts as a call

    first = run(act_env["db"], act_env["day"], out_dir=act_env["out"], caller=fake_llm, poster=lambda u, p: posted.append(p))
    second = run(act_env["db"], act_env["day"], out_dir=act_env["out"], caller=fake_llm, poster=lambda u, p: posted.append(p))
    forced = run(act_env["db"], act_env["day"], out_dir=act_env["out"], force=True, caller=fake_llm, poster=lambda u, p: posted.append(p))
    assert (first["status"], second["status"], forced["status"]) == ("posted", "skipped_already_posted", "posted")
    assert len(posted) == 2
    assert list(state.activation_log().status) == ["posted", "skipped_already_posted", "posted"][::-1]


def test_llm_results_are_cached(act_env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    calls = []

    def good_template_shaped(cfg, facts):
        calls.append(1)
        return json.dumps(narrate.template(facts))  # grounded by construction, so the checker accepts it

    run(act_env["db"], act_env["day"], out_dir=act_env["out"], caller=good_template_shaped)
    n = len(calls)
    second = run(act_env["db"], act_env["day"], out_dir=act_env["out"], caller=good_template_shaped)
    assert n >= 1 and len(calls) == n and second["narratives"]["cached"] == n


def test_activation_never_reads_truth_labels():
    for f in (ROOT / "activation").glob("*.py"):
        text = f.read_text()
        assert "labels." not in text and "account_truth" not in text, f.name
