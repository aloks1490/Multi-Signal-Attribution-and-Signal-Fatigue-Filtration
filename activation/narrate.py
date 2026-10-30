"""Alert explanations: an LLM writes them from a fact sheet; a checker rejects anything not in the facts.

Provider-neutral: any OpenAI-compatible chat endpoint (OpenRouter, NVIDIA NIM, ...), set by environment:
    LLM_BASE_URL   e.g. https://openrouter.ai/api/v1 or https://integrate.api.nvidia.com/v1
    LLM_API_KEY
    LLM_MODEL      the provider's model id (free models change often; pick from the provider's catalog)
    LLM_EXTRA_BODY optional JSON merged into each request for model-specific switches, e.g. to turn off
                   Nemotron 3's hidden reasoning: {"chat_template_kwargs": {"enable_thinking": false}}
Without a key or model, or when the model fails or the checker rejects its output, the deterministic
template is used, so the pipeline never depends on a free endpoint being up.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Callable

import requests

SYSTEM = """You write short sales alerts for account executives at Seqly, a sales-engagement platform.
You get a JSON fact sheet about one company. Use ONLY those facts: never invent people, titles, numbers, dates,
tools or events. Return one JSON object and nothing else, with exactly these keys:
  "headline": one sentence, at most 140 characters, saying why this account matters now
  "why_now": a list of 2 or 3 short bullet strings, each grounded in a listed signal, trigger or combo
  "contact_first": a list of 1 or 2 objects {"person_id": an id from facts.people, "why": one short sentence}
  "angle": one sentence suggesting how to open the conversation, framed for the first contact's role
Write plainly. No greetings, no markdown, no emojis."""

COMMON_WORDS = {
    "the", "this", "that", "they", "their", "them", "there", "these", "with", "and", "but", "for", "from", "after",
    "before", "since", "while", "when", "who", "what", "why", "how", "lead", "open", "start", "ask", "offer", "show",
    "share", "mention", "reach", "focus", "highlight", "position", "frame", "use", "point", "suggest", "follow",
    "strong", "three", "two", "four", "five", "multiple", "several", "recent", "recently", "new", "active", "both",
    "their", "its", "his", "her", "a", "an", "as", "at", "by", "in", "of", "on", "to", "is", "are", "was", "has",
    "have", "had", "be", "been", "it", "if", "or", "not", "no", "yes", "all", "any", "one", "more", "most", "than",
    "seqly", "ae", "aes", "sdr", "sdrs", "bdr", "vp", "cro", "ceo", "cto", "cfo", "cmo", "revops", "roi", "crm",
    "api", "gdpr", "q1", "q2", "q3", "q4", "head", "manager", "team", "teams", "sales", "pricing", "security",
    "integration", "integrations", "trial", "demo", "buying", "committee", "evaluation", "outbound", "pipeline",
}


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: int = 90
    max_tokens: int = 2000  # reasoning models spend part of this on hidden thinking before the answer
    extra_body: dict | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig | None":
        key, model = os.environ.get("LLM_API_KEY"), os.environ.get("LLM_MODEL")
        if not key or not model:
            return None
        extra = os.environ.get("LLM_EXTRA_BODY", "").strip()
        return cls(os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"), key, model,
                   max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2000")), extra_body=json.loads(extra) if extra else None)


# ---------- facts ----------

STAGE_RANK = {"BOFU": 0, "MOFU": 1, "TOFU": 2, "NONE": 3}


def facts_from_context(ctx: dict) -> dict:
    """The fact sheet sent to the model: a compact, JSON-safe view of one gold.alert_context row.
    Signals and each person's actions are ordered high-intent first, so cheap top-of-funnel noise never leads."""
    signals = sorted(ctx.get("signal_counts") or [], key=lambda s: (STAGE_RANK.get(s["stage"], 9), -int(s["n"]), s["signal"]))
    stage = {s["signal"]: s["stage"] for s in signals}
    people = []
    for i, p in enumerate(ctx.get("people") or [], start=1):
        did = sorted(p["did"], key=lambda e: (STAGE_RANK.get(stage.get(e, "NONE"), 9), e))
        people.append({"person_id": f"p{i}", "name": p["name"], "title": p["title"], "seniority": p["seniority"],
                       "did": did, "last_seen": str(p["last_seen"])})
    return {
        "company": ctx["company_name"],
        "industry": ctx["industry"],
        "employees": int(ctx["employee_count"]),
        "region": ctx["region"],
        "crm": ctx["crm"],
        "fit_grade": ctx["fit_grade"],
        "score": round(float(ctx["engine_score"])),
        "people_active_14d": int(ctx["people_14d"]),
        "anonymous_visitors_14d": int(ctx["anonymous_visitors"]),
        "activity_vs_usual": round(float(ctx["spike_ratio"]), 1),
        "combos": [c for c in (ctx.get("combos") or "").split(" + ") if c],
        "signals_14d": [{"signal": s["signal"], "stage": s["stage"], "count": int(s["n"])} for s in signals],
        "triggers_90d": [{"trigger": t["trigger"], "detail": t["detail"], "date": str(t["on_date"])} for t in (ctx.get("triggers") or [])],
        "people": people,
    }


