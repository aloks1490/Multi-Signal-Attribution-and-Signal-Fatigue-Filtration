"""M5: HubSpot sync against an in-memory fake HubSpot (no network)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import pytest

from activation import crm
from activation.hubspot import HubSpot, HubSpotError
from activation.run import run as run_digest
from app import queries as q
from tests.conftest import run_dbt


class Resp:
    def __init__(self, status: int, body: dict | None = None, headers: dict | None = None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = json.dumps(self._body) if body is not None else ""

    def json(self):
        return self._body


class FakeHubSpot:
    """Just enough of the HubSpot CRM API for the sync: properties, upserts, associations, tasks, paged reads."""

    def __init__(self, fail_first: int = 0):
        self.properties = {"companies": {"name", "domain", "lifecyclestage", "hs_num_open_deals"}, "contacts": {"email"}}
        self.groups = {"companies": set()}
        self.objects = {"companies": {}, "contacts": {}, "tasks": {}}
        self.assoc: set[tuple[str, str, str, str]] = set()
        self.next_id = 100
        self.fail_first = fail_first
        self.log: list[tuple[str, str]] = []

    def _id(self) -> str:
        self.next_id += 1
        return str(self.next_id)

    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        path = re.sub(r"^https://api\.hubapi\.com", "", url)
        self.log.append((method, path))
        assert headers["Authorization"].startswith("Bearer ")
        if self.fail_first:
            self.fail_first -= 1
            return Resp(429, {"message": "slow down"}, {"Retry-After": "0"})
        if m := re.fullmatch(r"/crm/v3/properties/(\w+)", path):
            if method == "GET":
                return Resp(200, {"results": [{"name": n} for n in sorted(self.properties[m[1]])]})
            if json["name"] in self.properties[m[1]]:
                return Resp(409, {"message": "exists"})
            self.properties[m[1]].add(json["name"])
            return Resp(201, json)
        if m := re.fullmatch(r"/crm/v3/properties/(\w+)/groups", path):
            if method == "GET":
                return Resp(200, {"results": [{"name": g} for g in self.groups[m[1]]]})
            self.groups[m[1]].add(json["name"])
            return Resp(201, json)
        if m := re.fullmatch(r"/crm/v3/objects/(\w+)/batch/upsert", path):
            assert len(json["inputs"]) <= 100
            results = []
            for inp in json["inputs"]:
                store, key = self.objects[m[1]], inp["id"]
                match = next((oid for oid, o in store.items() if o.get(inp["idProperty"]) == key), None)
                oid = match or self._id()
                store.setdefault(oid, {}).update({inp["idProperty"]: key, **inp["properties"]})
                results.append({"id": oid, "properties": dict(store[oid]), "new": match is None})
            return Resp(200, {"status": "COMPLETE", "results": results})
        if m := re.fullmatch(r"/crm/v3/objects/(\w+)/batch/create", path):
            results = []
            for inp in json["inputs"]:
                oid = self._id()
                self.objects[m[1]][oid] = dict(inp["properties"])
                results.append({"id": oid})
            return Resp(201, {"status": "COMPLETE", "results": results})
        if m := re.fullmatch(r"/crm/v4/associations/(\w+)/(\w+)/batch/associate/default", path):
            for inp in json["inputs"]:
                self.assoc.add((m[1], inp["from"]["id"], m[2], inp["to"]["id"]))
            return Resp(200, {"status": "COMPLETE", "results": []})
        if m := re.fullmatch(r"/crm/v3/objects/(\w+)/search", path):
            f = json["filterGroups"][0]["filters"][0]
            hits = [{"id": oid, "properties": o} for oid, o in self.objects[m[1]].items() if o.get(f["propertyName"]) == f["value"]]
            return Resp(200, {"results": hits})
        if m := re.fullmatch(r"/crm/v3/objects/(\w+)", path):
            items = sorted(self.objects[m[1]].items(), key=lambda kv: int(kv[0]))
            start = int(params.get("after", 0))
            page = items[start:start + params["limit"]]
            body = {"results": [{"id": oid, "properties": o} for oid, o in page]}
            if start + params["limit"] < len(items):
                body["paging"] = {"next": {"after": str(start + params["limit"])}}
            return Resp(200, body)
        return Resp(404, {"message": f"no route {method} {path}"})


@pytest.fixture()
def crm_env(small_db, db_copy, tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNAL_APP_STATE", str(tmp_path / "state.duckdb"))
    for var in ("LLM_API_KEY", "LLM_MODEL", "SLACK_WEBHOOK_URL", "HUBSPOT_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    day = q.df(small_db, """select alert_date, count(*) n from gold.engine_alerts
                            where is_active and alert_date >= (select cast(value as date) from seeds.scoring_params where param = 'eval_start')
                            group by 1 order by n desc, alert_date limit 1""")
    return {"db": db_copy, "day": day.alert_date[0].date(), "out": tmp_path / "out"}


def client(fake: FakeHubSpot) -> HubSpot:
    return HubSpot("test-token", session=fake, sleep=lambda s: None)


# ---------- client ----------

def test_batches_of_100_and_no_duplicates_on_repeat():
    fake, hs = FakeHubSpot(), None
    hs = client(fake)
    rows = [(f"acc_{i:05d}", {"name": f"Co {i}"}) for i in range(250)]
    first = hs.batch_upsert("companies", "signal_account_id", rows)
    upserts = [p for m, p in fake.log if p.endswith("/batch/upsert")]
    assert len(upserts) == 3 and len(first) == 250
    second = hs.batch_upsert("companies", "signal_account_id", rows)
    assert second == first and len(fake.objects["companies"]) == 250


def test_rate_limit_is_retried():
    fake = FakeHubSpot(fail_first=2)
    assert "name" in client(fake).property_names("companies")
    assert len(fake.log) == 3


def test_gives_up_after_max_retries():
    fake = FakeHubSpot(fail_first=99)
    with pytest.raises(HubSpotError):
        HubSpot("t", session=fake, sleep=lambda s: None, max_retries=2).property_names("companies")


def test_schema_setup_is_idempotent():
    fake = FakeHubSpot()
    hs = client(fake)
    assert hs.ensure_group("companies", crm.GROUP, "Signal Engine") is True
    created = hs.ensure_properties("companies", crm.company_properties())
    assert len(created) == 9 and len(crm.company_properties()) <= 10  # free plan: 10 custom properties
    assert hs.ensure_group("companies", crm.GROUP, "Signal Engine") is False
    assert hs.ensure_properties("companies", crm.company_properties()) == []


def test_paged_read_returns_everything():
    fake = FakeHubSpot()
    hs = client(fake)
    hs.batch_upsert("companies", "signal_account_id", [(f"a{i}", {}) for i in range(230)])
    assert len(hs.list_all("companies", ["signal_account_id"])) == 230


# ---------- push ----------

def test_dry_run_makes_no_calls_and_writes_the_plan(crm_env):
    r = crm.push(crm_env["db"], None, crm_env["day"], out_dir=crm_env["out"])
    plan = json.loads(Path(r["file"]).read_text())
    assert r["status"] == "dry_run" and r["companies"] > 0 and r["tasks"] >= 1
    assert all(c["domain"].endswith(".example") for c in plan["companies"])
    assert all(c["email"].endswith(".example") for c in plan["contacts"])
    assert not {"lifecyclestage", "signal_do_not_contact"} & set().union(*[set(c) for c in plan["companies"]])


def test_push_syncs_companies_contacts_and_tasks_once(crm_env):
    run_digest(crm_env["db"], crm_env["day"], out_dir=crm_env["out"])  # narratives for headlines and task bodies
    fake = FakeHubSpot()
    first = crm.push(crm_env["db"], client(fake), crm_env["day"], out_dir=crm_env["out"])
    n_companies, n_contacts = len(fake.objects["companies"]), len(fake.objects["contacts"])
    assert first["status"] == "synced" and first["tasks_created"] == first["tasks"] >= 1
    assert n_companies == first["companies"] and n_contacts == first["contacts"]
    assert any(a[0] == "contacts" and a[2] == "companies" for a in fake.assoc)
    assert sum(1 for a in fake.assoc if a[0] == "tasks") == first["tasks_created"]
    task = next(iter(fake.objects["tasks"].values()))
    assert task["hs_task_status"] == "NOT_STARTED" and task["hs_task_subject"].startswith("Signal Engine: reach out to")

    second = crm.push(crm_env["db"], client(fake), crm_env["day"], out_dir=crm_env["out"])
    assert second["tasks_created"] == 0 and second["tasks_skipped_existing"] == first["tasks"]
    assert len(fake.objects["companies"]) == n_companies and len(fake.objects["contacts"]) == n_contacts
    assert second["properties_created"] == 0


def test_push_never_overwrites_rep_owned_fields(crm_env):
    fake = FakeHubSpot()
    crm.push(crm_env["db"], client(fake), crm_env["day"], out_dir=crm_env["out"])
    oid = next(iter(fake.objects["companies"]))
    fake.objects["companies"][oid].update({"lifecyclestage": "customer", "signal_do_not_contact": "true"})
    crm.push(crm_env["db"], client(fake), crm_env["day"], out_dir=crm_env["out"])
    assert fake.objects["companies"][oid]["lifecyclestage"] == "customer"
    assert fake.objects["companies"][oid]["signal_do_not_contact"] == "true"


# ---------- pull: the loop ----------

def test_rep_marks_customer_in_hubspot_and_alerts_stop(crm_env, tmp_path):
    """Push, mark an alerted company as a customer in HubSpot, pull, rebuild: it is excluded and no longer alerts."""
    db = crm_env["db"]
    fake = FakeHubSpot()
    crm.push(db, client(fake), crm_env["day"], out_dir=crm_env["out"])
    target = q.df(db, "select account_id from gold.engine_alerts where is_active and alert_date = ? limit 1", [crm_env["day"]]).account_id[0]
    oid = next(o for o, p in fake.objects["companies"].items() if p["signal_account_id"] == target)
    fake.objects["companies"][oid]["lifecyclestage"] = "customer"

    pulled = crm.pull(db, client(fake))
    assert pulled["status"] == "pulled" and pulled["open_deals_property"] == "hs_num_open_deals"
    run_dbt(db, tmp_path, "build", "--select", "stg_hubspot_companies+")

    con = duckdb.connect(str(db), read_only=True)
    try:
        reason = con.execute("select reason from silver.account_exclusions where account_id = ?", [target]).fetchone()[0]
        alerts = con.execute("select count(*) from gold.engine_alerts where account_id = ?", [target]).fetchone()[0]
    finally:
        con.close()
    assert reason == "crm_customer" and alerts == 0


def test_pull_without_token_changes_nothing(crm_env):
    assert crm.pull(crm_env["db"], None) == {"status": "not_connected", "companies": 0}


def test_crm_sync_never_reads_truth_labels():
    text = (Path(__file__).resolve().parent.parent / "activation" / "crm.py").read_text()
    assert not re.search(r"labels\.[a-z_]", text) and "account_truth" not in text
