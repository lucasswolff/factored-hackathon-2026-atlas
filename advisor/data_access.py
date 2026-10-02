"""Read-only, allowlisted demo sessions for organizer-synthetic CSV records.

Startup selects ten aliases using country, segment, status and product type
only. Score and income are read only for a permitted active test session.
No source ID, name, document, phone, email, or raw row leaves this module.
"""

from __future__ import annotations

import csv
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTRY_CURRENCY = {"Colombia": "COP", "México": "MXN", "Argentina": "ARS"}
# Ordinals within (country, segment, current-card) source-row groups. They pin
# ten scenarios without committing customer IDs or reading financial fields
# before a demo session grants profile permission.
PERSONA_RULES = {
    "P01": ("Colombia", "Student", False, 2),
    "P02": ("México", "Student", False, 70),
    "P03": ("Argentina", "Student", False, 4),
    "P04": ("Colombia", "Basic", False, 2),
    "P05": ("México", "Basic", False, 3),
    "P06": ("Argentina", "Basic", False, 1),
    "P07": ("Colombia", "Plus", False, 1),
    "P08": ("México", "Premium", False, 2),
    "P09": ("Argentina", "Premium", False, 2),
    "P10": ("México", "Plus", True, 1),
}


@dataclass(frozen=True)
class Profile:
    alias: str
    country: str
    segment: str
    score: int | None
    monthly_income: Decimal | None
    currency: str
    has_current_credit_card: bool
    customer_status: str


def _decimal(value: str) -> Decimal | None:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _score(value: str) -> int | None:
    number = _decimal(value)
    if number is None or number != number.to_integral_value() or not 300 <= number <= 850:
        return None
    return int(number)


