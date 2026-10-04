# Four-card offer terms: country variants

**Status: design draft, 2026-09-28.** The [four card identities](../docs/card_catalog_draft.md) are team-created. The English brand names are **Campus, Horizon, Rewards, and Summit**, unchanged in Spanish and Portuguese conversations. This document defines the offer facts that the future UI and conversational layer may use; it does not define recommendation or prequalification thresholds. A card suggestion is for a signed-in existing customer after separate permission to use profile data. A card term is never inferred from `CORE.PRODUCTS` or from a historical campaign.

**Offer draft `CARD-CATALOG-DRAFT-2026-10-04-v3`: every term below is synthetic, proposed, and not yet an active customer-facing offer.** It is not copied from a real bank or the organizer dataset. This version keeps the previously chosen draft fees, spend thresholds, and interest figures and adds the no-commitment cancellation term. Final terms still require an effective period, benefit conditions, and complete cost disclosures; none of the figures is a guaranteed applicant rate.

## Offer matrix

| Card | Audience and product position | Core proposed benefits | Relative cost/benefit position |
| --- | --- | --- | --- |
| **Campus** | Student-only first card | Spending controls, reminders, education/everyday rewards; proposed zero annual fee | Modest limit and benefits. `CUSTOMERS.SEGMENT = 'Student'` is a demo routing signal, not proof of enrollment; a human verifies a real student requirement. |
| **Horizon** | Non-student entry card | Simple everyday rewards, alerts, standard support | No annual fee; simpler benefits than Rewards. |
| **Rewards** | Mid-tier card | Miles, a limited number of lounge visits, travel insurance, transparent foreign-currency conditions, everyday rewards | More benefits/cost than Horizon; fewer lounge visits and less travel coverage than Summit. |
| **Summit** | Premium card | Richer miles, more lounge visits, broader travel insurance, priority support | Higher cost and richer benefits than Rewards; no approval implied by income or segment. |

The following **12 country-card variants** share the **same core benefit rules**. Each variant needs its own version, dates, currency-denominated fee/waiver terms, and clear local cost disclosures:

| Country | Currency for offer amounts | Required card variants | Country-specific cost disclosure field |
| --- | --- | --- | --- |
| Colombia | COP | Campus, Horizon, Rewards, Summit | Purchase interest expressed as an effective annual rate (EA); all fees and conditions identified. |
| México | MXN | Campus, Horizon, Rewards, Summit | Annual ordinary interest rate and CAT, plus fees and conditions. |
| Argentina | ARS | Campus, Horizon, Rewards, Summit | TNA and CFT, plus fees and conditions. |

`CUSTOMERS.ESTIMATED_MONTHLY_INCOME` is in local currency according to the [organizer dictionary](../docs/factored_docs/complete_data_dictonary.pdf); it has no currency column. The country-to-currency mapping above is an explicit demo mapping. Income bands belong in the separate recommendation policy and must not be cross-country comparisons of raw amounts.

### Proposed annual fee, monthly spend waiver, and purchase interest

| Country | Campus annual fee | Horizon annual fee | Rewards maximum annual fee | Summit maximum annual fee | Draft purchase interest for every card in that country |
| --- | ---: | ---: | ---: | ---: | --- |
| Colombia | COP 0 | COP 0 | COP 360,000 | COP 1,200,000 | 20% effective annual (EA), synthetic |
| México | MXN 0 | MXN 0 | MXN 1,800 | MXN 6,000 | 36% fixed annual ordinary rate, synthetic |
| Argentina | ARS 0 | ARS 0 | ARS 60,000 | ARS 180,000 | 70% nominal annual (TNA), synthetic |

Campus and Horizon have no annual fee and no spend requirement. For Rewards and Summit, the listed annual fee is a **maximum** collected as 12 monthly installments. In each completed billing cycle, the installment is **fully waived** if posted eligible card purchases, net of refunds, meet or exceed that card's country threshold. If the threshold is missed, only that cycle's installment is charged. Cash advances, balance transfers, interest, and fees do not count toward spend. The first partial cycle after opening is waived; assessment begins with the first full cycle. These are synthetic demo rules, not terms from the supplied campaigns.

