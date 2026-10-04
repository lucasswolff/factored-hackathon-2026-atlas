"""Versioned, team-created recommendation and simulated precheck rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .data_access import Profile

POLICY_VERSION = "DEMO-CREDIT-POLICY-2026-09-30-v2"
OFFER_VERSION = "CARD-CATALOG-DRAFT-2026-10-04-v2"
CARDS = ("Campus", "Horizon", "Rewards", "Summit")
MIN_INCOME = {
    "Colombia": {"Horizon": Decimal(3000000), "Rewards": Decimal(10000000), "Summit": Decimal(24000000)},
    "México": {"Horizon": Decimal(13000), "Rewards": Decimal(40000), "Summit": Decimal(105000)},
    "Argentina": {"Horizon": Decimal(280000), "Rewards": Decimal(820000), "Summit": Decimal(2100000)},
}
MIN_SCORE = {"Campus": 540, "Horizon": 560, "Rewards": 650, "Summit": 720}


@dataclass(frozen=True)
class PolicyResult:
    card: str
    status: str
    reasons: tuple[str, ...]
    missing_data: tuple[str, ...]
    policy_version: str = POLICY_VERSION
    offer_version: str = OFFER_VERSION


def _validate(profile: Profile, card: str) -> None:
    if card not in CARDS or profile.country not in MIN_INCOME:
        raise ValueError("unsupported card/country")


def suggest(profile: Profile) -> PolicyResult:
    """A conversation starter, never an eligibility result."""
    if profile.customer_status != "Active":
        return PolicyResult("", "NO_SUGGESTION", ("customer_not_active",), ())
    if profile.has_current_credit_card:
        return PolicyResult("", "NO_SUGGESTION", ("current_credit_card_requires_review",), ())
    missing = tuple(k for k, v in (("credit_score", profile.score), ("estimated_monthly_income", profile.monthly_income)) if v is None)
    if missing:
        return PolicyResult("", "NO_SUGGESTION", ("missing_profile_data",), missing)
    for card in ("Summit", "Rewards"):
        if profile.score >= MIN_SCORE[card] and profile.monthly_income >= MIN_INCOME[profile.country][card]:
            return PolicyResult(card, "SUGGESTED_FOR_DISCUSSION", ("country_income_and_score_band",), ())
    if profile.segment == "Student":
        return PolicyResult("Campus", "SUGGESTED_FOR_DISCUSSION", ("student_segment_unverified_enrollment",), ())
    if profile.score >= MIN_SCORE["Horizon"] and MIN_INCOME[profile.country]["Horizon"] <= profile.monthly_income < MIN_INCOME[profile.country]["Rewards"]:
        return PolicyResult("Horizon", "SUGGESTED_FOR_DISCUSSION", ("entry_income_and_score_band",), ())
    return PolicyResult("", "NO_SUGGESTION", ("profile_needs_human_review",), ())


def precheck(profile: Profile, card: str) -> PolicyResult:
    """Simulation only: policy evidence for human review, never bank approval."""
    _validate(profile, card)
    if profile.customer_status != "Active":
        return PolicyResult(card, "REVIEW_REQUIRED", ("customer_not_active",), ())
    if profile.has_current_credit_card:
        return PolicyResult(card, "REVIEW_REQUIRED", ("current_credit_card_requires_review",), ())
    if card == "Campus" and profile.segment != "Student":
        return PolicyResult(card, "REVIEW_REQUIRED", ("student_status_unverified",), ())
    missing = tuple(k for k, v in (("credit_score", profile.score), ("estimated_monthly_income", profile.monthly_income)) if v is None)
    if missing:
        return PolicyResult(card, "REVIEW_REQUIRED", ("missing_profile_data",), missing)
    reasons = []
    if profile.score < MIN_SCORE[card]:
        reasons.append("score_below_demo_threshold")
    if card != "Campus" and profile.monthly_income < MIN_INCOME[profile.country][card]:
        reasons.append("income_below_demo_threshold")
    if reasons:
        if card == "Campus" and profile.segment == "Student" and reasons == ["score_below_demo_threshold"]:
            return PolicyResult(card, "REVIEW_REQUIRED",
                                ("score_below_demo_threshold", "student_enrollment_unverified"), ())
        if card == "Horizon" and reasons == ["score_below_demo_threshold"] and profile.score >= 540:
            return PolicyResult(card, "REVIEW_REQUIRED", ("score_near_demo_threshold",), ())
        return PolicyResult(card, "DOES_NOT_MEET_DEMO_RULES", tuple(reasons), ())
    if card == "Campus":
        return PolicyResult(card, "REVIEW_REQUIRED", ("student_enrollment_unverified",), ())
    return PolicyResult(card, "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW", ("synthetic_thresholds_met",), ())
