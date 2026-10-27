"""Accounts, contacts, IPs and the event emitter shared by noise, buyers and negatives."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
from faker import Faker

from generator import catalog
from generator import config as cfg


@dataclass
class Contact:
    contact_id: str
    account_id: str
    email: str
    first_name: str
    last_name: str
    title: str
    seniority: str
    function: str
    cookie: str  # web anonymous_id; the CRM never sees it


@dataclass
class Account:
    account_id: str
    company_name: str
    domain: str
    industry: str
    employee_count: int
    sales_headcount: int
    region: str
    crm: str
    tech_stack: list[str]
    customer_status: str
    is_competitor: bool
    has_open_deal: bool
    do_not_contact: bool
    owner_ae_id: str
    grade: str
    ips: list[str]
    contacts: list[Contact] = field(default_factory=list)

    @property
    def excluded(self) -> bool:
        return (
            self.customer_status == "customer"
            or self.is_competitor
            or self.has_open_deal
            or self.do_not_contact
            or self.grade == "D"
        )


class World:
    """Holds the generated entities and collects raw events for the bronze tables."""

    def __init__(self, seed: int, profile: cfg.Profile):
        self.seed = seed
        self.profile = profile
        self.rng = np.random.default_rng(seed)
        self.fake = Faker()
        self.fake.seed_instance(seed)
        self.accounts: list[Account] = []
        self.web: list[dict] = []
        self.product: list[dict] = []
        self.marketing: list[dict] = []
        self.triggers: list[dict] = []
        self.truth: dict[str, dict] = {}
        self.isp_ips: list[str] = []
        self._used_domains: set[str] = set()
        self._used_ips: set[str] = set()
        self._cookie_n = 0

    # ---------- random helpers ----------

    def choice(self, items, p=None):
        idx = self.rng.choice(len(items), p=p)
        return items[idx]

    def weighted_key(self, weights: dict):
        keys = list(weights)
        w = np.array([weights[k] for k in keys], dtype=float)
        return keys[self.rng.choice(len(keys), p=w / w.sum())]

    def new_cookie(self) -> str:
        self._cookie_n += 1
        return f"ck_{self.seed}_{self._cookie_n:07d}"

    def new_ip(self) -> str:
        while True:
            ip = f"{self.rng.integers(11, 223)}.{self.rng.integers(0, 256)}.{self.rng.integers(0, 256)}.{self.rng.integers(1, 255)}"
            if ip not in self._used_ips:
                self._used_ips.add(ip)
                return ip

    def random_day(self, start: date, end: date) -> date:
        """Weekday-weighted random date in [start, end]."""
        n = (end - start).days + 1
        days = [start + timedelta(days=i) for i in range(n)]
        w = np.array([1.0 if d.weekday() < 5 else 0.3 for d in days])
        return days[self.rng.choice(n, p=w / w.sum())]

    def ts_on(self, d: date) -> datetime:
        hour = int(np.clip(self.rng.normal(13, 3), 6, 22))
        return datetime(d.year, d.month, d.day, hour, int(self.rng.integers(0, 60)), int(self.rng.integers(0, 60)))

    def random_ts(self, start: date, end: date) -> datetime:
        return self.ts_on(self.random_day(start, end))

    # ---------- world building ----------

    def build_accounts(self) -> None:
        grades = list(cfg.GRADE_SHARE)
        shares = np.array([cfg.GRADE_SHARE[g] for g in grades])
        for i in range(self.profile.n_accounts):
            grade = grades[self.rng.choice(len(grades), p=shares)]
            lo, hi = cfg.GRADE_POINTS[grade]
            points = int(self.rng.integers(lo, hi + 1))
            self.accounts.append(self._account(i, grade, points))

        # Status flags, mutually exclusive, never on competitors.
        order = self.rng.permutation(len(self.accounts))
        n = len(self.accounts)
        n_cust, n_deal, n_dnc = round(n * cfg.CUSTOMER_SHARE), round(n * cfg.OPEN_DEAL_SHARE), max(1, round(n * cfg.DNC_SHARE))
        comp_idx = order[: cfg.N_COMPETITORS]
        cust_idx = order[cfg.N_COMPETITORS : cfg.N_COMPETITORS + n_cust]
        deal_idx = order[cfg.N_COMPETITORS + n_cust : cfg.N_COMPETITORS + n_cust + n_deal]
        dnc_idx = order[cfg.N_COMPETITORS + n_cust + n_deal : cfg.N_COMPETITORS + n_cust + n_deal + n_dnc]
        for k, i in enumerate(comp_idx):
            a = self.accounts[i]
            a.is_competitor = True
            a.company_name = catalog.COMPETITOR_NAMES[k % len(catalog.COMPETITOR_NAMES)]
            a.industry = "B2B Software"
        for i in cust_idx:
            self.accounts[i].customer_status = "customer"
        for i in deal_idx:
            self.accounts[i].has_open_deal = True
        for i in dnc_idx:
            self.accounts[i].do_not_contact = True

        for a in self.accounts:
            self._contacts(a)
        self.isp_ips = [self.new_ip() for _ in range(200)]

    def _account(self, i: int, grade: str, points: int) -> Account:
        # Split the target points into size (0-2) + four binary attributes.
        size_pts = int(self.rng.integers(max(0, points - 4), min(2, points) + 1))
        flags = [1] * (points - size_pts) + [0] * (4 - (points - size_pts))
        self.rng.shuffle(flags)
        ind_ok, reg_ok, crm_ok, sales_ok = flags

        if size_pts == 2:
            employees = int(self.rng.integers(50, 1001))
        elif size_pts == 1:
            employees = int(self.rng.integers(20, 50)) if self.rng.random() < 0.5 else int(self.rng.integers(1001, 5001))
        else:
            employees = int(self.rng.integers(10, 20)) if self.rng.random() < 0.5 else int(self.rng.integers(5001, 50001))

        if sales_ok:
            sales = int(self.rng.integers(5, max(6, min(employees // 3, 400)) + 1))
        else:
            sales = int(self.rng.integers(0, 5))

        name = self.fake.company()
        domain = self._domain(name)
        stack = list(self.rng.choice(catalog.OTHER_TOOLS, size=int(self.rng.integers(1, 5)), replace=False))
        if self.rng.random() < 0.25:
            stack.append(self.choice(catalog.COMPETITOR_TOOLS))
        crm = self.choice(catalog.TARGET_CRMS) if crm_ok else self.choice(catalog.OTHER_CRMS)

        return Account(
            account_id=f"acc_{i + 1:05d}",
            company_name=name,
            domain=domain,
            industry=self.choice(catalog.TARGET_INDUSTRIES if ind_ok else catalog.OTHER_INDUSTRIES),
            employee_count=employees,
            sales_headcount=sales,
            region=self.choice(catalog.TARGET_REGIONS if reg_ok else catalog.OTHER_REGIONS),
            crm=crm,
            tech_stack=sorted(set(stack)),
            customer_status="prospect",
            is_competitor=False,
            has_open_deal=False,
            do_not_contact=False,
            owner_ae_id=f"ae_{int(self.rng.integers(1, cfg.N_AES + 1))}",
            grade=grade,
            ips=[self.new_ip() for _ in range(int(self.rng.integers(1, 4)))],
        )

    def _domain(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "", name.lower().split(",")[0].split(" and ")[0])[:20] or "company"
        tld = self.choice([".com", ".io", ".co", ".ai"])
        domain, k = base + tld, 2
        while domain in self._used_domains:
            domain, k = f"{base}{k}{tld}", k + 1
        self._used_domains.add(domain)
        return domain

    def _contacts(self, a: Account) -> None:
        n = int(np.clip(3 + 1.5 * np.log2(max(a.employee_count, 2)) + self.rng.normal(0, 2), 3, 25))
        for _ in range(n):
            self.add_contact(a)
        # Every account has at least one sales and one revops-or-sales manager to sell to.
        if not any(c.function in catalog.BUYING_FUNCTIONS and c.seniority != "ic" for c in a.contacts):
            self.add_contact(a, function="sales", seniority="manager")

    def add_contact(self, a: Account, function: str | None = None, seniority: str | None = None) -> Contact:
        function = function or self.weighted_key(catalog.FUNCTION_SHARE)
        seniority = seniority or self.weighted_key(catalog.SENIORITY_SHARE)
        first, last = self.fake.first_name(), self.fake.last_name()
        email = re.sub(r"[^a-z0-9.@]", "", f"{first.lower()}.{last.lower()}@{a.domain}")
        existing = {c.email for c in a.contacts}
        k = 2
        while email in existing:
            email = re.sub(r"[^a-z0-9.@]", "", f"{first.lower()}.{last.lower()}{k}@{a.domain}")
            k += 1
        c = Contact(
            contact_id=f"{a.account_id}_c{len(a.contacts) + 1:02d}",
            account_id=a.account_id,
            email=email,
            first_name=first,
            last_name=last,
            title=self.choice(catalog.TITLES[(function, seniority)]),
            seniority=seniority,
            function=function,
            cookie=self.new_cookie(),
        )
        a.contacts.append(c)
        return c

    def outsider_email(self, a: Account) -> str:
        """An address at the account that is not a CRM contact (e.g. an invited teammate)."""
        return re.sub(r"[^a-z0-9.@]", "", f"{self.fake.first_name().lower()}.{self.fake.last_name().lower()}.{self.rng.integers(100, 999)}@{a.domain}")

    # ---------- event emitters ----------

    def emit_web(
        self,
        a: Account,
        kind: str,
        ts: datetime,
        contact: Contact | None = None,
        known: bool = False,
        cookie: str | None = None,
        unmapped_share: float = cfg.UNMAPPED_IP_SHARE,
    ) -> None:
        if contact is not None:
            cookie = contact.cookie
        cookie = cookie or self.new_cookie()
        ip = self.choice(self.isp_ips) if self.rng.random() < unmapped_share else self.choice(a.ips)
        self.web.append({
            "occurred_at": ts,
            "anonymous_id": cookie,
            "contact_email": contact.email if (contact is not None and known) else None,
            "ip": ip,
            "page_path": self.choice(catalog.WEB_PAGES[kind]),
            "utm_source": "paid" if kind == "ad_click" else None,
        })

    def emit_marketing(self, contact: Contact, name: str, ts: datetime) -> None:
        self.marketing.append({
            "occurred_at": ts,
            "contact_email": contact.email,
            "event_name": name,
            "campaign_id": f"cmp_{int(self.rng.integers(1, 40)):03d}",
        })

    def emit_product(self, email: str, name: str, ts: datetime) -> None:
        self.product.append({"occurred_at": ts, "user_email": email, "event_name": name})

    def emit_trigger(self, a: Account, trigger_type: str, ts: datetime, closed_at: datetime | None = None) -> None:
        self.triggers.append({
            "occurred_at": ts,
            "closed_at": closed_at,
            "account_domain": a.domain,
            "trigger_type": trigger_type,
            "detail": self.choice(catalog.TRIGGER_DETAILS[trigger_type]),
        })

    def emit_engagement(self, a: Account, kind: str, ts: datetime, contact: Contact | None, known_share: float = cfg.KNOWN_WEB_SHARE) -> None:
        """Emit one engagement event of any web or marketing kind for a person (or a stranger)."""
        if kind in catalog.MARKETING_EVENTS:
            contact = contact or self.choice(a.contacts)
            self.emit_marketing(contact, kind, ts)
        else:
            known = contact is not None and self.rng.random() < known_share
            self.emit_web(a, kind, ts, contact=contact, known=known)

    def set_truth(self, a: Account, truth_class: str, archetype: str | None = None,
                  intent_start: date | None = None, meeting: date | None = None) -> None:
        self.truth[a.account_id] = {
            "account_id": a.account_id,
            "truth_class": truth_class,
            "archetype": archetype,
            "intent_start_date": intent_start,
            "meeting_date": meeting,
        }

    def clamp(self, ts: datetime) -> datetime | None:
        """Drop events outside the simulation window."""
        if ts.date() < cfg.SIM_START or ts.date() > cfg.SIM_END:
            return None
        return ts