| Country | Rewards qualifying spend per billing cycle | Rewards installment when not waived | Summit qualifying spend per billing cycle | Summit installment when not waived |
| --- | ---: | ---: | ---: | ---: |
| Colombia | COP 3,000,000 | COP 30,000 | COP 10,000,000 | COP 100,000 |
| México | MXN 15,000 | MXN 150 | MXN 50,000 | MXN 500 |
| Argentina | ARS 400,000 | ARS 5,000 | ARS 1,200,000 | ARS 15,000 |

Example: a Rewards customer in México with MXN 16,000 of qualifying purchases in a full billing cycle pays **MXN 0** for that cycle's fee; with MXN 14,000, the fee is **MXN 150**. This is about card spending, **not** the customer's monthly income. A high income alone does not waive a fee.

**No minimum commitment and cancellation:** Campus, Horizon, Rewards, and Summit have no minimum holding or payment period in any of the three draft country variants. A cardholder may request cancellation at any time without an early-cancellation penalty. The monthly Rewards/Summit fee installments are charges for applicable billing cycles, not a requirement to keep the card for 12 months. No new annual-fee installments accrue for billing cycles after cancellation takes effect; already accrued charges and unpaid purchase balances remain payable. The exact effective date and handling of a partially completed cycle are not defined in this draft. This is a proposed product term; the demo has no live card-cancellation action or settled-account process.

