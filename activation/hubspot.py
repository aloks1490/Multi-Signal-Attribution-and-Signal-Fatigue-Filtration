"""Minimal HubSpot CRM client: schema setup, batch upserts, default associations, tasks, paged reads.

Uses a private-app token (HUBSPOT_TOKEN). Paths are the v3/v4 CRM endpoints; HubSpot is moving to dated versions
(e.g. /crm/objects/2026-09/...), so every path is built here in one place. The HTTP session is injectable so tests
run against an in-memory fake.
"""
from __future__ import annotations

import time
from typing import Callable, Iterable

import requests

BASE_URL = "https://api.hubapi.com"
BATCH = 100  # HubSpot batch endpoints take at most 100 inputs
RETRY_STATUSES = {429, 500, 502, 503, 504}


class HubSpotError(RuntimeError):
    pass


def chunks(items: list, size: int = BATCH) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


class HubSpot:
    def __init__(self, token: str, session=None, base_url: str = BASE_URL, sleep: Callable[[float], None] = time.sleep,
                 max_retries: int = 5):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.sleep = sleep
        self.max_retries = max_retries
        self.calls = 0

    # ---------- transport ----------

    def request(self, method: str, path: str, json: dict | None = None, params: dict | None = None,
                ok: tuple[int, ...] = (200, 201, 204, 207)) -> dict:
        for attempt in range(self.max_retries + 1):
            self.calls += 1
            r = self.session.request(method, self.base_url + path, json=json, params=params, headers=self.headers, timeout=30)
            if r.status_code in ok:
                return r.json() if r.status_code != 204 and r.text else {}
            if r.status_code in RETRY_STATUSES and attempt < self.max_retries:
                wait = float(r.headers.get("Retry-After", 0) or 0) or min(2 ** attempt, 30)
                self.sleep(wait)
                continue
            raise HubSpotError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        raise HubSpotError(f"{method} {path}: retries exhausted")

    # ---------- schema ----------

    def property_names(self, object_type: str) -> set[str]:
        data = self.request("GET", f"/crm/v3/properties/{object_type}")
        return {p["name"] for p in data.get("results", [])}

    def ensure_group(self, object_type: str, name: str, label: str) -> bool:
        groups = self.request("GET", f"/crm/v3/properties/{object_type}/groups").get("results", [])
        if any(g["name"] == name for g in groups):
            return False
        self.request("POST", f"/crm/v3/properties/{object_type}/groups", json={"name": name, "label": label})
        return True

    def ensure_properties(self, object_type: str, definitions: list[dict]) -> list[str]:
        """Create the properties that do not exist yet. Returns the names created."""
        existing = self.property_names(object_type)
        created = []
        for d in definitions:
            if d["name"] not in existing:
                self.request("POST", f"/crm/v3/properties/{object_type}", json=d)
                created.append(d["name"])
        return created

    # ---------- records ----------

    def batch_upsert(self, object_type: str, id_property: str, rows: list[tuple[str, dict]]) -> dict[str, str]:
        """Create or update records keyed by a unique property. Returns {key: hubspot id}."""
        ids: dict[str, str] = {}
        for part in chunks(rows):
            body = {"inputs": [{"idProperty": id_property, "id": key, "properties": props} for key, props in part]}
            data = self.request("POST", f"/crm/v3/objects/{object_type}/batch/upsert", json=body)
            if data.get("numErrors"):
                raise HubSpotError(f"upsert {object_type}: {data.get('errors')}")
            for res in data.get("results", []):
                ids[str(res["properties"].get(id_property))] = str(res["id"])
        return ids

    def batch_create(self, object_type: str, properties: list[dict]) -> list[str]:
        out = []
        for part in chunks(properties):
            data = self.request("POST", f"/crm/v3/objects/{object_type}/batch/create",
                                json={"inputs": [{"properties": p} for p in part]})
            out += [str(r["id"]) for r in data.get("results", [])]
        return out

    def associate_default(self, from_type: str, to_type: str, pairs: list[tuple[str, str]]) -> None:
        """Link records with HubSpot's default association (no association type ids needed)."""
        for part in chunks(pairs):
            body = {"inputs": [{"from": {"id": a}, "to": {"id": b}} for a, b in part]}
            self.request("POST", f"/crm/v4/associations/{from_type}/{to_type}/batch/associate/default", json=body)

    def find_by(self, object_type: str, prop: str, value: str, properties: list[str]) -> list[dict]:
        body = {"filterGroups": [{"filters": [{"propertyName": prop, "operator": "EQ", "value": value}]}],
                "properties": properties, "limit": 10}
        return self.request("POST", f"/crm/v3/objects/{object_type}/search", json=body).get("results", [])

    def list_all(self, object_type: str, properties: list[str]) -> list[dict]:
        out, after = [], None
        while True:
            params = {"limit": BATCH, "properties": ",".join(properties)}
            if after:
                params["after"] = after
            data = self.request("GET", f"/crm/v3/objects/{object_type}", params=params)
            out += data.get("results", [])
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                return out
