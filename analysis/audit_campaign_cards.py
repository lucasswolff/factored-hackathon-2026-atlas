"""Aggregate local campaign evidence for planning demo cards; emits no customer rows.

Run from the repository root with: python3 analysis/audit_campaign_cards.py
The local CSVs and Snowflake tables were loaded from the same source.
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        yield from csv.DictReader(source)


def country(value):
    return {"Mexico": "México"}.get(value, value)


campaigns = {
    r["campaign_id"]: r
    for r in rows(DATA / "marketing_campaigns.csv")
    if r["promoted_product"] == "Tarjeta Crédito"
}
customers = {
    r["customer_id"]: (
        r["country"],
        r["segment"],
        r["customer_status"],
        r["accepts_marketing"],
    )
    for r in rows(DATA / "customers.csv")
}
card_owners = {
    r["customer_id"]
    for r in rows(DATA / "products.csv")
    if r["product_type"] == "Tarjeta Crédito"
}

counts = defaultdict(Counter)
country_counts = defaultdict(Counter)
for path in (DATA / "campaign_sends").rglob("*.csv"):
    for send in rows(path):
        campaign_id = send["campaign_id"]
        if campaign_id not in campaigns:
            continue
        stat = counts[campaign_id]
        stat["sends"] += 1
        if send["was_clicked"].lower() != "true":
            continue
        stat["clicks"] += 1
        customer = customers.get(send["customer_id"])
        if customer is None:
            stat["orphan_clicks"] += 1
            continue
        customer_country, customer_segment, status, marketing = customer
        campaign = campaigns[campaign_id]
        target_country = country(campaign["target_country"])
        if target_country and customer_country != target_country:
            stat["off_target_country"] += 1
            continue
        if campaign["target_segment"] and customer_segment != campaign["target_segment"]:
            stat["off_target_segment"] += 1
            continue
        stat["matched_clicks"] += 1
        country_counts[campaign_id][customer_country] += 1
        if status == "Active" and send["customer_id"] not in card_owners:
            stat["active_without_card"] += 1
            if marketing.lower() == "true":
                stat["with_current_marketing_opt_in"] += 1

print(
    "campaign_id|name|objective|target_segment|target_country|status|"
    "sends|clicks|matched_clicks|active_without_card|"
    "with_current_marketing_opt_in|matched_click_countries"
)
for campaign_id, campaign in sorted(campaigns.items(), key=lambda item: item[1]["campaign_name"]):
    stat = counts[campaign_id]
    countries = ",".join(
        f"{place}:{n}" for place, n in sorted(country_counts[campaign_id].items())
    )
    print(
        "|".join(
            [
                campaign_id,
                campaign["campaign_name"],
                campaign["campaign_objective"],
                campaign["target_segment"] or "(all)",
                campaign["target_country"] or "(all)",
                campaign["campaign_status"],
                *(
                    str(stat[key])
                    for key in (
                        "sends",
                        "clicks",
                        "matched_clicks",
                        "active_without_card",
                        "with_current_marketing_opt_in",
                    )
                ),
                countries,
            ]
        )
    )
