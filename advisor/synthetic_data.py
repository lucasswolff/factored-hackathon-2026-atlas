"""Small team-written fixtures for a hosted, source-data-free judge demo."""

from __future__ import annotations

import secrets
from decimal import Decimal

from .data_access import COUNTRY_CURRENCY, Profile

SOURCE_LABEL = "TEAM_GENERATED_DEMO_FIXTURE"

# Invented examples. These are not copied customer rows or a source-data export.
# Scores and incomes deliberately exercise the synthetic policy's common edges.
FIXTURES = {
    "P01": ("Colombia", "Student", "Bogotá", "Bogotá D.C.", "Student", 615, "1800000", False),
    "P02": ("México", "Student", "Puebla", "Puebla", "Student", 535, "8000", False),
    "P03": ("Argentina", "Student", "Córdoba", "Córdoba", "Student", 610, "320000", False),
    "P04": ("Colombia", "Basic", "Cali", "Valle del Cauca", "Retail associate", 550, "4000000", False),
    "P05": ("México", "Basic", "Guadalajara", "Jalisco", "Office assistant", 590, "18000", False),
    "P06": ("Argentina", "Basic", "Rosario", "Santa Fe", "Technician", 605, "340000", False),
    "P07": ("Colombia", "Plus", "Medellín", "Antioquia", "Engineer", 680, "12000000", False),
    "P08": ("México", "Premium", "Monterrey", "Nuevo León", "Consultant", 765, "140000", False),
    "P09": ("Argentina", "Premium", "Mendoza", "Mendoza", "Business owner", 750, "2400000", False),
    "P10": ("México", "Plus", "Querétaro", "Querétaro", "Designer", 690, "55000", True),
}


class SyntheticDirectory:
    source_label = SOURCE_LABEL

    def __init__(self):
        self._sessions: dict[str, str] = {}

    def aliases(self) -> tuple[str, ...]:
        return tuple(FIXTURES)

    def public_persona(self, alias: str) -> dict[str, str]:
        if alias not in FIXTURES:
            raise PermissionError("No permitted demo persona for this alias")
        country, segment, *_ = FIXTURES[alias]
        return {"alias": alias, "country": country, "segment": segment}

    def public_list(self) -> list[dict[str, str]]:
        return [self.public_persona(alias) for alias in self.aliases()]

    def persona_preview(self, alias: str) -> dict[str, object]:
        public = self.public_persona(alias)
        country, _, city, state, occupation, score, income, has_card = FIXTURES[alias]
        return {**public, "city": city, "state": state, "occupation": occupation,
                "customer_status": "Active", "credit_score": score,
                "estimated_monthly_income": income, "income_currency": COUNTRY_CURRENCY[country],
                "estimated_monthly_income_usd": None, "usd_rate_date": None,
                "has_current_credit_card": has_card, "source": SOURCE_LABEL}

    def issue_test_session(self, alias: str) -> str:
        self.public_persona(alias)
        token = secrets.token_urlsafe(32)
        self._sessions[token] = alias
        return token

    def close_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def restore_test_session(self, token: str, alias: str) -> None:
        """Restore a server-issued fixture binding from trusted session storage."""
        self.public_persona(alias)
        if not token:
            raise PermissionError("Trusted demo session required")
        self._sessions[token] = alias

    def read_profile(self, token: str | None, profile_permission: bool) -> Profile:
        if not token or token not in self._sessions:
            raise PermissionError("Trusted demo session required")
        if not profile_permission:
            raise PermissionError("Profile-use permission required")
        alias = self._sessions[token]
        country, segment, _, _, _, score, income, has_card = FIXTURES[alias]
        return Profile(alias, country, segment, score, Decimal(income),
                       COUNTRY_CURRENCY[country], has_card, "Active")
