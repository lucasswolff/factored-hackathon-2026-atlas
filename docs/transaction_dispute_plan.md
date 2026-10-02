# Archived candidate: transaction dispute triage

This is the previous project direction, retained for reference. The current build scope is the [campaign-triggered credit-product advisor](project_plan.md).

## Goal and scope

Build one working AI-assisted customer-service flow for a card charge that a customer questions. It begins as a transaction inquiry and becomes dispute intake if the customer still does not recognize the charge. This is the **Transaction Disputes** challenge category, with charge explanation as its first step.

The prototype must demonstrate three paths in both Spanish and Portuguese:

1. **Normal:** An authenticated customer identifies a charge; the system retrieves their transaction, explains the recorded merchant, date, amount, currency, and status, and checks whether that resolves the question.
2. **Ambiguous or unsupported:** Multiple charges match, data is missing, or the request is outside scope; the system asks a targeted question or abstains.
3. **Human-required:** A charge remains unrecognized or needs investigation; the system records the customer's description of the problem, creates a *mock* dispute intake only after confirmation, verifies the resulting case ID/status, and hands off the verified facts, customer statement, risk signals, actions taken, and open questions.

Fraud-risk signals may prioritize human review. The system must never automatically declare a transaction fraudulent, accuse the customer of a false claim, deny a dispute, move money, or claim that a mock intake is a live bank filing.

## Evidence and data fit

The organizer's [problem statement](factored_docs/problem_statement.pdf) requires a focused workflow, baseline, learned component, held-out evaluation, multilingual interactions, access controls, failure handling, and a credible route to operation. The [complete data dictionary](factored_docs/complete_data_dictonary.pdf) defines the available fields and joins.

Initial local CSV scans found 4,425,008 transactions, 686,296 call-center interactions, 171,321 transcripts, 67,095 complaints, and 400,000 products. Transactional contacts are the largest contact group (240,056). There are 12,297 complaints categorized as unrecognized charges. These are **dataset counts**, not measured production demand.

**Load status:** The user has completed the Snowflake load. Both Snowflake and the local CSVs came from the same AWS source, and the user reports `FACTORED_ANALYTICS.ACTIVITY.TRANSACTIONS` contains 4,425,008 rows, matching the local count. We treat the local audit as representative of the Snowflake data.

**Audit status:** The [offline data audit](data_audit.md) records the baseline and quality checks. [The Snowflake audit worksheet](../snowflake/03_audit.sql) can reproduce them if needed. It found that all populated complaint product links contradict customer ownership; the prototype must not use them for customer-level lookup.

Important limitations to validate and keep visible:

- Complaints have no transaction ID, and `origin_interaction_id` is empty in the local complaint rows. Do not infer a complaint-to-transaction link; require the customer to select the charge.
- All 44,570 populated complaint-to-product links point to products owned by different customers. Use complaints only in aggregate analysis until the data issue is resolved.
- Complaint descriptions have only five distinct values in the local files. They are not useful as rich dispute narratives.
- All 171,321 transcript rows have `detected_language = es`; customer text has only 42 distinct values and mostly asks about balances. Topic labels can disagree with the text. Treat Portuguese examples and varied dispute utterances as team-created test data, with clear provenance.
- `transactions.is_fraud` is a possible transaction-fraud label. Every score above 30 coincides with a fraud label locally, but some fraud-labeled rows score 30 or below or have no score. Audit score/label provenance before using `fraud_score` to train or evaluate a new model. There is no label for dishonest customer disputes.
- `products.current_balance` is a snapshot; it must not be represented as a historical balance at the time of an old transaction.
- The Snowflake landing tables store strings. Curated types, null handling, duplicates, timestamps, and as-of joins need explicit checks.

## Proposed system