class DemoDirectory:
    """Fixture-only token issuer; alias choice is not real authentication."""

    def __init__(self, data_dir: Path = ROOT / "data",
                 cache_path: Path = ROOT / "advisor/.local/persona_index.json"):
        self._customers_path = Path(data_dir) / "customers.csv"
        products_path = Path(data_dir) / "products.csv"
        self._products_path = products_path
        self._cache_path = Path(cache_path)
        self._sessions: dict[str, str] = {}
        self._source_identity = self._identity()
        cached = self._read_cache()
        if cached is not None:
            self._ids = {alias: entry["source_id"] for alias, entry in cached.items()}
            self._card_flags = {alias: entry["has_card"] for alias, entry in cached.items()}
            return
        cards = set()
        product_ids = set()
        with products_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not {"product_id", "customer_id", "product_type", "product_status"} <= set(reader.fieldnames or ()):
                raise ValueError("products schema mismatch")
            for row in reader:
                if row["product_id"] in product_ids:
                    raise ValueError("duplicate product ID")
                product_ids.add(row["product_id"])
                if row["product_type"] == "Tarjeta Crédito" and row["product_status"] in {"Active", "Blocked", "Suspended"}:
                    cards.add(row["customer_id"])
        self._ids: dict[str, str] = {}
        self._card_flags: dict[str, bool] = {}
        counts: dict[tuple[str, str, bool], int] = {}
        seen = set()
        with self._customers_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not {"customer_id", "country", "segment", "customer_status"} <= set(reader.fieldnames or ()):
                raise ValueError("customers schema mismatch")
            for row in reader:
                cid = row["customer_id"]
                if not cid or cid in seen:
                    raise ValueError("missing or duplicate customer ID")
                seen.add(cid)
                if row["customer_status"] != "Active":
                    continue
                group = (row["country"], row["segment"], cid in cards)
                counts[group] = counts.get(group, 0) + 1
                for alias, (*base, ordinal) in PERSONA_RULES.items():
                    if group == tuple(base) and counts[group] == ordinal:
                        self._ids[alias] = cid
                        self._card_flags[alias] = cid in cards
        if set(self._ids) != set(PERSONA_RULES):
            raise ValueError(f"Demo persona coverage missing: {sorted(set(PERSONA_RULES) - set(self._ids))}")
        if self._identity() != self._source_identity:
            raise ValueError("Source changed while building demo index")
        self._write_cache()

    def _identity(self) -> tuple[tuple[int, int], tuple[int, int]]:
        return tuple((p.stat().st_size, p.stat().st_mtime_ns)
                     for p in (self._customers_path, self._products_path))

    def _read_cache(self) -> dict | None:
        try:
            cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(cache, dict):
            return None
        if cache.get("version") != 1 or cache.get("source_identity") != [list(v) for v in self._source_identity]:
            return None
        entries = cache.get("entries")
        if not isinstance(entries, dict) or set(entries) != set(PERSONA_RULES):
            return None
        for alias, entry in entries.items():
            if (not isinstance(entry, dict) or not isinstance(entry.get("source_id"), str)
                or not entry["source_id"] or not isinstance(entry.get("has_card"), bool)
                or entry["has_card"] != PERSONA_RULES[alias][2]):
                return None
        return entries

    def _write_cache(self) -> None:
        self._cache_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = {"version": 1, "source_identity": [list(v) for v in self._source_identity],
                   "entries": {alias: {"source_id": self._ids[alias],
                                       "has_card": self._card_flags[alias]}
                               for alias in self.aliases()}}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self._cache_path.parent,
                                         prefix=".persona-", delete=False) as file:
            temp_path = Path(file.name)
            os.chmod(temp_path, 0o600)
            json.dump(payload, file, ensure_ascii=False)
        os.replace(temp_path, self._cache_path)

    def aliases(self) -> tuple[str, ...]:
        return tuple(sorted(self._ids))

    def public_list(self) -> list[dict[str, str]]:
        return [self.public_persona(alias) for alias in self.aliases()]

    def public_persona(self, alias: str) -> dict[str, str]:
        if alias not in self._ids:
            raise PermissionError("No permitted demo persona for this alias")
        return {"alias": alias, "country": PERSONA_RULES[alias][0],
                "segment": PERSONA_RULES[alias][1]}

    def persona_preview(self, alias: str) -> dict[str, object]:
        """Safe, allowlisted fixture details for the simulated sign-in screen."""
        public = self.public_persona(alias)
        if self._identity() != self._source_identity:
            raise ValueError("Customer/product source changed; rebuild demo directory")
        with self._customers_path.open(encoding="utf-8-sig", newline="") as file:
            row = next((item for item in csv.DictReader(file)
                        if item["customer_id"] == self._ids[alias]), None)
        if row is None:
            raise ValueError("Selected customer row missing")
        currency = COUNTRY_CURRENCY[public["country"]]
        income = _decimal(row["estimated_monthly_income"])
        latest: tuple[str, Decimal] | None = None
        with (ROOT / "data/daily_exchange_rates.csv").open(encoding="utf-8-sig", newline="") as file:
            for rate in csv.DictReader(file):
                if rate["source_currency"] == currency and rate["target_currency"] == "USD":
                    date = rate["date"]
                    value = _decimal(rate["exchange_rate"])
                    if value is not None and (latest is None or date > latest[0]):
                        latest = (date, value)
        usd = (income * latest[1]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if income is not None and latest else None
        return {**public, "city": row["city"], "state": row["state"],
                "occupation": row["occupation"], "customer_status": row["customer_status"],
                "credit_score": _score(row["credit_score"]),
                "estimated_monthly_income": str(income) if income is not None else None,
                "income_currency": currency, "estimated_monthly_income_usd": str(usd) if usd is not None else None,
                "usd_rate_date": latest[0] if latest else None,
                "has_current_credit_card": self._card_flags[alias]}

    def issue_test_session(self, alias: str) -> str:
        self.public_persona(alias)
        token = secrets.token_urlsafe(32)
        self._sessions[token] = alias
        return token

    def close_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def read_profile(self, token: str | None, profile_permission: bool) -> Profile:
        if not token or token not in self._sessions:
            raise PermissionError("Trusted demo session required")
        if not profile_permission:
            raise PermissionError("Separate profile-use permission required")
        alias = self._sessions[token]
        cid = self._ids[alias]
        if self._identity() != self._source_identity:
            raise ValueError("Customer/product source changed; rebuild demo directory")
        with self._customers_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not {"customer_id", "country", "segment", "credit_score", "estimated_monthly_income", "customer_status"} <= set(reader.fieldnames or ()):
                raise ValueError("customers schema mismatch")
            row = next((item for item in reader if item["customer_id"] == cid), None)
        if row is None:
            raise ValueError("Selected customer row missing")
        expected = PERSONA_RULES[alias]
        if row["customer_status"] != "Active" or (row["country"], row["segment"]) != expected[:2]:
            raise ValueError("Selected customer data changed")
        return Profile(alias, row["country"], row["segment"], _score(row["credit_score"]),
                       _decimal(row["estimated_monthly_income"]), COUNTRY_CURRENCY[row["country"]],
                       self._card_flags[alias], row["customer_status"])
