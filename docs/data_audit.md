# Data audit and service baseline

This audit belongs to the [archived transaction-dispute concept](transaction_dispute_plan.md). The current MVP is the [credit-product advisor](project_plan.md); its data assessment is in [credit_marketing_feasibility.md](credit_marketing_feasibility.md).

This is an **offline baseline from the local CSV files**, not a measurement of the proposed service or of a live bank. I scanned the relevant CSVs with DuckDB 1.1.3 using `read_csv(..., all_varchar=true)` and aggregated without exporting customer-level rows. The local files and Snowflake tables were loaded from the same AWS source; the user confirmed Snowflake's transaction count matches. We treat them as the same dataset. [snowflake/03_audit.sql](../snowflake/03_audit.sql) is an optional, read-only way to reproduce these aggregates in Snowflake.

## Coverage and integrity

| Table | Local rows | Distinct primary IDs |
| --- | ---: | ---: |
| Customers | 150,000 | 150,000 |
| Products | 400,000 | 400,000 |
| Transactions | 4,425,008 | 4,425,008 |
| Call-center interactions | 686,296 | 686,296 |
| Call transcripts | 171,321 | 171,321 |
| Complaints | 67,095 | 67,095 |
| Satisfaction surveys | 212,759 | 212,759 |

Transaction timestamps run from 2023-06-17 to 2026-06-18. In the local files, all transaction timestamps and amounts parse, all `is_fraud` values parse as booleans, and all non-null `fraud_score` values parse as numbers. All 4,425,008 transactions join to a customer and product owned by that customer. There are 1,547,432 transactions on credit/debit card products; 1,083,406 of these are purchases.

**Complaint links are unreliable.** Of 67,095 complaints, 44,570 have an `affected_product_id`. Each ID exists in `CORE.PRODUCTS`, but **all 44,570** matching product rows have a different `customer_id` from the complaint. For the 12,297 unrecognized-charge complaints specifically, 8,143 have a product ID and all 8,143 have this mismatch; the other 4,154 have no product ID. All complaint customer IDs exist in `CORE.CUSTOMERS`, so this is an ownership inconsistency rather than a missing-record join. None of the complaints has an `origin_interaction_id`, and there is no transaction ID field. We cannot tell from these files why the product IDs were assigned this way. For the prototype, select transactions only from the authenticated customer's transaction/product records. Use complaint rows for aggregate baseline statistics, not to identify a customer's charge or create a case history.

## Demand and outcome baseline

| Signal | Local result | Interpretation |
| --- | ---: | --- |
| Transactional contact reason | 240,056 of 686,296 calls; 219,671 marked resolved (91.51%) | Large inquiry volume, but the reason is broad and does not isolate card charges. |
| Complaint contact reason | 117,021 calls; 51,021 marked resolved (43.60%) | Lower recorded first-contact resolution; this is not the same population as complaint cases. |
| Unrecognized-charge complaint category | 12,297 of 67,095 complaints | Direct evidence of dispute-related work. |
| Unrecognized-charge complaints with SLA breach | 2,507 of 12,297 (20.39%) | Useful operational baseline, not a predicted benefit of the prototype. |
| Linked CSAT, transactional contacts | 44,837 responses; average 2.91/5 | Survey respondents are a subset of interactions. |
| Linked CSAT, complaint contacts | 21,843 responses; average 2.43/5 | Do not generalize this average to all contacts. |

Within the 12,297 unrecognized-charge complaint rows, 4,906 are `In Process`, 3,648 `Open`, 2,516 `Resolved`, 618 `Escalated`, 498 `Closed`, and 111 `Rejected`. Their descriptions contain only **one distinct value**, so the text cannot support rich dispute-intent modeling. These complaint statuses are a snapshot; they are not end-to-end resolution rates for the new service.

## Fraud and language limits

There are 4,316 `is_fraud = true` transactions among 4,425,008 (0.098%). Card purchases have 1,086 fraud-labeled rows among 1,083,406 (0.100%). The low prevalence makes accuracy a poor standalone metric for a learned risk component.

The relationship between `fraud_score` and `is_fraud` is:

| Fraud score | Rows | Fraud-labeled rows |
| --- | ---: | ---: |
| Above 30 | 2,373 | 2,373 |
| 30 or below | 3,537,478 | 1,052 |
| Missing | 885,157 | 891 |

So **a score above 30 always coincides with a fraud label in this dataset**, but the reverse is false: it identifies only 2,373 of 4,316 fraud-labeled transactions (55.0%). It may be an intentional risk rule or an existing score with useful signal. We do not know whether the score was available before the label or derived from it. Use it as an existing risk signal or baseline only after checking its provenance; do not silently use it as a feature in a new fraud model and claim independent predictive performance. The label concerns **transaction fraud**, not whether a customer makes a dishonest dispute; the latter has no label in this dataset.

All 171,321 transcripts have `detected_language = es`. They contain only 42 distinct customer-text values, mostly balance questions, and just one non-null `detected_intents` value. Some topic labels contradict the transcript text. Use these rows for coverage analysis, not as unquestioned intent ground truth. Portuguese and varied dispute test cases must be team-created and clearly labeled as such.

## Implications for the prototype

1. Build charge lookup from `ACTIVITY.TRANSACTIONS` joined to `CORE.PRODUCTS` by `PRODUCT_ID`, with the service enforcing the authenticated `CUSTOMER_ID` and product ownership. Start with card purchases, then decide whether payments and withdrawals belong in scope.
2. Keep existing `SERVICE.COMPLAINTS` out of customer-level retrieval because its product links contradict ownership. The mock dispute case store should have its own verified `transaction_id` and customer ID.
3. Treat the reported contact and complaint metrics as the **before** baseline. Measure the proposed system on held-out cases; do not call offline simulation a production improvement.
4. Audit whether the transaction-fraud label supports a useful model without `fraud_score`. If it does not, evaluate another learned component, such as retrieval or intent recognition, against a baseline using manually judged cases.
