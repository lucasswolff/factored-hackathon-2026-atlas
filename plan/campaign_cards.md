# Campaign cards: source audit and proposed demo mapping

**Status: step 1 shortlist for review, 2026-09-27.** The judge will click a displayed campaign card to start a **new simulated conversation**. That click is a new demo event, not a replay of a historical `CAMPAIGN_SENDS` click, and it does not authenticate the visitor. Each displayed card points to one team-created offer from the [draft catalog](../docs/card_catalog_draft.md). The supplied campaign rows have only the generic promoted product `Tarjeta Crédito`; they do not identify these named cards or provide their terms. **The four offers, including Campus, are planned for Colombia, México, and Argentina.** A source campaign's target country limits that campaign card, not the offer's country availability.

## Selection method

Select supplied `MARKETING_CAMPAIGNS` rows where `PROMOTED_PRODUCT = 'Tarjeta Crédito'`, favoring a `TARGET_SEGMENT` aligned with the intended card audience, a usable historical send population, and an `Acquisition` or `Cross-sell` objective. Avoid `Retention`, `Reactivation`, and `Up-sell` for the initial no-card journey. Target segment is **campaign metadata**, not an eligibility rule. A blank target country means the source has no country restriction; it does not prove that every offer term applies in every country. The demo must label the mapping and offer content as created by the team.

| Demo offer | Source campaign ID and name | Source objective / audience | Historical evidence | Why this candidate; limitation |
| --- | --- | --- | --- | --- |
| **Campus** | `CMP-YYT37NY1CZS7` — `CMP_XSL_CC_Jun2025_0036` | Cross-sell; `Student`; Colombia | 13,815 sends; 800 recorded clicks; 12 clicked sends matched both target segment and country; 4 of those currently belong to active customers without a credit card | A source campaign explicitly targeting students in Colombia. Its country target restricts this historical campaign card only; **Campus itself is planned in all three countries**. The mismatch between campaign target and actual send recipients does not establish student enrollment. |
| **Horizon** | `CMP-I5TGQ4SXP4EG` — `CMP_ACQ_CC_Jan2026_0173` | Acquisition; `Basic`; country unspecified | 10,145 sends; 585 recorded clicks; 356 clicked sends matched `Basic`; 167 of those currently belong to active customers without a credit card | Good entry-card audience and reach in all three customer countries. `Acquisition` does not tell us whether the campaign meant new bank customers or new cardholders; the demo itself remains existing-customer-only. |
| **Rewards** | `CMP-NM2UHJMKPA0C` — `CMP_ACQ_CC_Jan2024_0050` | Acquisition; `Plus`; country unspecified | 7,067 sends; 405 recorded clicks; 102 clicked sends matched `Plus`; 44 of those currently belong to active customers without a credit card | `Plus` is a plausible mid-tier audience. Source data does not say this campaign included miles, lounges, insurance, or any other proposed Rewards benefit. The `Acquisition` objective has the same ambiguity as Horizon's. |
| **Summit** | `CMP-N3I2U4V7H3KU` — `CMP_XSL_CC_Jul2024_0160` | Cross-sell; `Premium`; country unspecified | 12,453 sends; 1,190 recorded clicks; 112 clicked sends matched `Premium`; 54 of those currently belong to active customers without a credit card | Strongest aligned premium cross-sell candidate with measured clicks. The source does not contain premium-card terms; Summit benefits are team-created. |

All four campaign rows are marked `Completed`; their recorded end dates precede 2026-09-27. Display them as **historical campaign context used in a demo**, never as currently active bank promotions. The UI may use a friendly, team-created title such as “Discover Campus,” but should retain the source campaign ID/name in an inspectable detail and mark the named-card mapping as demo-created. Do not expose source campaign codes as customer-facing card names.

The counts above are **send/click rows, not unique people**. `active customer without a credit card` uses the current `CUSTOMERS` and `PRODUCTS` snapshots, so it does not establish who held a card or had marketing consent when a historical message was sent. Campaign target fields also do not guarantee that actual sends reached only that target: Campus has 800 recorded clicks but just 12 clicked sends match both its `Student` and Colombia targeting. Historical click rates remain descriptive; they do not validate the demo's four-offer mapping.

## Country coverage and demo personas

The browser entry screen now lets students explore Campus in all three countries. Colombia uses the mapped historical Campus campaign; México and Argentina open a Campus-focused direct offer conversation without a campaign ID. The general direct-entry path can also use existing no-card customers in all three countries. Current active, no-credit-card snapshot counts by segment are:

| Country | Student | Basic | Plus | Premium |
| --- | ---: | ---: | ---: | ---: |
| Argentina | 623 | 7,843 | 3,242 | 1,297 |
| Colombia | 1,042 | 11,815 | 4,943 | 1,957 |
| México | 1,628 | 19,477 | 8,104 | 3,338 |

These counts show possible test-persona populations, not verified card eligibility. The selected **Campus campaign row** is Colombia-targeted; it says nothing about Campus availability in México or Argentina. Horizon, Rewards, and Summit have no source campaign country restriction, but their future offer terms still need distinct country versions. Student personas from México and Argentina can start a Campus-focused direct conversation. If we also want a Campus campaign-click path in those countries, it needs a separate, clearly labeled demo campaign card or an appropriately matched source campaign; the Colombia-targeted source row must not be presented as a México/Argentina campaign.

## Reproduce and inspect in Snowflake

The local read-only audit is [analysis/audit_campaign_cards.py](../analysis/audit_campaign_cards.py). Run `python3 analysis/audit_campaign_cards.py` to see all 52 credit-card campaigns and their aggregate send/click counts. Local CSVs and Snowflake came from the same AWS source; **the user does not need to open Snowflake to create this mapping**. To inspect the four selected campaign rows there if desired:

```sql
SELECT CAMPAIGN_ID, CAMPAIGN_NAME, CAMPAIGN_OBJECTIVE, PROMOTED_PRODUCT,
       TARGET_SEGMENT, TARGET_COUNTRY, START_DATE, END_DATE, CAMPAIGN_STATUS
FROM FACTORED_ANALYTICS.MARKETING.MARKETING_CAMPAIGNS
WHERE CAMPAIGN_ID IN (
  'CMP-YYT37NY1CZS7',
  'CMP-I5TGQ4SXP4EG',
  'CMP-NM2UHJMKPA0C',
  'CMP-N3I2U4V7H3KU'
)
ORDER BY CAMPAIGN_NAME;
```

The source campaign ID → demo offer ID mapping should eventually be stored in a small versioned demo-owned table or config, rather than written back into the supplied campaign table. Only after that mapping exists should a new demo click be attributed to a named offer.
