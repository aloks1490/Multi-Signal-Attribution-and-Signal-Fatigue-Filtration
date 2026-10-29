"""M2: pattern rules behave as designed on the hard negatives and buyers of the small world."""
from __future__ import annotations

import pytest

ACTIVITY_MULT = "m_breadth * m_sources * m_spike * m_gate"


def accounts_of(con, archetype: str) -> list[str]:
    return [r[0] for r in con.execute(
        "select account_id from labels.account_truth where archetype = ?", [archetype]).fetchall()]


@pytest.mark.parametrize("archetype", ["pricing_hammerer", "stalled_trial"])
def test_single_person_accounts_are_damped(con, archetype):
    """One person can't carry an account: on its most active day the activity multiplier is below 1."""
    for aid in accounts_of(con, archetype):
        mult, people = con.execute(f"""
            select {ACTIVITY_MULT}, people_14d from gold.account_daily_scores
            where account_id = ? order by activity_score desc, score_date limit 1""", [aid]).fetchone()
        if people <= 1:
            assert mult < 1.0, aid


def test_content_bingers_get_no_boost_without_bofu(con):
    rows = con.execute(f"""
        select s.account_id, s.score_date, {ACTIVITY_MULT}
        from gold.account_daily_scores s
        join labels.account_truth t using (account_id)
        where t.archetype = 'content_binger' and s.bofu_people_14d = 0 and s.activity_score > 0""").fetchall()
    assert rows
    assert all(m < 1.0 for _, _, m in rows)


def test_triggers_alone_earn_no_combo(con):
    bonus = con.execute("""
        select coalesce(max(s.combo_bonus), 0)
        from gold.account_daily_scores s
        join labels.account_truth t using (account_id)
        where t.archetype = 'trigger_only'""").fetchone()[0]
    assert bonus == 0


def test_committee_buyers_get_boosted(con):
    for aid in accounts_of(con, "committee"):
        best = con.execute(f"""
            select max({ACTIVITY_MULT}), max(combo_bonus), max(engine_score / nullif(engine_score_m1, 0))
            from gold.account_daily_scores s
            join labels.account_truth t using (account_id)
            where s.account_id = ? and s.score_date between t.intent_start_date and t.meeting_date""", [aid]).fetchone()
        assert best[0] > 1.0 and best[1] > 0 and best[2] > 1.0, (aid, best)


def test_alert_reasons_name_signals(con):
    reasons = [r[0] for r in con.execute("select reason from gold.engine_alerts").fetchall()]
    assert reasons
    assert all(" · fit " in r and ("_page" in r or "_" in r) for r in reasons)