| Component | Responsibility |
| --- | --- |
| Data layer | Use the loaded Snowflake tables; build typed, deduplicated, documented views for customers, products, transactions, and contact outcomes. Track source file and refresh time. |
| Service tools | Verify a trusted test session; fetch only that customer's permitted transactions; look up selected transaction; create and read back a mock dispute case; record an auditable handoff. |
| Conversation layer | Understand Spanish/Portuguese requests, maintain context, clarify ambiguity, explain tool-returned facts, and summarize a handoff. Policies and authorization are enforced outside model prose. |
| Risk support | If the labels pass audit, compare a transaction-fraud ranking model with a simple rules baseline. Exclude `fraud_score`, `is_fraud`, future outcomes, and post-dispute data from model features. Use scores only to prioritize review. |
| Evaluation | Replay fixed normal, ambiguous, human-required, and adversarial cases through the full system. Capture tool results, actions, latency, cost, and reviewer judgments. |

If the fraud label or features are unsuitable, use a learned retrieval or intent component with manually judged relevance/intent labels and document that change. Do not present a weak fraud model as a useful detector simply to satisfy the ML requirement.

## Success criteria

These are prototype acceptance criteria, not claims of production readiness.

- **Security and control:** All tests for cross-customer access, expired sessions, unauthorized actions, and prompt injection result in no unauthorized disclosure or action. No case creation occurs before explicit customer confirmation. A failed tool call is reported as a failure, never as a completed action.
- **Workflow:** Demonstrate one successful normal resolution, one clarification, and one verified mock dispute handoff in each language. The handoff contains the selected transaction, verified facts, customer statement, actions and outcome, and unanswered questions; it contains no unsupported accusation.
- **Evidence:** Publish the contact-volume and outcome baseline with query, time range, denominators, and data-quality notes. Report safe automated resolution separately from simple containment.
- **ML:** Compare at least one learned component with a baseline on the same held-out workload. Report sample sizes, label source/quality, split strategy, false positives and negatives, and relevant metrics. For fraud ranking, use precision/recall and precision at a fixed review capacity; do not use accuracy alone on the imbalanced label.
- **Operations:** Report p50/p95 end-to-end latency, cost per attempted case and per successful automated resolution, unsafe outcomes, missed/unnecessary handoffs, and results by language. Show bounded retries, tracing, safe fallback, and reproducible setup.

## How to test

1. **Data contracts:** Check headers, types, required fields, duplicate IDs, orphaned keys, date ranges, and late arrivals. Validate as-of behavior so later events cannot leak into historical evaluations.
2. **Service tests:** Exercise session ownership, multiple matching charges, missing records, read-back verification after mock case creation, idempotency, and tool timeouts/errors.
3. **Model evaluation:** Freeze a time-based held-out set before tuning; add customer separation or another leakage control where the task requires it. Compare the learned component with a simple baseline, inspect errors, and keep the final test set untouched until selection is complete.
4. **Conversation evaluation:** Use labeled Spanish and team-created Portuguese cases for normal, ambiguous, and human-required paths. Include wrong or missing data, expired sessions, cross-customer requests, prompt injection, unsupported requests, and multilingual ambiguity. Review factual grounding and handoff quality manually on a sample.
5. **End-to-end demo:** Replay fixed cases from a clean setup and save aggregate results and sanitized traces. Distinguish offline measurements, mock actions, and projected business impact.

## Next steps

1. Define the exact tool contracts, trusted test-session fixture, case state machine, and handoff format. Write the normal, ambiguous, and disputed-charge scripts in Spanish and Portuguese.
2. Implement the minimum end-to-end service and mock dispute case store, then add the conversation layer and deterministic policy gates.
3. Audit whether `is_fraud` supports a useful learned component without `fraud_score`; decide whether the existing score is a valid baseline, then freeze the held-out evaluation set before tuning.
4. Run the full evaluation, document failures and limits, then prepare the deployed demo, 4–6 slides, and short video required by the [kickoff deck](factored_docs/datathon_kickoff.pdf).
