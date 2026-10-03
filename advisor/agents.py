"""Private, roster-backed candidate selection for simulated chat handoffs."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from .data_access import ROOT

ROSTER_KEY = "ROSTER#CREDIT_CHAT"
COUNTRIES = {"México": "Mexico", "Colombia": "Colombia", "Argentina": "Argentina"}
LANGUAGES = {"es": "español", "pt": "portugués"}


def eligible_agent(row: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only noncontact fields needed for assignment."""
    if (row.get("agent_status") != "Active" or row.get("specialty") != "Créditos" or
            row.get("agent_type") not in {"Digital", "Hybrid"}):
        return None
    languages = [part.strip().casefold() for part in row.get("languages", "").split(",")]
    if not row.get("agent_id") or not any(code in languages for code in LANGUAGES.values()):
        return None
    return {"agent_id": row["agent_id"], "country_of_origin": row.get("country_of_origin", ""),
            "native_accent": row.get("native_accent", ""), "languages": languages,
            "specialty": "Créditos", "agent_type": row["agent_type"], "agent_status": "Active"}


def choose_agent(rows: list[dict[str, Any]], language: str, country: str,
                 conversation_id: str) -> dict[str, Any] | None:
    required = LANGUAGES.get(language)
    if required is None:
        return None
    candidates = [row for row in rows if row.get("agent_status") == "Active"
                  and row.get("specialty") == "Créditos"
                  and row.get("agent_type") in {"Digital", "Hybrid"}
                  and required in row.get("languages", [])]
    if not candidates:
        return None
    same_country = [row for row in candidates if row.get("country_of_origin") == COUNTRIES.get(country)]
    pool = sorted(same_country or candidates, key=lambda row: row["agent_id"])
    index = int.from_bytes(hashlib.sha256(conversation_id.encode()).digest()[:8], "big") % len(pool)
    selected = pool[index]
    return {"agent_id": selected["agent_id"], "country_match": bool(same_country),
            "language": language, "specialty": "Créditos", "assignment_mode": "MOCK_ROSTER"}


class LocalAgentDirectory:
    def __init__(self, path: Path = ROOT / "data/service_agents.csv"):
        self.path = Path(path)

    def candidates(self) -> list[dict[str, Any]]:
        with self.path.open(encoding="utf-8-sig", newline="") as file:
            return [candidate for row in csv.DictReader(file)
                    if (candidate := eligible_agent(row)) is not None]


class EmptyAgentDirectory:
    """Hosted fallback when the private roster adapter is not configured."""

    def candidates(self) -> list[dict[str, Any]]:
        return []


class DynamoAgentDirectory:
    def __init__(self, table: Any):
        self.table = table

    def candidates(self) -> list[dict[str, Any]]:
        rows = []
        cursor = None
        while True:
            options: dict[str, Any] = {"FilterExpression": "pk = :roster",
                                       "ExpressionAttributeValues": {":roster": ROSTER_KEY},
                                       "ConsistentRead": True}
            if cursor:
                options["ExclusiveStartKey"] = cursor
            result = self.table.scan(**options)
            rows.extend(item["agent"] for item in result.get("Items", []))
            cursor = result.get("LastEvaluatedKey")
            if not cursor:
                return rows
