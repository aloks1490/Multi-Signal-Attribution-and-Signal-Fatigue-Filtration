"""Names the generator emits: page paths, product/marketing events, triggers, titles.

Names only. Weights and half-lives live in dbt seeds; the generator must never read them.
"""

# Web event kind → page paths. dbt maps paths back to event types via seeds/page_rules.csv.
WEB_PAGES = {
    "blog_visit": ["/blog/cold-email-benchmarks", "/blog/sdr-ramp-plan", "/blog/sequence-templates", "/blog/reply-rates"],
    "case_study_view": ["/customers/northwind", "/customers/globex"],
    "integration_page": ["/integrations/salesforce", "/integrations/hubspot"],
    "comparison_page": ["/vs/outreach", "/vs/salesloft", "/vs/apollo"],
    "pricing_page": ["/pricing"],
    "security_page": ["/security", "/trust/gdpr"],
    "demo_request": ["/demo/thank-you"],
    "unmapped_page": ["/careers", "/about", "/legal/privacy"],
    "ad_click": ["/lp/outbound-playbook", "/lp/ai-sequences"],  # emitted with utm_source='paid'
}
WEB_KINDS = set(WEB_PAGES)

MARKETING_EVENTS = {"email_open", "email_click", "webinar_attended", "content_download"}

PRODUCT_EVENTS = (
    "trial_started",
    "mailbox_connected",
    "sequence_created",
    "teammate_invited",
    "crm_connected",
    "usage_limit_hit",
)

TRIGGER_DETAILS = {
    "funding_round": ["Seed $4M", "Series A $15M", "Series B $40M", "Series C $90M"],
    "new_sales_leader": ["VP Sales", "CRO", "Head of Sales Development", "Head of RevOps"],
    "sdr_job_post": ["SDR", "BDR", "Senior SDR", "SDR Team Lead"],
    "competitor_tool_dropped": ["Outreach", "Salesloft", "Apollo"],
    "crm_adopted": ["Salesforce", "HubSpot"],
}

TARGET_INDUSTRIES = ["B2B Software", "Fintech", "Martech", "HR Tech", "Cybersecurity", "Data & Analytics"]
OTHER_INDUSTRIES = ["Retail", "Hospitality", "Construction", "Education", "Healthcare Services", "Logistics"]
TARGET_REGIONS = ["NA", "EU"]
OTHER_REGIONS = ["APAC", "LATAM", "MEA"]
TARGET_CRMS = ["Salesforce", "HubSpot"]
OTHER_CRMS = ["Pipedrive", "Zoho", "None"]
COMPETITOR_TOOLS = ["Outreach", "Salesloft", "Apollo"]
OTHER_TOOLS = ["Gong", "ZoomInfo", "Slack", "Snowflake", "Segment", "Intercom", "Marketo", "Clay"]
COMPETITOR_NAMES = ["Cadenceo", "Sequencr", "Reachly"]

FUNCTION_SHARE = {
    "sales": 0.35,
    "revops": 0.10,
    "marketing": 0.20,
    "engineering": 0.15,
    "security": 0.05,
    "finance": 0.05,
    "other": 0.10,
}
SENIORITY_SHARE = {"exec": 0.12, "manager": 0.28, "ic": 0.60}
BUYING_FUNCTIONS = ("sales", "revops")

TITLES = {
    ("sales", "exec"): ["VP Sales", "CRO", "VP Revenue"],
    ("sales", "manager"): ["Sales Manager", "SDR Manager", "Head of Sales Development"],
    ("sales", "ic"): ["SDR", "BDR", "Account Executive"],
    ("revops", "exec"): ["VP Revenue Operations"],
    ("revops", "manager"): ["RevOps Manager", "Head of Sales Ops"],
    ("revops", "ic"): ["RevOps Analyst", "Sales Ops Specialist"],
    ("marketing", "exec"): ["CMO", "VP Marketing"],
    ("marketing", "manager"): ["Demand Gen Manager", "Content Manager"],
    ("marketing", "ic"): ["Marketing Specialist", "Content Writer"],
    ("engineering", "exec"): ["CTO", "VP Engineering"],
    ("engineering", "manager"): ["Engineering Manager"],
    ("engineering", "ic"): ["Software Engineer", "Data Engineer"],
    ("security", "exec"): ["CISO"],
    ("security", "manager"): ["Security Manager"],
    ("security", "ic"): ["Security Analyst"],
    ("finance", "exec"): ["CFO"],
    ("finance", "manager"): ["Finance Manager"],
    ("finance", "ic"): ["Financial Analyst"],
    ("other", "exec"): ["COO", "CEO"],
    ("other", "manager"): ["Operations Manager"],
    ("other", "ic"): ["Operations Associate"],
}
