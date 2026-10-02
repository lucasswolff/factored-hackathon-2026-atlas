# Exploratory idea: campaign-triggered credit-product service

This audit informed the current [credit-product MVP](mvp_requirements.md). It assesses a journey from marketing message to click, product conversation, and potential application under the organizer's [Credit-Product Info & Eligibility Support](factored_docs/problem_statement.pdf) example.

## What the supplied data supports

The figures below come from aggregate scans of the local CSVs with DuckDB 1.1.3 (`read_csv(..., all_varchar=true, hive_partitioning=false)`). The local and Snowflake copies came from the same AWS source.

| Journey step | Evidence | Limitation |
| --- | --- | --- |
| Campaign sent | 200 campaigns; 175 have sends. There are 1,746,801 sends and 1,642,044 delivered messages. | Campaign descriptions are generic; they do not contain credit offer terms. |
| Customer opens/clicks | 487,309 opens and 97,793 clicks. `CAMPAIGN_SENDS` includes send, open, click, and conversion timestamps. | This measures message engagement, not eligibility or purchase. |
| Customer opens a product conversation | 68,691 chats exist in call-center interactions, including 15,135 `Producto` and 5,612 `Comercial` chats. | Only 281 clicked sends are followed by any chat for the same customer within seven days; 84 are product/commercial chats. The chat has no send or campaign ID, so these are temporal associations, not proven attribution. |
| Customer acquires product | 9,799 sends have `had_conversion = true` (0.56% of sends; 10.0% of clicks). | The dictionary defines conversion as the desired action, not a product contract. Only 2 of these 9,799 have a same-day opening of the promoted product. For Acquisition campaigns, 1 of 1,564 flagged conversions has a same-day promoted-product opening. |

Of the 1,564 flagged conversions on Acquisition-objective sends, 1,328 have a specified promoted product type; 380 recipients already owned that product type before the send. Across all objectives, only 40 flagged conversions have a matching promoted-product opening within 30 days of the send. This does **not** mean only 40 acquisitions occurred: attribution fields and conversion semantics are insufficient to determine the actual number. It does mean `had_conversion` cannot be reported as verified contracts.

`DIGITAL_EVENTS` has 15,620,994 rows. Its `utm_campaign` is populated on 838,917 rows, but contains only three generic values (`retention`, `spring_promo`, `new_users`), not the IDs in `MARKETING_CAMPAIGNS`. Product events are page views/clicks, with no product application or purchase events. A same-customer, seven-day join finds 3,503 clicked sends followed by a Product PageView; this remains a temporal association.

## Product information and eligibility

The campaign table identifies a promoted product, and `CUSTOMERS` has credit score and estimated income fields. `PRODUCTS` records existing customer holdings, product type, credit limit, rate, opening date, and channel. These can support context and descriptive analysis, but they are **not a current offer catalog, approved eligibility policy, or application outcome dataset**. Campaign descriptions are generic; for example, credit-card campaigns have 52 rows but only five distinct non-null descriptions.

To make this a credible credit-service prototype, choose one product (for example, a credit card or personal loan) and add a clearly labeled **synthetic, versioned offer and eligibility policy**. The conversation model can explain those terms and collect missing information. A deterministic policy service should calculate a simulated eligibility result; borderline or unsupported cases go to a human. After customer confirmation, record and read back a **mock application or lead** in a separate prototype store. Do not call this a real product acquisition, independently approve credit, or insert a fabricated contract into the supplied `PRODUCTS` table.

## Can we A/B test campaigns?

Every one of the 175 campaigns with sends has five `template_used` variants, so historical click and conversion rates can be **compared descriptively** by template. The data does not show randomized assignment or a holdout, and 47,482 campaign–customer pairs saw more than one variant. Historical differences therefore cannot establish that one template *caused* more purchases or even more clicks. A prospective prototype A/B test can explicitly randomize one customer to one variant, log assignment and exposure, define a single outcome (such as qualified mock applications), and analyze by assignment. Without real users and real outcomes, its results are a simulation, not measured business lift.

## Recommendation

**Feasible as a focused Credit-Product Info & Eligibility Support prototype:** a customer clicks a credit-product campaign, authenticates, asks questions in Spanish or Portuguese, receives grounded product information and a simulated eligibility explanation, then either ends the conversation or confirms a mock application/human handoff. Marketing data establishes top-of-funnel demand and a baseline for engagement. The conversation, policy, application action, and experiment instrumentation must be built and evaluated as new prototype components.

This is less directly supported end-to-end by the historical data than transaction-dispute triage: the campaign-to-chat and conversion-to-contract links are missing. The trade-off is a compelling acquisition journey with more synthetic policy and outcome data. Keep the challenge submission centered on **customer service and eligibility**, with campaign analytics as supporting context, rather than presenting a standalone marketing optimization system.
