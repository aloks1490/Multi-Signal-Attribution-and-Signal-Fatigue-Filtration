"""Daily Slack digest: one message to one channel through an incoming webhook (Block Kit)."""
from __future__ import annotations

from datetime import date

import requests

MAX_BLOCKS = 50  # Slack's limit per message


def esc(text: str) -> str:
    """Escape Slack mrkdwn control characters."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _link(app_url: str | None, account_id: str, label: str) -> str:
    if not app_url:
        return f"*{esc(label)}*"
    return f"*<{app_url.rstrip('/')}/account?account={account_id}|{esc(label)}>*"


def build_digest(as_of: date, profile: str, alerts: list[dict], handraises: list[dict], week: dict, app_url: str | None) -> dict:
    """alerts: dicts with account_id, company_name, owner_ae_id, score, fit_grade, alert_kind, narrative, people.
    handraises: dicts with account_id, company_name, owner_ae_id.
    week: alerts_this_week, capacity, held_by_cooldown, deferred."""
    title = f"Signal Engine · {as_of:%a %d %b %Y}"
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text":
            f"*{len(alerts)}* new account alerts · *{len(handraises)}* demo requests · profile *{esc(profile)}*"}]},
    ]
    if handraises:
        lines = "\n".join(f"• {_link(app_url, h['account_id'], h['company_name'])} asked for a demo · owner {esc(h['owner_ae_id'])}"
                          for h in handraises)
        blocks += [{"type": "section", "text": {"type": "mrkdwn", "text": f":rotating_light: *Act now: demo requests*\n{lines}"}}]

    by_ae: dict[str, list[dict]] = {}
    for a in alerts:
        by_ae.setdefault(a["owner_ae_id"], []).append(a)
    for ae in sorted(by_ae):
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{esc(ae)}* · {len(by_ae[ae])} new"}})
        for a in sorted(by_ae[ae], key=lambda x: -x["score"]):
            n = a["narrative"]
            people = {p["person_id"]: p for p in a["people"]}
            kind = " · :arrow_up: score jumped" if a["alert_kind"] == "jump" else ""
            why = "\n".join(f"• {esc(b)}" for b in n["why_now"])
            contacts = "; ".join(
                f"{esc(people[c['person_id']]['name'])} ({esc(people[c['person_id']]['title'])}): {esc(c['why'])}"
                for c in n["contact_first"] if c["person_id"] in people)
            text = (f"{_link(app_url, a['account_id'], a['company_name'])} · score {a['score']:.0f} · fit {a['fit_grade']}{kind}\n"
                    f"{esc(n['headline'])}\n{why}")
            if contacts:
                text += f"\n*Contact first:* {contacts}"
            text += f"\n*Angle:* {esc(n['angle'])}"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}})
    if not alerts and not handraises:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "No new alerts today. Quiet days are the point."}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
        f"This week: {week['alerts_this_week']} alerts of {week['capacity']} capacity · "
        f"held back by cooldown today: {week['held_by_cooldown']} · deferred by budget today: {week['deferred']}"}]})
    if len(blocks) > MAX_BLOCKS:
        blocks = blocks[:MAX_BLOCKS - 1] + [{"type": "context", "elements": [{"type": "mrkdwn", "text": "More alerts in the app."}]}]
    return {"text": f"{title}: {len(alerts)} new alerts", "blocks": blocks}


def post(webhook_url: str, payload: dict, timeout: int = 15) -> None:
    r = requests.post(webhook_url, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Slack webhook returned {r.status_code}: {r.text[:200]}")
