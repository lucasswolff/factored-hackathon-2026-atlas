-- Read-only audit for the transaction-dispute prototype.
-- Run after 02_load.sql as FACTORED_USER / FACTORED_ANALYST.
-- Each SELECT returns a separate result set. The local results are in docs/data_audit.md.
-- All landing columns are VARCHAR; TRY_ conversions expose malformed values.

USE ROLE FACTORED_ANALYST;
USE WAREHOUSE FACTORED_WH;
USE DATABASE FACTORED_ANALYTICS;

-- 1. Row counts and primary-key uniqueness for the relevant tables.
SELECT 'CORE.CUSTOMERS' AS table_name, COUNT(*) AS row_count,
       COUNT(DISTINCT CUSTOMER_ID) AS distinct_ids,
       SUM(IFF(NULLIF(TRIM(CUSTOMER_ID), '') IS NULL, 1, 0)) AS missing_ids
FROM CORE.CUSTOMERS
UNION ALL
SELECT 'CORE.PRODUCTS', COUNT(*), COUNT(DISTINCT PRODUCT_ID),
       SUM(IFF(NULLIF(TRIM(PRODUCT_ID), '') IS NULL, 1, 0))
FROM CORE.PRODUCTS
UNION ALL
SELECT 'ACTIVITY.TRANSACTIONS', COUNT(*), COUNT(DISTINCT TRANSACTION_ID),
       SUM(IFF(NULLIF(TRIM(TRANSACTION_ID), '') IS NULL, 1, 0))
FROM ACTIVITY.TRANSACTIONS
UNION ALL
SELECT 'SERVICE.CALL_CENTER_INTERACTIONS', COUNT(*), COUNT(DISTINCT INTERACTION_ID),
       SUM(IFF(NULLIF(TRIM(INTERACTION_ID), '') IS NULL, 1, 0))
FROM SERVICE.CALL_CENTER_INTERACTIONS
UNION ALL
SELECT 'SERVICE.CALL_TRANSCRIPTS', COUNT(*), COUNT(DISTINCT TRANSCRIPT_ID),
       SUM(IFF(NULLIF(TRIM(TRANSCRIPT_ID), '') IS NULL, 1, 0))
FROM SERVICE.CALL_TRANSCRIPTS
UNION ALL
SELECT 'SERVICE.COMPLAINTS', COUNT(*), COUNT(DISTINCT COMPLAINT_ID),
       SUM(IFF(NULLIF(TRIM(COMPLAINT_ID), '') IS NULL, 1, 0))
FROM SERVICE.COMPLAINTS
UNION ALL
SELECT 'SERVICE.SATISFACTION_SURVEYS', COUNT(*), COUNT(DISTINCT SURVEY_ID),
       SUM(IFF(NULLIF(TRIM(SURVEY_ID), '') IS NULL, 1, 0))
FROM SERVICE.SATISFACTION_SURVEYS
ORDER BY table_name;

-- 2. Transaction data contract and time range. Invalid values include NULL.
SELECT COUNT(*) AS row_count,
       MIN(TRY_TO_TIMESTAMP_NTZ(TRANSACTION_DATE)) AS first_transaction_at,
       MAX(TRY_TO_TIMESTAMP_NTZ(TRANSACTION_DATE)) AS last_transaction_at,
       SUM(IFF(TRY_TO_TIMESTAMP_NTZ(TRANSACTION_DATE) IS NULL, 1, 0)) AS invalid_transaction_dates,
       SUM(IFF(TRY_TO_DECIMAL(AMOUNT, 18, 2) IS NULL, 1, 0)) AS invalid_amounts,
       SUM(IFF(TRY_TO_BOOLEAN(IS_FRAUD) IS NULL, 1, 0)) AS invalid_fraud_labels,
       SUM(IFF(FRAUD_SCORE IS NOT NULL AND TRY_TO_DOUBLE(FRAUD_SCORE) IS NULL, 1, 0)) AS invalid_fraud_scores
FROM ACTIVITY.TRANSACTIONS;

-- 3. Join integrity. A transaction must belong to the selected customer's product.
SELECT COUNT(*) AS transaction_rows,
       SUM(IFF(C.CUSTOMER_ID IS NULL, 1, 0)) AS missing_customer_rows,
       SUM(IFF(P.PRODUCT_ID IS NULL, 1, 0)) AS missing_product_rows,
       SUM(IFF(P.PRODUCT_ID IS NOT NULL AND P.CUSTOMER_ID <> T.CUSTOMER_ID, 1, 0)) AS product_owner_mismatch_rows,
       SUM(IFF(P.PRODUCT_TYPE IN ('Tarjeta Crédito', 'Tarjeta Débito'), 1, 0)) AS card_transaction_rows
FROM ACTIVITY.TRANSACTIONS T
LEFT JOIN CORE.CUSTOMERS C ON T.CUSTOMER_ID = C.CUSTOMER_ID
LEFT JOIN CORE.PRODUCTS P ON T.PRODUCT_ID = P.PRODUCT_ID;

-- 4. Complaint joins are audited, not trusted for a transaction match.
SELECT COUNT(*) AS complaint_rows,
       SUM(IFF(C.CUSTOMER_ID IS NULL, 1, 0)) AS missing_customer_rows,
       SUM(IFF(Q.AFFECTED_PRODUCT_ID IS NOT NULL, 1, 0)) AS populated_product_link_rows,
       SUM(IFF(Q.AFFECTED_PRODUCT_ID IS NOT NULL AND P.PRODUCT_ID IS NULL, 1, 0)) AS orphan_product_link_rows,
       SUM(IFF(P.PRODUCT_ID IS NOT NULL AND P.CUSTOMER_ID <> Q.CUSTOMER_ID, 1, 0)) AS product_owner_mismatch_rows,
       SUM(IFF(Q.ORIGIN_INTERACTION_ID IS NOT NULL, 1, 0)) AS populated_interaction_link_rows
