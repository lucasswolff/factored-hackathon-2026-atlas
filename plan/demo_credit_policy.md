# Synthetic recommendation and precheck policy v2

**Version:** `DEMO-CREDIT-POLICY-2026-09-30-v2`

**Status:** team-created simulation; no bank approval, pricing decision, or lending rule.
**Input lineage:** read-only `data/customers.csv` and `data/products.csv`, the
same organizer-supplied synthetic source loaded into Snowflake. These are
current-file snapshots, not verified live customer facts or point-in-time
historical application features. No target/approval labels were supplied to
calibrate this policy.

The advisor selects one of 10 allowlisted demo personas by alias. The alias is
a test-session fixture, not a password or real authentication. No arbitrary
customer ID, document number, or campaign link can retrieve a profile. A
profile-use permission is required before reading its score/income through the
service. A separate, card-specific, one-use consent is required for each
simulated precheck. The language model receives no raw customer row or policy
inputs; the deterministic service returns and explains its own result.

## Rules

| Card | Minimum score | Monthly estimated income: Colombia (COP) | México (MXN) | Argentina (ARS) |
| --- | ---: | ---: | ---: | ---: |
| Campus | 540 for numeric check; lower recorded-Student scores go to review | No income minimum; a positive stored estimate is required | Same | Same |
| Horizon | 560 for numeric check; 540–559 goes to review if income floor is met | 3,000,000 | 13,000 | 280,000 |
| Rewards | 650 | 10,000,000 | 40,000 | 820,000 |
| Summit | 720 | 24,000,000 | 105,000 | 2,100,000 |

These rounded values were chosen for a demo using aggregate country-level
income distributions and scores in the source file. Horizon's income floor is
below each country's observed active-customer 10th percentile; Rewards is near
the median; Summit is near the 75th percentile. Score cutoffs are similarly
illustrative, not estimated default-risk thresholds. Amounts are never
compared across currencies. No actual affordability calculation, debts,
delinquencies, account behavior, enrollment proof, credit bureau check, or
regulatory approval process is modeled.

Recommendation starts with the highest of Summit or Rewards whose local income
and score bands are met. Otherwise, a `Student`-segment customer with usable
score and positive stored income can discuss Campus; a non-student in Horizon's income band at score 560+ can
discuss Horizon. Missing income/score, active/blocked/suspended credit-card
holdings, or a mismatched high-income/low-score profile yields no automatic
suggestion. This is a conversation suggestion, **not** a precheck result.
`Student` is not proof of current enrollment.

For a consented precheck, the service checks active customer status, current
credit-card holding, card-specific student status, missing values, and the
score/income thresholds above. It returns one of:

- `MEETS_DEMO_THRESHOLDS_PENDING_REVIEW`: numeric demo rules met; human decides.
- `REVIEW_REQUIRED`: current card, missing data, unverified student status,
  recorded-Student Campus score below 540, or Horizon score 540–559 with the
  local income floor met.
- `DOES_NOT_MEET_DEMO_RULES`: a valid numeric value is below a synthetic
  threshold. This is **not** a real credit denial.

Campus always needs human enrollment verification, even when `Student` is
recorded. A non-`Student` requesting Campus is also sent to review rather than
treated as definitively non-enrolled. The policy does not approve a card, set a
limit or personalized rate, write to `PRODUCTS`, or create an application.
Horizon scores below 540 and income below its local floor still return
`DOES_NOT_MEET_DEMO_RULES`.

## Ten-record source check

The fixed fixture selector in [data_access.py](../advisor/data_access.py) picks
10 pinned row ordinals within `(country, segment, current-card)` groups from
the source CSVs. At service startup, it does **not** read score or income.
Only a permitted active test session can read its selected row's financial
fields. An owner-only, Git-ignored local index caches the ten source IDs and
current-card flags so subsequent starts need no full CSV scan. The fixture
never copies source IDs or personal fields into this report. The
[integration test](../advisor/test_customer_policy.py) re-reads the
files and checks all ten outcomes, consent gates, access failures, and exact
country-threshold boundaries. In the 10-record run:

Source checksums for this run: `customers.csv` SHA-256
`c5bb1f835d688b6191c7447e32b6334ce03641a24b3c060dceaf138514db34c6`;
`products.csv` SHA-256
`f071906b4342b35f80fb634cba46f74b3ccacc373fe96bbe55377d29553698df`.

| Result | Count |
| --- | ---: |
| Campus / Horizon / Rewards / Summit suggested for discussion | 3 / 1 / 1 / 2 |
| No automatic suggestion | 3 |
| Precheck: meets demo thresholds, pending review | 4 |
| Precheck: review required | 6 |
| Precheck: below synthetic threshold | 0 |
| Actual approvals or product acquisitions | 0 |

The selected records include all three countries, students, low scores,
missing score, and an existing credit-card holder. This is a **coverage test**
of the invented rules, not evidence they predict repayment or are fair to
customers. The organizer snapshot and synthetic values must be reviewed before
any use beyond a hackathon demonstration.
