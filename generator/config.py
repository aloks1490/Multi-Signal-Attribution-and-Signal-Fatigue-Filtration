"""Generation profiles and knobs for the synthetic world.

Dates are fixed (not `today`) so every run with the same seed is identical.
"""
from dataclasses import dataclass
from datetime import date, timedelta

SIM_START = date(2026, 3, 31)
EVAL_START = date(2026, 6, 29)  # Monday
EVAL_END = date(2026, 9, 27)  # Sunday; 13 full weeks
SIM_END = EVAL_END
N_AES = 5

NEGATIVE_TYPES = (
    "pricing_hammerer",
    "bot_burst",
    "trigger_only",
    "content_binger",
    "low_fit_active",
    "customer_active",
    "open_deal_active",
    "stalled_trial",
)


@dataclass(frozen=True)
class Profile:
    name: str
    n_accounts: int
    n_planted: int
    n_random_converters: int
    n_per_negative_type: int


PROFILES = {
    "small": Profile("small", n_accounts=200, n_planted=6, n_random_converters=2, n_per_negative_type=1),
    "standard": Profile("standard", n_accounts=2000, n_planted=20, n_random_converters=5, n_per_negative_type=8),
}

# Fit grade mix (target points → grade). Most of any market sits outside the ICP.
GRADE_POINTS = {"A": (5, 6), "B": (4, 4), "C": (3, 3), "D": (0, 2)}
GRADE_SHARE = {"A": 0.10, "B": 0.15, "C": 0.25, "D": 0.50}

# Account status shares (mutually exclusive, drawn after fit).
CUSTOMER_SHARE = 0.04
OPEN_DEAL_SHARE = 0.02
DNC_SHARE = 0.01
N_COMPETITORS = 3

# Awareness level → (share, event-count rule) for background first-party activity.
AWARENESS_SHARE = {"unaware": 0.55, "low": 0.30, "engaged": 0.15}

# Background web/marketing event mix (relative weights).
NOISE_MIX = {
    "blog_visit": 35,
    "ad_click": 20,
    "email_open": 15,
    "email_click": 8,
    "content_download": 5,
    "case_study_view": 4,
    "pricing_page": 4,
    "webinar_attended": 3,
    "integration_page": 3,
    "unmapped_page": 2,
    "comparison_page": 1.5,
    "security_page": 1,
    "demo_request": 0.1,
}
NOISE_TRIAL_PROB = {"unaware": 0.0, "low": 0.01, "engaged": 0.05}

# Share of web events that carry a known email, and that come from unmapped (ISP) IPs.
KNOWN_WEB_SHARE = 0.40
UNMAPPED_IP_SHARE = 0.20

# Background triggers: share of all accounts that get one in the simulation.
TRIGGER_RATES = {
    "funding_round": 0.08,
    "new_sales_leader": 0.10,
    "sdr_job_post": 0.15,
    "competitor_tool_dropped": 0.03,
    "crm_adopted": 0.03,
}

# Planted buyers.
ARCHETYPE_SHARE = {"committee": 0.5, "quiet": 0.3, "plg": 0.2}
BUYER_TRIGGER_PROB = 0.70
BUYER_DEMO_PROB = 0.30
INTENT_LEAD_DAYS = (14, 42)  # intent episode starts this many days before the meeting


def sim_days() -> int:
    return (SIM_END - SIM_START).days + 1


def day(offset: int) -> date:
    return SIM_START + timedelta(days=offset)