def facts_hash(facts: dict) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()[:16]


# ---------- model call ----------

def call_llm(cfg: LLMConfig, facts: dict) -> str:
    """One chat completion. Asks for JSON mode first; some free models reject it, so retry without."""
    body = {
        "model": cfg.model,
        "temperature": 0.2,
        "max_tokens": cfg.max_tokens,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
        **(cfg.extra_body or {}),
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    url = f"{cfg.base_url}/chat/completions"
    r = requests.post(url, json={**body, "response_format": {"type": "json_object"}}, headers=headers, timeout=cfg.timeout)
    if r.status_code == 400:
        r = requests.post(url, json=body, headers=headers, timeout=cfg.timeout)
    r.raise_for_status()
    choice = r.json()["choices"][0]
    message = choice.get("message") or {}
    content = message.get("content")
    if not content:
        # Reasoning models can use the whole budget thinking and return no answer.
        raise ValueError(f"empty reply (finish_reason={choice.get('finish_reason')}, message keys={sorted(message)})")
    return content


def parse(text: str) -> dict:
    """Extract the JSON object from a reply that may carry code fences or stray prose."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


# ---------- checker ----------

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def _fact_numbers(facts: dict) -> set[str]:
    """Numbers in the facts plus harmless rewordings: '09' → '9', '4.0' → '4', and the parts of ISO dates."""
    nums = _numbers(facts)
    out = set(nums)
    for n in nums:
        out.add(str(int(float(n))) if float(n) == int(float(n)) else n)
    for y, m, d in re.findall(r"(\d{4})-(\d{2})-(\d{2})", json.dumps(facts)):
        out |= {y, str(int(m)), str(int(d))}
    return out


def _fact_words(facts: dict) -> set[str]:
    """Words in the facts plus month names of the dates they contain ('2026-06-09' allows 'June' and 'Jun')."""
    words = _words(facts)
    for _, m, _ in re.findall(r"(\d{4})-(\d{2})-(\d{2})", json.dumps(facts)):
        name = MONTHS[int(m) - 1]
        words |= {name, name[:3]}
    return words


def _numbers(value) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", json.dumps(value, ensure_ascii=False)))  # ASCII escapes like \u00b7 hold digits


def _words(value) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z&'.-]+", json.dumps(value, ensure_ascii=False))}


def check(out: dict, facts: dict) -> list[str]:
    """Reasons to reject the model's output. Empty list = accepted."""
    problems = []
    if not isinstance(out.get("headline"), str) or not 0 < len(out["headline"]) <= 160:
        problems.append("headline missing or too long")
    if not isinstance(out.get("why_now"), list) or not 1 <= len(out["why_now"]) <= 3 or not all(isinstance(b, str) for b in out["why_now"]):
        problems.append("why_now must be 1-3 strings")
    if not isinstance(out.get("angle"), str) or not out["angle"]:
        problems.append("angle missing")
    ids = {p["person_id"] for p in facts["people"]}
    contacts = out.get("contact_first")
    if not isinstance(contacts, list) or not 1 <= len(contacts) <= 2:
        problems.append("contact_first must have 1-2 entries")
    else:
        for c in contacts:
            if not isinstance(c, dict) or c.get("person_id") not in ids:
                problems.append(f"unknown person_id {c.get('person_id') if isinstance(c, dict) else c!r}")
    if problems:
        return problems

    text = {"headline": out["headline"], "why_now": out["why_now"], "angle": out["angle"],
            "why": [c.get("why", "") for c in contacts]}
    invented_numbers = _numbers(text) - _fact_numbers(facts) - {"1", "2", "3", "14", "90"}
    if invented_numbers:
        problems.append(f"numbers not in facts: {sorted(invented_numbers)}")
    known = _fact_words(facts) | COMMON_WORDS
    for sentence in [out["headline"], *out["why_now"], out["angle"], *text["why"]]:
        words = re.findall(r"[A-Za-z][A-Za-z&'’.-]+", sentence)
        for w in words[1:]:  # the first word of a sentence is capitalised anyway
            if w[0].isupper() and not _is_known(w, known):
                problems.append(f"name or term not in facts: {w}")
    return problems


def _is_known(word: str, known: set[str]) -> bool:
    """A word is known if it, or a plain grammatical form of it, is: possessive (Seqly's), plural (BDRs),
    or every capitalised part of a hyphenated word (A-grade, SDR-related)."""
    w = word.lower().strip(".'’")
    w = re.sub(r"['’]s$", "", w)
    forms = {w, w[:-1] if w.endswith("s") else w}
    if any(f in known for f in forms):
        return True
    # Hyphenated: only capitalised parts can be names (SDR-related → check "SDR"; "related" is ordinary English).
    parts = [p for p in word.strip(".'’").split("-") if p]
    return len(parts) > 1 and all(_is_known(p, known) or len(p) == 1 or not p[0].isupper() for p in parts)


# ---------- template fallback ----------

ANGLES = {
    "pricing_page": "Open with cost: what a ramped SDR team costs today and what Seqly changes.",
    "comparison_page": "They are comparing tools: lead with what makes switching easy.",
    "security_page": "Security is on their mind: offer the security pack and a call with your solutions engineer.",
    "integration_page": "They are checking the CRM integration: offer a short sync walkthrough.",
    "teammate_invited": "The trial is spreading: offer to help set up the team's first sequences.",
    "usage_limit_hit": "They hit the trial limit: offer a plan that fits the team size.",
}


def template(facts: dict) -> dict:
    signals = [s["signal"] for s in facts["signals_14d"]]
    intent = [s["signal"] for s in facts["signals_14d"] if s["stage"] in ("BOFU", "MOFU")] or signals
    bullets = []
    if facts["people_active_14d"] > 1:
        bullets.append(f"{facts['people_active_14d']} people active in the last 14 days")
    if intent:
        bullets.append("Highest-intent activity: " + ", ".join(intent[:3]))
    if facts["triggers_90d"]:
        t = facts["triggers_90d"][0]
        bullets.append(f"{t['trigger']}: {t['detail']} ({t['date']})")
    if facts["combos"]:
        bullets.append("Pattern: " + " + ".join(facts["combos"]))
    order = {"exec": 0, "manager": 1, "ic": 2}
    people = sorted(facts["people"], key=lambda p: (order.get(p["seniority"], 3), p["last_seen"]))
    contacts = [{"person_id": p["person_id"], "why": "most senior active person; recently on " + ", ".join(p["did"][:2])} for p in people[:1]]
    angle = next((ANGLES[s] for s in intent if s in ANGLES), "Reference their recent activity and ask what prompted it.")
    return {
        "headline": f"{facts['company']}: {facts['score']} · fit {facts['fit_grade']} · " + (", ".join(intent[:2]) or "rising activity"),
        "why_now": bullets[:3] or ["Score crossed the alert threshold"],
        "contact_first": contacts,
        "angle": angle,
    }


# ---------- entry point ----------

@dataclass
class Narrative:
    content: dict
    source: str  # "llm" or "template"
    model: str | None
    problems: list[str]


def narrate(facts: dict, cfg: LLMConfig | None, caller: Callable[[LLMConfig, dict], str] = call_llm) -> Narrative:
    if cfg is None:
        return Narrative(template(facts), "template", None, ["no LLM configured"])
    try:
        out = parse(caller(cfg, facts))
    except Exception as e:  # network, rate limit, bad JSON: never block the digest
        return Narrative(template(facts), "template", cfg.model, [f"llm error: {type(e).__name__}: {str(e)[:200]}"])
    problems = check(out, facts)
    if problems:
        return Narrative(template(facts), "template", cfg.model, problems)
    return Narrative(out, "llm", cfg.model, [])