FROM SERVICE.COMPLAINTS Q
LEFT JOIN CORE.CUSTOMERS C ON Q.CUSTOMER_ID = C.CUSTOMER_ID
LEFT JOIN CORE.PRODUCTS P ON Q.AFFECTED_PRODUCT_ID = P.PRODUCT_ID;

-- 5. Contact demand and observed first-contact outcomes.
-- CONTACT_REASON is broad; this does not measure charge-specific demand.
SELECT CONTACT_REASON, COUNT(*) AS interaction_rows,
       SUM(IFF(TRY_TO_BOOLEAN(WAS_RESOLVED) = TRUE, 1, 0)) AS resolved_rows,
       SUM(IFF(TRY_TO_BOOLEAN(WAS_ESCALATED) = TRUE, 1, 0)) AS escalated_rows,
       ROUND(100.0 * SUM(IFF(TRY_TO_BOOLEAN(WAS_RESOLVED) = TRUE, 1, 0)) / NULLIF(COUNT(*), 0), 2) AS resolved_pct
FROM SERVICE.CALL_CENTER_INTERACTIONS
GROUP BY CONTACT_REASON
ORDER BY interaction_rows DESC;

-- 6. Unrecognized-charge complaint volume and operational outcomes.
SELECT STATUS, COUNT(*) AS complaint_rows,
       SUM(IFF(TRY_TO_BOOLEAN(SLA_BREACHED) = TRUE, 1, 0)) AS sla_breached_rows,
       ROUND(100.0 * SUM(IFF(TRY_TO_BOOLEAN(SLA_BREACHED) = TRUE, 1, 0)) / NULLIF(COUNT(*), 0), 2) AS sla_breached_pct
FROM SERVICE.COMPLAINTS
WHERE CATEGORY = 'Transactions' AND SUBCATEGORY = 'Cargo no reconocido'
GROUP BY STATUS
ORDER BY complaint_rows DESC;

-- 7. Recorded transaction status and fraud-label prevalence.
SELECT TRANSACTION_STATUS, COUNT(*) AS transaction_rows,
       SUM(IFF(TRY_TO_BOOLEAN(IS_FRAUD) = TRUE, 1, 0)) AS fraud_labeled_rows,
       ROUND(100.0 * SUM(IFF(TRY_TO_BOOLEAN(IS_FRAUD) = TRUE, 1, 0)) / NULLIF(COUNT(*), 0), 3) AS fraud_labeled_pct
FROM ACTIVITY.TRANSACTIONS
GROUP BY TRANSACTION_STATUS
ORDER BY transaction_rows DESC;

-- 8. Card purchase subset: the strongest source for charge-explanation cases.
SELECT P.PRODUCT_TYPE, COUNT(*) AS purchase_rows,
       SUM(IFF(TRY_TO_BOOLEAN(T.IS_FRAUD) = TRUE, 1, 0)) AS fraud_labeled_rows
FROM ACTIVITY.TRANSACTIONS T
JOIN CORE.PRODUCTS P ON T.PRODUCT_ID = P.PRODUCT_ID
WHERE P.PRODUCT_TYPE IN ('Tarjeta Crédito', 'Tarjeta Débito')
  AND T.TRANSACTION_TYPE = 'Purchase'
GROUP BY P.PRODUCT_TYPE
ORDER BY purchase_rows DESC;

-- 9. Leakage warning: inspect how FRAUD_SCORE separates IS_FRAUD.
-- Do not use FRAUD_SCORE as a model feature until its generation is understood.
SELECT TRY_TO_BOOLEAN(IS_FRAUD) AS is_fraud,
       COUNT(*) AS transaction_rows,
       SUM(IFF(FRAUD_SCORE IS NULL, 1, 0)) AS missing_score_rows,
       SUM(IFF(TRY_TO_DOUBLE(FRAUD_SCORE) > 30, 1, 0)) AS score_above_30_rows,
       ROUND(AVG(TRY_TO_DOUBLE(FRAUD_SCORE)), 2) AS average_score,
       MAX(TRY_TO_DOUBLE(FRAUD_SCORE)) AS max_score
FROM ACTIVITY.TRANSACTIONS
GROUP BY TRY_TO_BOOLEAN(IS_FRAUD)
ORDER BY is_fraud;

-- 10. Text coverage and label variety for the language/intent plan.
SELECT DETECTED_LANGUAGE, COUNT(*) AS transcript_rows,
       COUNT(DISTINCT CUSTOMER_TEXT) AS distinct_customer_texts,
       COUNT(DISTINCT DETECTED_INTENTS) AS distinct_nonnull_intent_values
FROM SERVICE.CALL_TRANSCRIPTS
GROUP BY DETECTED_LANGUAGE
ORDER BY transcript_rows DESC;

-- 11. Linked CSAT by contact reason. CSAT uses its own 1-5 scale.
SELECT I.CONTACT_REASON, COUNT(*) AS csat_responses,
       ROUND(AVG(TRY_TO_DOUBLE(S.MAIN_SCORE)), 2) AS average_csat,
       SUM(IFF(TRY_TO_DOUBLE(S.MAIN_SCORE) <= 2, 1, 0)) AS low_score_responses
FROM SERVICE.SATISFACTION_SURVEYS S
JOIN SERVICE.CALL_CENTER_INTERACTIONS I ON S.INTERACTION_ID = I.INTERACTION_ID
WHERE S.SURVEY_TYPE = 'CSAT'
GROUP BY I.CONTACT_REASON
ORDER BY csat_responses DESC;