**Argentina fee review:** The ARS fee and spend thresholds are fixed for each published offer version. Review them every six months **with inflation in mind**, but do **not** automatically index them to inflation or change an existing version mid-cycle. A review may result in unchanged amounts or a proposed new version. Any proposed increase requires a dated new version and advance customer notice; the draft should allow at least 60 days before a fee increase. This is a design rule for the demo, not a claim that the current figures are live. The [BCRA's card guidance](https://www.bcra.gob.ar/tarjeta-de-credito-funcionamiento-costos-y-buenas-practicas/) states that changes in charges or commissions must be communicated at least 60 calendar days in advance.

Suggested plain-language notice for an Argentine offer: “The fee and spending threshold shown are fixed for this version. We review them every six months and may update them to reflect inflation. Any change will be published in a new version and communicated in advance; there is no automatic increase.”

These are **illustrative product prices**, not a lending rate assigned to a person. The same purchase-interest figure within each country keeps card positioning about services and benefits rather than promising a better financing rate to a wealthier customer. Taxes, cash-advance fees, late fees, the México CAT, and the Argentina CFT are **not defined in this demo**; the assistant must not calculate or claim them from this table. If the user asks for the full cost of borrowing, it should say the draft is incomplete and offer a human handoff. No rate is guaranteed by a simulated precheck.

**México purchase-interest rule for the demo:** The synthetic 36% is an **annual ordinary fixed rate** for unpaid revolving purchase balances on all four México variants. It is a proposed card term, not a promotional or personalized rate. “Fixed” means this draft has no benchmark-linked adjustment or scheduled monthly rate reset; it does **not** mean every payment is the same. The simulated journey creates no credit contract, so the assistant must never promise a real customer this rate. An actual agreement would need its own effective terms and required disclosures. If the customer pays the statement's **payment to avoid interest** by the due date, ordinary purchase interest is generally avoided; otherwise the interest charge depends on the unpaid daily balances and payment timing. A 36% annual rate is roughly 3% per month as a simple rate illustration, **not** a quoted monthly charge or a CAT. Banco de México distinguishes the annual ordinary rate from [CAT, which incorporates other credit costs](https://www.banxico.org.mx/CATWebTarjetas/); [CONDUSEF explains the payment to avoid interest](https://revista.condusef.gob.mx/credito/2026/07/anatomia-de-tu-tdc/) and [ordinary-interest calculations from the average daily balance](https://revista.condusef.gob.mx/credito/tarjeta/2013/10/no-hay-dinero-mas-caro-que-el-que-no-se-tiene-2/). [CONDUSEF lists both fixed and variable rates](https://revista.condusef.gob.mx/usuario-inteligente/sabias-que/2016/07/no-pagues-de-mas/) among Mexican credit products; choosing fixed here is a **team-created simplification**, not a general rule for Mexico.

In plain language, all three rate labels describe **interest on an unpaid purchase balance**, before other charges; none is the full cost of the card:

- **20% EA (Colombia):** “Effective annual” states the one-year interest effect including compounding at that rate. The comparable monthly rate would be about 1.53%; actual charges depend on the unpaid balance and payment timing. [Colombia's financial supervisor explains EA conversions.](https://www.superfinanciera.gov.co/publicaciones/61554/consumidor-financieroinformacion-generalsimulador-de-conversion-de-tasas-de-interes-61554/)
- **36% fixed annual ordinary rate (México):** “Ordinary” means the regular interest rate on an unpaid revolving purchase balance. “Fixed” means this synthetic offer has no scheduled rate reset or floating benchmark. Dividing 36% by 12 gives roughly 3% for one month as a simple illustration, not the interest on a particular statement. It is not the CAT and excludes other costs. See the México rule above.
- **70% TNA (Argentina):** “Nominal annual” quotes a yearly rate before monthly compounding. Dividing by 12 gives roughly 5.83% for one month as a simple illustration; the effective one-year cost can be higher if unpaid interest compounds. It is not the CFT and it excludes fees. [BCRA defines nominal and effective rates.](https://www.bcra.gob.ar/archivos/Pdfs/BCRAyVos/Diccionario_Financiero.pdf)
- **Synthetic:** We invented these three percentages for the demo; they are not historical customer rates, current bank offers, or a recommendation to borrow.

### Shared benefit quantities across countries

The **same core benefits and quantities** apply to each named card in Colombia, México, and Argentina. They remain proposed demo terms until benefit conditions and an effective version are finalized:

| Card | Rewards | Lounge visits | Travel insurance |
| --- | --- | ---: | --- |
| Campus | 1% statement credit on eligible education purchases | None | None |
| Horizon | 1% statement credit on eligible groceries and transit | None | None |
| Rewards | 1 mile per USD-equivalent 1 of posted purchases, net of refunds | 2 proposed complimentary visits per card year | Proposed trip coverage up to USD 20,000 |
| Summit | 2 miles per USD-equivalent 1 of posted purchases, net of refunds | 8 proposed complimentary visits per card year | Proposed trip coverage up to USD 75,000 |

**Miles-earning rule:** Rewards and Summit earn on **all posted retail purchases**, regardless of merchant category or whether the purchase is domestic or international. The source amount in its transaction currency is converted to a USD equivalent, then multiplied by 1 or 2 miles respectively. Refunds/reversals remove the corresponding earned miles; cash advances, balance transfers, interest, fees, and cash-equivalent transfers are not purchases. This earning rule is separate from the **local-currency spending threshold** for a monthly fee waiver. The user selected USD-based miles, similar to the approach they know from Brazilian cards; this is a team-created demo rule, not a claim about actual Brazilian or source-bank products.

### Draft USD conversion rule for miles

This is a **team-created rewards-calculation rule**, not an actual card-network exchange-rate or billing-currency rule. It applies to the Rewards and Summit miles comparison only; it does not set the amount billed for a foreign-currency purchase or the local-currency spend used for a fee waiver.

1. Count a retail purchase only after it is posted. For a **historical illustration**, restrict source rows to `TRANSACTION_TYPE = 'Purchase'` and `TRANSACTION_STATUS = 'Approved'`, then use `ACTIVITY.TRANSACTIONS.PROCESS_DATE` as the *proxy* for posting date. An approved status and processing date do **not** independently verify card-ledger posting, so the result is illustrative rather than an actual earned-miles balance. Do not use `TRANSACTION_DATE` for the rate lookup. A hypothetical new purchase needs its actual future posting date before any exact miles result can be stated.
2. Take the recorded purchase `AMOUNT` and `CURRENCY`. For COP, MXN, or ARS, select `EXCHANGE_RATE` from `CORE.DAILY_EXCHANGE_RATES` where `DATE = process_date`, `SOURCE_CURRENCY = purchase currency`, and `TARGET_CURRENCY = 'USD'`. The rate's unit is **USD per one unit of source currency**, so `USD-equivalent = amount × exchange_rate`. For a USD purchase, use 1 USD per USD without a lookup. Use the direct source-currency→USD rate, not `BUY_RATE`, `SELL_RATE`, the inverse USD→source row, or `TRANSACTIONS.AMOUNT_USD` (whose calculation is not documented as this rewards rule). No FX spread is added to miles conversion.
3. Calculate with decimal arithmetic, retaining at least six fractional digits of USD equivalent internally. Multiply by **1 mile/USD** for Rewards or **2 miles/USD** for Summit. Sum purchase and linked-refund adjustments over a billing cycle, then round the resulting miles balance **once to two decimals, half up** for the demo statement. A linked refund reverses the original purchase's USD-equivalent value at its original rate, even if the refund is processed on a later date. If the original purchase cannot be identified, the adjustment and exact miles result remain unavailable rather than using the refund-date rate. Rounding is a demo convention; redemption and reward caps remain undefined.
4. If the date is missing, the direct pair/rate is missing or invalid, or the purchase is outside the supplied rate-table coverage, give the earning formula and say an exact result is unavailable. Do not silently carry forward a stale rate or use a live FX quote from an unapproved source. A future live demo would need a separately selected, dated FX provider and a quoted-rate snapshot before calculating new-purchase miles.

The local and Snowflake source table has one direct COP→USD, MXN→USD, and ARS→USD row per calendar day from **2023-06-17 through 2026-06-17**, with no duplicate date/pair keys in that interval. It is historical, not a current or contractual rate feed. For example, its **2025-08-31 MXN→USD rate is 0.057989**; a single MXN 1,000 posted purchase on that date would illustrate **57.99 Rewards miles** or **115.98 Summit miles** after the demo's two-decimal statement rounding. The rate is not an offer available today. Real card-network or issuer conversion may use a different rate/date and fees; [Visa's public rules](https://caribbean.visa.com/content/dam/VCOM/download/about-visa/visa-rules-public.pdf) describe separate exchange-rate and fee disclosures for international card transactions.

**Draft lounge rules for Rewards and Summit:** the listed 2 or 8 complimentary visits are per card year for the primary cardholder. A guest may enter with the cardholder, but each guest consumes one additional visit from the same allowance. Unused visits do not roll over. Entry depends on a participating lounge having capacity; the participating network and named lounges are not specified in this offer draft. The advisor can explain the quota and guest rule but must not promise access to a named lounge.

**Draft travel-coverage rules:** the listed USD 20,000 Rewards and USD 75,000 Summit amounts are maximum emergency-medical-expense coverage per covered trip for the primary cardholder, not cash benefits. The round-trip fare must be paid in full with the card; coverage runs from departure to return for trips of up to 30 consecutive days. Pre-existing conditions and elective treatment are excluded. Claims require the trip purchase record and medical documentation. The insurer, policy certificate, claims channel, geographic exclusions, and effective coverage status are not yet specified. Until a policy certificate is issued, the advisor must not promise that a particular trip or claim is insured. These are team-created comparison terms, not active entitlements. Campus's student-only condition still requires human verification because the dataset does not prove enrollment.

## Required fields before an offer is customer-facing

For each variant, record: stable card ID; offer version and provenance (`TEAM_CREATED_DEMO`); country and currency; effective/expiry dates; Spanish and Portuguese display copy; intended audience; annual fee and waiver conditions; purchase interest with country-appropriate rate basis; total-cost disclosure where applicable; cash-advance and late-fee terms if discussed; possible limit range and the fact that a limit is not guaranteed; reward earn/redemption rules and exclusions; lounge-visit quota and guest rules; travel-insurance coverage, qualifying conditions, exclusions, and provider/status; foreign-currency/FX terms; payment/grace-period terms; and a source section ID for every factual answer. If any term is still unset, the assistant must say it is unavailable in the demo and offer a human handoff rather than inventing it.

The country-specific disclosure field names reflect public consumer guidance from [CONDUSEF on CAT and card fees](https://revista.condusef.gob.mx/credito/2026/07/anatomia-de-tu-tdc/), [Colombia's financial supervisor on EA rates](https://www.superfinanciera.gov.co/publicaciones/61554/consumidor-financieroinformacion-generalsimulador-de-conversion-de-tasas-de-interes-61554/), and [BCRA on card costs](https://www.bcra.gob.ar/tarjeta-de-credito-funcionamiento-costos-y-buenas-practicas/). These sources guide which concepts to state; the four demo products and any eventual amounts are not taken from them.

## Open choices for final terms

- The user accepted the draft prices, spend thresholds, and interest figures, the USD-based all-purchase miles rule, and presenting travel features only as proposed benefits. No real offer is active.
- The historical miles-conversion method is drafted above. A live dated FX source for new purchases, reward caps/redemption rules, benefit exclusions, insurer/network arrangements, and effective dates are still open before writing customer-facing FAQ answers. Taxes, cash-advance/late-fee terms, México CAT, and Argentina CFT are explicitly unavailable in the demo; do not invent them or a complete borrowing-cost estimate. Never imply a historical source campaign contained these terms.
